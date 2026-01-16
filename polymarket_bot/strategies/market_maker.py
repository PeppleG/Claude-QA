"""
Phase 1: Market Making Strategy

Enters both sides of new markets when spreads are wide,
capturing spread profits with minimal directional risk.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .base import BaseStrategy, StrategySignal
from ..models import Market, Position, Side, Strategy
from ..config import TradingConfig

logger = logging.getLogger(__name__)


@dataclass
class MarketMakerPosition:
    """Tracks paired Yes/No positions for market making."""
    market_id: str
    yes_position: Optional[Position] = None
    no_position: Optional[Position] = None
    entry_time: datetime = None
    total_invested: float = 0.0

    @property
    def is_complete(self) -> bool:
        """Check if both sides are filled."""
        return self.yes_position is not None and self.no_position is not None

    @property
    def current_pnl(self) -> float:
        """Calculate current P&L from both positions."""
        pnl = 0.0
        if self.yes_position:
            pnl += self.yes_position.unrealized_pnl
        if self.no_position:
            pnl += self.no_position.unrealized_pnl
        return pnl


class MarketMakerStrategy(BaseStrategy):
    """
    Market Making Strategy (Phase 1)

    Strategy:
    - Enter new Bitcoin prediction markets early
    - Buy BOTH "Yes" AND "No" positions simultaneously
    - Capture spread profits with minimal directional risk

    Entry Conditions:
    - New market (launched within configurable hours)
    - High uncertainty (wide bid-ask spreads > threshold)
    - Sufficient liquidity for entry
    - Bitcoin-related market

    Exit Conditions:
    - Spread narrows below profitable threshold
    - Clear directional trend emerges (hand off to Phase 2)
    - Position holding time exceeds maximum
    """

    name = "market_maker"
    strategy_type = Strategy.MARKET_MAKER

    def __init__(self, config: TradingConfig):
        super().__init__(config)
        self.paired_positions: dict[str, MarketMakerPosition] = {}
        self.min_spread = config.spread_threshold
        self.allocation_split = config.market_maker_allocation

    async def analyze(self, market: Market) -> Optional[StrategySignal]:
        """
        Analyze market for market-making opportunity.

        Args:
            market: Market to analyze

        Returns:
            StrategySignal if opportunity found
        """
        # Check if we already have a position in this market
        existing = self.paired_positions.get(market.id)

        if existing:
            # Check if we should exit
            if self._should_exit_market_maker(existing, market):
                return StrategySignal(
                    market_id=market.id,
                    action="exit_both",
                    confidence=0.8,
                    reason="Spread narrowed or trend emerged"
                )
            return None

        # Check entry conditions
        if self.should_enter(market):
            return StrategySignal(
                market_id=market.id,
                action="enter_both_sides",
                confidence=self._calculate_confidence(market),
                reason=f"Wide spread ({market.spread:.2%}) in new Bitcoin market"
            )

        return None

    def should_enter(self, market: Market) -> bool:
        """
        Check if market meets entry criteria for market making.

        Criteria:
        1. Bitcoin-related market
        2. Wide bid-ask spread (> threshold)
        3. Sufficient volume/liquidity
        4. Not already in position
        """
        # Skip if already in this market
        if market.id in self.paired_positions:
            return False

        # Must be Bitcoin-related
        if not market.is_bitcoin_related:
            logger.debug(f"Skipping {market.id}: not Bitcoin-related")
            return False

        # Check spread width
        if market.spread < self.min_spread:
            logger.debug(f"Skipping {market.id}: spread too narrow ({market.spread:.2%})")
            return False

        # Check minimum volume
        if market.volume < self.config.min_market_volume:
            logger.debug(f"Skipping {market.id}: volume too low ({market.volume})")
            return False

        # Check market is active
        if not market.is_active:
            logger.debug(f"Skipping {market.id}: market not active")
            return False

        logger.info(
            f"Market {market.id} meets entry criteria: "
            f"spread={market.spread:.2%}, volume={market.volume}"
        )
        return True

    def should_exit(self, position: Position, market: Market) -> bool:
        """
        Check if should exit position.

        For market making, we check the paired position.
        """
        paired = self.paired_positions.get(market.id)
        if not paired:
            return False

        return self._should_exit_market_maker(paired, market)

    def _should_exit_market_maker(
        self,
        paired: MarketMakerPosition,
        market: Market
    ) -> bool:
        """
        Determine if market-maker position should be exited.

        Exit when:
        1. Spread narrows below profitable threshold
        2. Clear directional trend (one side moving strongly)
        3. Maximum holding time exceeded
        """
        # Check spread narrowing
        if market.spread < self.min_spread * 0.5:
            logger.info(f"Exit signal: spread narrowed to {market.spread:.2%}")
            return True

        # Check for directional trend (hand off to Phase 2)
        if self._detect_trend(paired, market):
            logger.info(f"Exit signal: trend detected in {market.id}")
            return True

        # Check holding time
        if paired.entry_time:
            holding_time = (datetime.utcnow() - paired.entry_time).total_seconds()
            max_hold = 3600  # 1 hour default
            if holding_time > max_hold:
                logger.info(f"Exit signal: max holding time exceeded")
                return True

        return False

    def _detect_trend(self, paired: MarketMakerPosition, market: Market) -> bool:
        """
        Detect if a clear trend has emerged.

        A trend is detected when one side is significantly winning.
        """
        if not paired.is_complete:
            return False

        yes_pnl = paired.yes_position.unrealized_pnl_percent if paired.yes_position else 0
        no_pnl = paired.no_position.unrealized_pnl_percent if paired.no_position else 0

        # If one side is up significantly while other is down
        trend_threshold = 20  # 20% divergence
        if abs(yes_pnl - no_pnl) > trend_threshold:
            return True

        # If prices moved significantly from 50/50
        price_divergence = abs(market.yes_price - 0.5)
        if price_divergence > 0.15:  # More than 15% from 50/50
            return True

        return False

    def _calculate_confidence(self, market: Market) -> float:
        """
        Calculate confidence score for entering this market.

        Higher confidence for:
        - Wider spreads
        - Higher volume
        - Newer markets
        """
        confidence = 0.5  # Base confidence

        # Wider spread = higher confidence
        spread_bonus = min(market.spread / 0.20, 0.25)  # Max 0.25 bonus
        confidence += spread_bonus

        # Higher volume = higher confidence
        if market.volume > 50000:
            confidence += 0.15
        elif market.volume > 20000:
            confidence += 0.10

        return min(confidence, 1.0)

    def calculate_entry_amounts(self, capital: float, market: Market) -> tuple[float, float]:
        """
        Calculate entry amounts for both sides.

        Args:
            capital: Total capital to allocate
            market: Target market

        Returns:
            Tuple of (yes_quantity, no_quantity)
        """
        # Apply position limits
        max_allocation = capital * self.config.max_position_percent
        allocation = min(capital * self.allocation_split, max_allocation)

        # Split evenly between Yes and No
        half_allocation = allocation / 2

        # Calculate quantities based on current prices
        yes_quantity = half_allocation / market.yes_price if market.yes_price > 0 else 0
        no_quantity = half_allocation / market.no_price if market.no_price > 0 else 0

        return yes_quantity, no_quantity

    def register_entry(
        self,
        market_id: str,
        yes_position: Position,
        no_position: Position
    ):
        """
        Register a new market-maker position.

        Args:
            market_id: Market identifier
            yes_position: Yes side position
            no_position: No side position
        """
        paired = MarketMakerPosition(
            market_id=market_id,
            yes_position=yes_position,
            no_position=no_position,
            entry_time=datetime.utcnow(),
            total_invested=yes_position.cost_basis + no_position.cost_basis
        )
        self.paired_positions[market_id] = paired
        logger.info(
            f"Registered market-maker position in {market_id}: "
            f"invested ${paired.total_invested:.2f}"
        )

    def get_winning_side(self, market_id: str) -> Optional[Side]:
        """
        Determine which side is winning for handoff to Phase 2.

        Args:
            market_id: Market identifier

        Returns:
            Winning Side or None if no clear winner
        """
        paired = self.paired_positions.get(market_id)
        if not paired or not paired.is_complete:
            return None

        yes_pnl = paired.yes_position.unrealized_pnl
        no_pnl = paired.no_position.unrealized_pnl

        if yes_pnl > no_pnl:
            return Side.YES
        elif no_pnl > yes_pnl:
            return Side.NO
        return None

    def get_losing_position(self, market_id: str) -> Optional[Position]:
        """
        Get the losing position for exit.

        Args:
            market_id: Market identifier

        Returns:
            Losing Position or None
        """
        paired = self.paired_positions.get(market_id)
        if not paired or not paired.is_complete:
            return None

        winning_side = self.get_winning_side(market_id)
        if winning_side == Side.YES:
            return paired.no_position
        elif winning_side == Side.NO:
            return paired.yes_position
        return None
