"""
Phase 2: Trend Following Strategy

Monitors position momentum, abandons losers,
and reallocates capital to winning positions.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .base import BaseStrategy, StrategySignal
from ..models import Market, Position, Side, Strategy, MomentumData
from ..config import TradingConfig

logger = logging.getLogger(__name__)


@dataclass
class PricePoint:
    """Single price observation."""
    timestamp: datetime
    yes_price: float
    no_price: float


@dataclass
class TrendPosition:
    """Tracks a trend-following position."""
    market_id: str
    side: Side
    position: Position
    entry_time: datetime = field(default_factory=datetime.utcnow)
    scale_ins: int = 0  # Number of times we've scaled in
    max_scale_ins: int = 3  # Maximum scale-in attempts


class TrendFollowerStrategy(BaseStrategy):
    """
    Trend Following Strategy (Phase 2)

    Strategy:
    - Monitor momentum of positions
    - Identify winning vs losing sides
    - Sell/abandon losing positions
    - Reallocate 100% capital to winning side
    - Scale into winners as confidence builds

    Entry Conditions:
    - Clear directional price movement
    - Volume confirms trend
    - Momentum sustained over multiple periods

    Exit Conditions:
    - Trend reversal detected
    - Stop loss triggered
    - Profit target reached
    """

    name = "trend_follower"
    strategy_type = Strategy.TREND_FOLLOWER

    def __init__(self, config: TradingConfig):
        super().__init__(config)
        self.trend_positions: dict[str, TrendPosition] = {}
        self.price_history: dict[str, deque] = {}  # market_id -> price history
        self.momentum_data: dict[str, MomentumData] = {}

        # Configuration
        self.check_interval = config.momentum_check_interval
        self.momentum_threshold = config.momentum_threshold
        self.confirmation_periods = config.trend_confirmation_periods
        self.history_size = 20  # Keep last 20 price points

    async def analyze(self, market: Market) -> Optional[StrategySignal]:
        """
        Analyze market for trend-following opportunities.

        Args:
            market: Market to analyze

        Returns:
            StrategySignal if action needed
        """
        # Update price history
        self._update_price_history(market)

        # Calculate momentum
        momentum = self._calculate_momentum(market.id)
        if momentum:
            self.momentum_data[market.id] = momentum

        # Check existing position
        existing = self.trend_positions.get(market.id)

        if existing:
            # Check for exit conditions
            if self._should_exit_trend(existing, market, momentum):
                return StrategySignal(
                    market_id=market.id,
                    action=f"sell_{existing.side.value}",
                    quantity=existing.position.quantity,
                    confidence=0.85,
                    reason="Trend reversal or stop-loss triggered"
                )

            # Check for scale-in opportunity
            if self._should_scale_in(existing, market, momentum):
                return StrategySignal(
                    market_id=market.id,
                    action=f"buy_{existing.side.value}",
                    confidence=momentum.confidence if momentum else 0.7,
                    reason="Scaling into winning trend"
                )

            return None

        # Check for new entry
        if momentum and momentum.direction and self.should_enter(market):
            return StrategySignal(
                market_id=market.id,
                action=f"buy_{momentum.direction.value}",
                confidence=momentum.confidence,
                reason=f"Clear {momentum.direction.value} trend detected"
            )

        return None

    def should_enter(self, market: Market) -> bool:
        """
        Check if market meets entry criteria for trend following.

        Criteria:
        1. Clear directional momentum
        2. Sufficient volume
        3. Trend confirmed over multiple periods
        """
        # Must have enough price history
        history = self.price_history.get(market.id)
        if not history or len(history) < self.confirmation_periods:
            return False

        # Must have calculated momentum
        momentum = self.momentum_data.get(market.id)
        if not momentum or not momentum.direction:
            return False

        # Confidence must be above threshold
        if momentum.confidence < 0.6:
            logger.debug(f"Skipping {market.id}: low confidence ({momentum.confidence:.2f})")
            return False

        # Check volume
        if market.volume < self.config.min_market_volume:
            return False

        return True

    def should_exit(self, position: Position, market: Market) -> bool:
        """Check if position should be exited."""
        trend_pos = self.trend_positions.get(market.id)
        if not trend_pos:
            return False

        momentum = self.momentum_data.get(market.id)
        return self._should_exit_trend(trend_pos, market, momentum)

    def _update_price_history(self, market: Market):
        """Update price history for momentum calculation."""
        if market.id not in self.price_history:
            self.price_history[market.id] = deque(maxlen=self.history_size)

        self.price_history[market.id].append(PricePoint(
            timestamp=datetime.utcnow(),
            yes_price=market.yes_price,
            no_price=market.no_price
        ))

    def _calculate_momentum(self, market_id: str) -> Optional[MomentumData]:
        """
        Calculate price momentum for a market.

        Momentum is calculated as the rate of price change
        over recent periods.
        """
        history = self.price_history.get(market_id)
        if not history or len(history) < 2:
            return None

        prices = list(history)

        # Calculate price velocity (change per period)
        yes_changes = []
        no_changes = []

        for i in range(1, len(prices)):
            yes_change = prices[i].yes_price - prices[i-1].yes_price
            no_change = prices[i].no_price - prices[i-1].no_price
            yes_changes.append(yes_change)
            no_changes.append(no_change)

        if not yes_changes:
            return None

        # Average momentum
        yes_momentum = sum(yes_changes) / len(yes_changes)
        no_momentum = sum(no_changes) / len(no_changes)

        # Determine direction
        direction = None
        confidence = 0.0

        yes_total = sum(yes_changes)
        no_total = sum(no_changes)

        # Check if momentum is strong enough
        if abs(yes_total) > self.momentum_threshold:
            if yes_total > 0:
                direction = Side.YES
                confidence = min(yes_total / 0.20, 1.0)  # Cap at 1.0
            else:
                direction = Side.NO
                confidence = min(abs(yes_total) / 0.20, 1.0)

        # Check consistency (how many periods moved in same direction)
        if direction == Side.YES:
            consistent = sum(1 for c in yes_changes if c > 0)
        elif direction == Side.NO:
            consistent = sum(1 for c in yes_changes if c < 0)
        else:
            consistent = 0

        consistency_score = consistent / len(yes_changes) if yes_changes else 0
        confidence *= consistency_score

        return MomentumData(
            market_id=market_id,
            yes_momentum=yes_momentum,
            no_momentum=no_momentum,
            direction=direction,
            confidence=confidence,
            price_history=[(p.timestamp, p.yes_price, p.no_price) for p in prices[-5:]]
        )

    def _should_exit_trend(
        self,
        trend_pos: TrendPosition,
        market: Market,
        momentum: Optional[MomentumData]
    ) -> bool:
        """
        Determine if trend position should be exited.

        Exit conditions:
        1. Trend reversal (momentum now opposite)
        2. Stop loss triggered
        3. Profit target reached
        4. Momentum died (no clear direction)
        """
        position = trend_pos.position

        # Check stop loss
        if position.should_stop_loss(self.config.risk_per_trade * 6):  # 30% stop
            logger.info(f"Stop loss triggered for {market.id}")
            return True

        # Check profit target (30x for discount positions)
        if position.unrealized_pnl_percent > 3000:  # 30x = 3000%
            logger.info(f"Profit target reached for {market.id}")
            return True

        # Check trend reversal
        if momentum and momentum.direction:
            if momentum.direction != trend_pos.side and momentum.confidence > 0.6:
                logger.info(f"Trend reversal detected for {market.id}")
                return True

        # Check momentum death
        if momentum and not momentum.direction and momentum.confidence < 0.3:
            logger.info(f"Momentum died for {market.id}")
            return True

        return False

    def _should_scale_in(
        self,
        trend_pos: TrendPosition,
        market: Market,
        momentum: Optional[MomentumData]
    ) -> bool:
        """
        Determine if we should add to winning position.

        Scale-in conditions:
        1. Position is profitable
        2. Trend still intact
        3. Haven't exceeded max scale-ins
        4. High confidence momentum
        """
        # Check scale-in limit
        if trend_pos.scale_ins >= trend_pos.max_scale_ins:
            return False

        # Position must be profitable
        if not trend_pos.position.is_profitable:
            return False

        # Need minimum profit before scaling
        if trend_pos.position.unrealized_pnl_percent < 10:  # At least 10% profit
            return False

        # Trend must be intact with high confidence
        if not momentum or momentum.direction != trend_pos.side:
            return False

        if momentum.confidence < 0.7:
            return False

        return True

    def register_position(self, market_id: str, side: Side, position: Position):
        """
        Register a new trend-following position.

        Args:
            market_id: Market identifier
            side: Position side (YES/NO)
            position: Position object
        """
        trend_pos = TrendPosition(
            market_id=market_id,
            side=side,
            position=position,
            entry_time=datetime.utcnow()
        )
        self.trend_positions[market_id] = trend_pos
        self.add_position(position)
        logger.info(f"Registered trend position: {side.value} in {market_id}")

    def record_scale_in(self, market_id: str, additional_quantity: float):
        """Record a scale-in to existing position."""
        trend_pos = self.trend_positions.get(market_id)
        if trend_pos:
            trend_pos.scale_ins += 1
            trend_pos.position.quantity += additional_quantity
            logger.info(
                f"Scaled into {market_id}: scale-in #{trend_pos.scale_ins}, "
                f"new quantity: {trend_pos.position.quantity}"
            )

    def handoff_from_market_maker(
        self,
        market_id: str,
        winning_side: Side,
        position: Position
    ):
        """
        Receive handoff from market-maker strategy.

        When Phase 1 detects a trend, it hands off the winning
        position to Phase 2 for trend following.

        Args:
            market_id: Market identifier
            winning_side: The winning side from market making
            position: The winning position to continue
        """
        logger.info(
            f"Handoff from market maker: {winning_side.value} "
            f"in {market_id} (PnL: {position.unrealized_pnl_percent:.1f}%)"
        )
        self.register_position(market_id, winning_side, position)
