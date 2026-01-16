"""
Main Trading Bot Orchestrator

Coordinates all strategies, manages the trading loop,
and handles execution of trades.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from .config import BotConfig, load_config
from .models import Market, Order, Position, Side, OrderType, Strategy
from .api import PolymarketClient, PriceFeedClient
from .strategies import (
    MarketMakerStrategy,
    TrendFollowerStrategy,
    DiscountHunterStrategy,
)
from .strategies.base import StrategySignal
from .risk_management import RiskManager
from .analytics import Analytics

logger = logging.getLogger(__name__)


class PolymarketTradingBot:
    """
    Polymarket Trading Bot

    Implements three core strategies:
    1. Market Making - Enter both sides when spreads are wide
    2. Trend Following - Reallocate capital to winning positions
    3. Discount Hunting - Accumulate heavily discounted positions

    Performance Target: 95%+ win rate
    """

    def __init__(self, config: Optional[BotConfig] = None):
        self.config = config or load_config()
        self.running = False

        # Initialize clients
        self.polymarket = PolymarketClient(self.config.api)
        self.price_feeds = PriceFeedClient()

        # Initialize strategies
        self.market_maker = MarketMakerStrategy(self.config.trading)
        self.trend_follower = TrendFollowerStrategy(self.config.trading)
        self.discount_hunter = DiscountHunterStrategy(self.config.trading)

        # Initialize risk management
        self.risk_manager = RiskManager(
            self.config.risk,
            self.config.trading.initial_capital
        )

        # Initialize analytics
        self.analytics = Analytics()
        self.analytics.set_initial_capital(self.config.trading.initial_capital)

        # State tracking
        self.active_markets: dict[str, Market] = {}
        self.last_market_scan = None

        logger.info("Polymarket Trading Bot initialized")

    async def start(self):
        """Start the trading bot."""
        logger.info("Starting trading bot...")

        async with self.polymarket, self.price_feeds:
            self.running = True
            await self._main_loop()

    async def stop(self):
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")
        self.running = False

    async def _main_loop(self):
        """
        Main trading loop.

        Continuously:
        1. Scan for new markets (Phase 1)
        2. Monitor active positions (Phase 2)
        3. Hunt for discounts (Phase 3)
        4. Manage risk
        """
        logger.info("Entering main trading loop")

        while self.running:
            try:
                # Check risk levels first
                alerts = self.risk_manager.check_risk_levels()
                for alert in alerts:
                    logger.warning(f"Risk Alert [{alert.level}]: {alert.message}")

                # Skip trading if disabled
                if not self.risk_manager.trading_enabled:
                    logger.info("Trading disabled, waiting...")
                    await asyncio.sleep(60)
                    continue

                # Phase 1: Monitor for new markets
                await self._run_phase1_market_making()

                # Phase 2: Manage active positions (trend following)
                await self._run_phase2_trend_following()

                # Phase 3: Hunt for discounts (continuous)
                await self._run_phase3_discount_hunting()

                # Take periodic snapshots
                if self._should_take_snapshot():
                    self.risk_manager.take_snapshot()
                    self.analytics.update_equity(self.risk_manager.current_capital)

                # Wait before next iteration
                await asyncio.sleep(self.config.main_loop_interval)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

        logger.info("Main loop exited")

    # ==================== Phase 1: Market Making ====================

    async def _run_phase1_market_making(self):
        """
        Phase 1: Market Making Strategy

        - Scan for new Bitcoin markets
        - Enter both sides when spreads are wide
        - Monitor for trend emergence (handoff to Phase 2)
        """
        # Scan for new markets periodically
        if self._should_scan_markets():
            markets = await self.polymarket.get_new_bitcoin_markets(hours=24)
            for market in markets:
                self.active_markets[market.id] = market

        # Analyze each market for market-making opportunity
        for market in self.active_markets.values():
            # Update market data
            try:
                prices = await self.polymarket.get_market_prices(market.id)
                market.yes_price = prices["yes_price"]
                market.no_price = prices["no_price"]
                market.yes_bid = prices["yes_bid"]
                market.yes_ask = prices["yes_ask"]
                market.no_bid = prices["no_bid"]
                market.no_ask = prices["no_ask"]
            except Exception as e:
                logger.warning(f"Failed to update prices for {market.id}: {e}")
                continue

            # Generate signal
            signal = await self.market_maker.analyze(market)

            if signal:
                await self._execute_market_maker_signal(signal, market)

    async def _execute_market_maker_signal(self, signal: StrategySignal, market: Market):
        """Execute a market-making signal."""
        if signal.action == "enter_both_sides":
            # Check risk limits
            capital = self.risk_manager.current_capital
            allocation = capital * self.config.trading.max_position_percent

            can_trade, reason = self.risk_manager.can_open_position(
                market.id, allocation
            )
            if not can_trade:
                logger.info(f"Cannot enter market maker: {reason}")
                return

            # Calculate position sizes
            yes_qty, no_qty = self.market_maker.calculate_entry_amounts(
                allocation, market
            )

            # Execute both orders
            yes_order = await self.polymarket.place_order(
                market_id=market.id,
                side=Side.YES,
                quantity=yes_qty,
                order_type=OrderType.MARKET
            )

            no_order = await self.polymarket.place_order(
                market_id=market.id,
                side=Side.NO,
                quantity=no_qty,
                order_type=OrderType.MARKET
            )

            if yes_order.is_filled and no_order.is_filled:
                # Create positions
                yes_position = Position(
                    market_id=market.id,
                    side=Side.YES,
                    quantity=yes_order.filled_quantity,
                    entry_price=yes_order.filled_price,
                    current_price=market.yes_price,
                    strategy=Strategy.MARKET_MAKER,
                )
                no_position = Position(
                    market_id=market.id,
                    side=Side.NO,
                    quantity=no_order.filled_quantity,
                    entry_price=no_order.filled_price,
                    current_price=market.no_price,
                    strategy=Strategy.MARKET_MAKER,
                )

                # Register with strategy and risk manager
                self.market_maker.register_entry(
                    market.id, yes_position, no_position
                )
                self.risk_manager.register_position(yes_position)
                self.risk_manager.register_position(no_position)

                logger.info(
                    f"Market maker entry: {market.id} - "
                    f"YES: {yes_qty:.0f} @ ${yes_order.filled_price:.3f}, "
                    f"NO: {no_qty:.0f} @ ${no_order.filled_price:.3f}"
                )

        elif signal.action == "exit_both":
            # Determine winning side for handoff
            winning_side = self.market_maker.get_winning_side(market.id)
            losing_position = self.market_maker.get_losing_position(market.id)

            if losing_position:
                # Close losing position
                await self._close_position(losing_position)

            # Handoff winner to trend follower
            if winning_side:
                paired = self.market_maker.paired_positions.get(market.id)
                if paired:
                    winning_position = (
                        paired.yes_position if winning_side == Side.YES
                        else paired.no_position
                    )
                    if winning_position:
                        self.trend_follower.handoff_from_market_maker(
                            market.id, winning_side, winning_position
                        )

    # ==================== Phase 2: Trend Following ====================

    async def _run_phase2_trend_following(self):
        """
        Phase 2: Trend Following Strategy

        - Monitor position momentum
        - Scale into winners
        - Exit on reversal or stop-loss
        """
        for market in self.active_markets.values():
            signal = await self.trend_follower.analyze(market)

            if signal:
                await self._execute_trend_signal(signal, market)

    async def _execute_trend_signal(self, signal: StrategySignal, market: Market):
        """Execute a trend-following signal."""
        if signal.action.startswith("buy_"):
            side = Side.YES if "yes" in signal.action else Side.NO

            # Check if scaling in or new entry
            existing = self.trend_follower.trend_positions.get(market.id)

            if existing:
                # Scale-in to existing position
                capital = self.risk_manager.current_capital * 0.05  # 5% scale-in
                price = market.yes_price if side == Side.YES else market.no_price
                quantity = capital / price if price > 0 else 0

                order = await self.polymarket.place_order(
                    market_id=market.id,
                    side=side,
                    quantity=quantity,
                    order_type=OrderType.MARKET
                )

                if order.is_filled:
                    self.trend_follower.record_scale_in(market.id, order.filled_quantity)
                    logger.info(f"Trend scale-in: {market.id} {side.value} +{quantity:.0f}")

            else:
                # New trend entry
                capital = self.risk_manager.current_capital
                allocation = capital * self.config.trading.max_position_percent

                can_trade, reason = self.risk_manager.can_open_position(
                    market.id, allocation
                )
                if not can_trade:
                    logger.info(f"Cannot enter trend: {reason}")
                    return

                price = market.yes_price if side == Side.YES else market.no_price
                quantity = allocation / price if price > 0 else 0

                order = await self.polymarket.place_order(
                    market_id=market.id,
                    side=side,
                    quantity=quantity,
                    order_type=OrderType.MARKET
                )

                if order.is_filled:
                    position = Position(
                        market_id=market.id,
                        side=side,
                        quantity=order.filled_quantity,
                        entry_price=order.filled_price,
                        current_price=price,
                        strategy=Strategy.TREND_FOLLOWER,
                    )
                    self.trend_follower.register_position(market.id, side, position)
                    self.risk_manager.register_position(position)
                    logger.info(f"Trend entry: {market.id} {side.value} {quantity:.0f} @ ${price:.3f}")

        elif signal.action.startswith("sell_"):
            # Exit trend position
            trend_pos = self.trend_follower.trend_positions.get(market.id)
            if trend_pos:
                await self._close_position(trend_pos.position)
                del self.trend_follower.trend_positions[market.id]

    # ==================== Phase 3: Discount Hunting ====================

    async def _run_phase3_discount_hunting(self):
        """
        Phase 3: Discount Hunting Strategy (MAJOR PROFIT DRIVER)

        - Scan ALL markets for extreme discounts
        - Aggressive accumulation at $0.01-$0.03
        - Scale out at profit targets
        """
        # Get all active markets
        try:
            all_markets = await self.polymarket.get_markets(active_only=True, limit=200)
        except Exception as e:
            logger.warning(f"Failed to fetch markets for discount hunting: {e}")
            return

        for market in all_markets:
            # Update prices
            try:
                prices = await self.polymarket.get_market_prices(market.id)
                market.yes_price = prices["yes_price"]
                market.no_price = prices["no_price"]
            except Exception:
                continue

            # Analyze for discount opportunity
            signal = await self.discount_hunter.analyze(market)

            if signal:
                await self._execute_discount_signal(signal, market)

    async def _execute_discount_signal(self, signal: StrategySignal, market: Market):
        """Execute a discount hunting signal."""
        if signal.action.startswith("buy_"):
            side = Side.YES if "yes" in signal.action else Side.NO
            price = signal.price or (market.yes_price if side == Side.YES else market.no_price)

            # Calculate position size (maximize shares, limit risk)
            capital = self.risk_manager.current_capital
            max_risk = capital * 0.05  # 5% max risk for discounts
            quantity = self.discount_hunter.calculate_position_size(
                capital, price, max_risk
            )

            can_trade, reason = self.risk_manager.can_open_position(
                market.id, quantity * price
            )
            if not can_trade:
                logger.info(f"Cannot enter discount: {reason}")
                return

            order = await self.polymarket.place_order(
                market_id=market.id,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET
            )

            if order.is_filled:
                position = Position(
                    market_id=market.id,
                    side=side,
                    quantity=order.filled_quantity,
                    entry_price=order.filled_price,
                    current_price=price,
                    strategy=Strategy.DISCOUNT_HUNTER,
                )
                self.discount_hunter.register_position(
                    market.id, side, position, order.filled_price
                )
                self.risk_manager.register_position(position)

                potential_return = 0.50 / order.filled_price
                logger.info(
                    f"DISCOUNT ENTRY: {market.id} {side.value} "
                    f"{quantity:.0f} @ ${order.filled_price:.3f} "
                    f"(potential {potential_return:.0f}x return)"
                )

        elif signal.action.startswith("sell_"):
            # Take profit on discount position
            discount_pos = self.discount_hunter.discount_positions.get(market.id)
            if discount_pos:
                # Sell specified quantity
                sell_qty = signal.quantity or discount_pos.position.quantity

                order = await self.polymarket.place_order(
                    market_id=market.id,
                    side=discount_pos.side,
                    quantity=sell_qty,
                    order_type=OrderType.MARKET
                )

                if order.is_filled:
                    # Update position
                    discount_pos.position.quantity -= order.filled_quantity

                    profit = (order.filled_price - discount_pos.entry_price) * order.filled_quantity
                    logger.info(
                        f"DISCOUNT PROFIT: {market.id} sold {sell_qty:.0f} "
                        f"@ ${order.filled_price:.3f}, profit: ${profit:.2f}"
                    )

                    # Remove position if fully closed
                    if discount_pos.position.quantity <= 0:
                        del self.discount_hunter.discount_positions[market.id]

    # ==================== Position Management ====================

    async def _close_position(self, position: Position):
        """Close a position and record the trade."""
        # Get current price
        market = self.active_markets.get(position.market_id)
        if market:
            current_price = (
                market.yes_price if position.side == Side.YES
                else market.no_price
            )
        else:
            current_price = position.current_price

        # Place sell order
        order = await self.polymarket.place_order(
            market_id=position.market_id,
            side=position.side,
            quantity=position.quantity,
            order_type=OrderType.MARKET
        )

        if order.is_filled:
            # Close in risk manager and record trade
            trade = self.risk_manager.close_position(
                position.id, order.filled_price
            )
            if trade:
                self.analytics.record_trade(trade)
                logger.info(
                    f"Position closed: {position.market_id} "
                    f"P&L: ${trade.profit:.2f} ({trade.profit_percent:.1f}%)"
                )

    # ==================== Utility Methods ====================

    def _should_scan_markets(self) -> bool:
        """Check if we should scan for new markets."""
        if self.last_market_scan is None:
            return True
        elapsed = (datetime.utcnow() - self.last_market_scan).total_seconds()
        return elapsed > 300  # Scan every 5 minutes

    def _should_take_snapshot(self) -> bool:
        """Check if we should take a portfolio snapshot."""
        elapsed = (datetime.utcnow() - self.risk_manager.last_snapshot_time).total_seconds()
        return elapsed > 60  # Snapshot every minute

    def get_status(self) -> dict:
        """Get comprehensive bot status."""
        return {
            "running": self.running,
            "risk": self.risk_manager.get_status(),
            "analytics": self.analytics.get_summary(),
            "positions": {
                "market_maker": len(self.market_maker.paired_positions),
                "trend_follower": len(self.trend_follower.trend_positions),
                "discount_hunter": len(self.discount_hunter.discount_positions),
            },
            "active_markets": len(self.active_markets),
        }

    def generate_report(self) -> str:
        """Generate performance report."""
        return self.analytics.generate_report()
