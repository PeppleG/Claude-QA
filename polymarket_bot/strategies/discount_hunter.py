"""
Phase 3: Discount Hunting Strategy (Major Profit Driver)

Scans for and accumulates heavily discounted positions ($0.01-$0.03)
during volatility spikes for massive upside potential.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .base import BaseStrategy, StrategySignal
from ..models import Market, Position, Side, Strategy
from ..config import TradingConfig

logger = logging.getLogger(__name__)


@dataclass
class DiscountOpportunity:
    """Represents a discount buying opportunity."""
    market_id: str
    side: Side
    price: float
    potential_return: float  # e.g., 30x
    risk_amount: float  # Total $ at risk
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio."""
        return self.potential_return


@dataclass
class DiscountPosition:
    """Tracks a discount hunting position."""
    market_id: str
    side: Side
    position: Position
    entry_price: float
    target_prices: list[float] = field(default_factory=list)  # Scale-out targets
    entry_time: datetime = field(default_factory=datetime.utcnow)


class DiscountHunterStrategy(BaseStrategy):
    """
    Discount Hunting Strategy (Phase 3) - MAJOR PROFIT DRIVER

    Strategy:
    - Continuously scan all markets for extreme discounts
    - Aggressively accumulate positions at $0.01-$0.03
    - Minimal risk per share, massive upside (30x+)

    Entry Conditions:
    - Price drops below extreme discount threshold ($0.03)
    - Sharp volatility spike created the discount
    - Market still has resolution potential (not settled)

    Exit Conditions:
    - Price recovers to target levels (10x-30x return)
    - Scale out at multiple profit targets
    - Time-based exit if no recovery

    Example:
    - "Yes" crashes from $0.50 → $0.02 during panic
    - Buy 5,000 shares @ $0.02 = $100 total risk
    - Price recovers to $0.60 = $2,900 profit (29x return)
    """

    name = "discount_hunter"
    strategy_type = Strategy.DISCOUNT_HUNTER

    def __init__(self, config: TradingConfig):
        super().__init__(config)
        self.discount_positions: dict[str, DiscountPosition] = {}
        self.opportunities: list[DiscountOpportunity] = []

        # Configuration
        self.alert_threshold = config.discount_threshold  # $0.05
        self.extreme_threshold = config.extreme_discount_threshold  # $0.03
        self.min_price = config.min_discount_price  # $0.01
        self.max_price = config.max_discount_price  # $0.03

        # Profit targets (multiples of entry)
        self.profit_targets = [10, 20, 30]  # 10x, 20x, 30x

    async def analyze(self, market: Market) -> Optional[StrategySignal]:
        """
        Analyze market for discount opportunities.

        Args:
            market: Market to analyze

        Returns:
            StrategySignal if discount opportunity found
        """
        # Check existing position
        existing = self.discount_positions.get(market.id)

        if existing:
            # Check for exit (profit target)
            signal = self._check_profit_targets(existing, market)
            if signal:
                return signal
            return None

        # Scan for new discount opportunities
        opportunity = self._scan_for_discount(market)
        if opportunity:
            self.opportunities.append(opportunity)
            return StrategySignal(
                market_id=market.id,
                action=f"buy_{opportunity.side.value}",
                price=opportunity.price,
                confidence=self._calculate_confidence(opportunity),
                reason=f"Extreme discount: ${opportunity.price:.3f} ({opportunity.potential_return:.0f}x potential)"
            )

        return None

    def should_enter(self, market: Market) -> bool:
        """
        Check if market has a discount opportunity.

        Criteria:
        1. Price in extreme discount range ($0.01-$0.03)
        2. Market is still active
        3. Not already in position
        """
        if market.id in self.discount_positions:
            return False

        if not market.is_active:
            return False

        # Check for discount on either side
        return (
            self._is_extreme_discount(market.yes_price) or
            self._is_extreme_discount(market.no_price)
        )

    def should_exit(self, position: Position, market: Market) -> bool:
        """Check if discount position should be exited."""
        discount_pos = self.discount_positions.get(market.id)
        if not discount_pos:
            return False

        # Check profit targets
        current_return = position.current_price / position.entry_price
        return current_return >= self.profit_targets[0]  # Exit at first target

    def _is_extreme_discount(self, price: float) -> bool:
        """Check if price is in extreme discount range."""
        return self.min_price <= price <= self.max_price

    def _is_discount_alert(self, price: float) -> bool:
        """Check if price warrants an alert."""
        return price <= self.alert_threshold

    def _scan_for_discount(self, market: Market) -> Optional[DiscountOpportunity]:
        """
        Scan market for discount opportunity.

        Returns:
            DiscountOpportunity if found, None otherwise
        """
        # Check Yes side
        if self._is_extreme_discount(market.yes_price):
            potential_return = 0.50 / market.yes_price  # Assume recovery to $0.50
            return DiscountOpportunity(
                market_id=market.id,
                side=Side.YES,
                price=market.yes_price,
                potential_return=potential_return,
                risk_amount=market.yes_price,  # Per share risk
            )

        # Check No side
        if self._is_extreme_discount(market.no_price):
            potential_return = 0.50 / market.no_price
            return DiscountOpportunity(
                market_id=market.id,
                side=Side.NO,
                price=market.no_price,
                potential_return=potential_return,
                risk_amount=market.no_price,
            )

        return None

    def _calculate_confidence(self, opportunity: DiscountOpportunity) -> float:
        """
        Calculate confidence score for discount opportunity.

        Higher confidence for:
        - Lower prices (more asymmetric risk/reward)
        - Higher potential returns
        """
        confidence = 0.5  # Base confidence

        # Lower price = higher confidence
        if opportunity.price <= 0.01:
            confidence += 0.3
        elif opportunity.price <= 0.02:
            confidence += 0.2
        elif opportunity.price <= 0.03:
            confidence += 0.1

        # Higher potential return = higher confidence
        if opportunity.potential_return >= 30:
            confidence += 0.15
        elif opportunity.potential_return >= 20:
            confidence += 0.10

        return min(confidence, 1.0)

    def _check_profit_targets(
        self,
        discount_pos: DiscountPosition,
        market: Market
    ) -> Optional[StrategySignal]:
        """
        Check if any profit targets have been hit.

        Returns signal to sell portion of position at each target.
        """
        position = discount_pos.position
        entry_price = discount_pos.entry_price

        # Get current price for our side
        current_price = (
            market.yes_price if discount_pos.side == Side.YES
            else market.no_price
        )

        # Calculate current return multiple
        current_return = current_price / entry_price if entry_price > 0 else 0

        # Check each profit target
        for i, target in enumerate(self.profit_targets):
            if current_return >= target:
                # Calculate portion to sell (1/3 at each target)
                sell_portion = position.quantity / (len(self.profit_targets) - i)

                logger.info(
                    f"Profit target hit for {market.id}: "
                    f"{current_return:.1f}x return (target: {target}x)"
                )

                return StrategySignal(
                    market_id=market.id,
                    action=f"sell_{discount_pos.side.value}",
                    quantity=sell_portion,
                    confidence=0.95,
                    reason=f"Profit target {target}x reached ({current_return:.1f}x actual)"
                )

        return None

    def calculate_position_size(
        self,
        capital: float,
        price: float,
        max_risk: Optional[float] = None
    ) -> float:
        """
        Calculate position size for discount entry.

        For discounts, we want to maximize shares while limiting total risk.

        Args:
            capital: Available capital
            price: Entry price
            max_risk: Maximum $ to risk (default 5% of capital)

        Returns:
            Number of shares to buy
        """
        if max_risk is None:
            max_risk = capital * 0.05  # 5% max risk

        # Number of shares we can buy with max_risk
        shares = max_risk / price if price > 0 else 0

        logger.info(
            f"Discount position size: {shares:.0f} shares @ ${price:.3f} "
            f"(total risk: ${shares * price:.2f})"
        )

        return shares

    def register_position(
        self,
        market_id: str,
        side: Side,
        position: Position,
        entry_price: float
    ):
        """
        Register a new discount position.

        Args:
            market_id: Market identifier
            side: Position side
            position: Position object
            entry_price: Entry price
        """
        # Calculate profit target prices
        target_prices = [entry_price * target for target in self.profit_targets]

        discount_pos = DiscountPosition(
            market_id=market_id,
            side=side,
            position=position,
            entry_price=entry_price,
            target_prices=target_prices,
            entry_time=datetime.utcnow()
        )

        self.discount_positions[market_id] = discount_pos
        self.add_position(position)

        logger.info(
            f"Registered discount position: {side.value} in {market_id} "
            f"@ ${entry_price:.3f}, targets: {target_prices}"
        )

    def get_all_opportunities(
        self,
        min_return: float = 10.0
    ) -> list[DiscountOpportunity]:
        """
        Get all current discount opportunities.

        Args:
            min_return: Minimum potential return multiple

        Returns:
            List of opportunities sorted by potential return
        """
        filtered = [
            opp for opp in self.opportunities
            if opp.potential_return >= min_return
        ]
        return sorted(filtered, key=lambda x: x.potential_return, reverse=True)

    def get_position_status(self, market_id: str) -> Optional[dict]:
        """
        Get detailed status of a discount position.

        Args:
            market_id: Market identifier

        Returns:
            Status dictionary or None
        """
        discount_pos = self.discount_positions.get(market_id)
        if not discount_pos:
            return None

        position = discount_pos.position
        current_return = position.current_price / discount_pos.entry_price

        return {
            "market_id": market_id,
            "side": discount_pos.side.value,
            "entry_price": discount_pos.entry_price,
            "current_price": position.current_price,
            "quantity": position.quantity,
            "cost_basis": position.cost_basis,
            "current_value": position.current_value,
            "unrealized_pnl": position.unrealized_pnl,
            "return_multiple": current_return,
            "target_prices": discount_pos.target_prices,
            "entry_time": discount_pos.entry_time.isoformat(),
        }
