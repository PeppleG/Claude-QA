"""
Data models for the Polymarket Trading Bot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class Side(Enum):
    """Trading side enumeration."""
    YES = "yes"
    NO = "no"


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionStatus(Enum):
    """Position status enumeration."""
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class Strategy(Enum):
    """Trading strategy enumeration."""
    MARKET_MAKER = "market_maker"
    TREND_FOLLOWER = "trend_follower"
    DISCOUNT_HUNTER = "discount_hunter"


@dataclass
class Market:
    """Represents a Polymarket prediction market."""
    id: str
    question: str
    description: str = ""
    end_date: Optional[datetime] = None
    volume: float = 0.0
    liquidity: float = 0.0
    yes_price: float = 0.5
    no_price: float = 0.5
    yes_bid: float = 0.0
    yes_ask: float = 0.0
    no_bid: float = 0.0
    no_ask: float = 0.0
    is_active: bool = True
    is_bitcoin_related: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def spread(self) -> float:
        """Calculate the bid-ask spread."""
        yes_spread = self.yes_ask - self.yes_bid if self.yes_ask > 0 else 0
        no_spread = self.no_ask - self.no_bid if self.no_ask > 0 else 0
        return max(yes_spread, no_spread)

    @property
    def mid_price_yes(self) -> float:
        """Calculate mid price for Yes side."""
        if self.yes_bid > 0 and self.yes_ask > 0:
            return (self.yes_bid + self.yes_ask) / 2
        return self.yes_price

    @property
    def mid_price_no(self) -> float:
        """Calculate mid price for No side."""
        if self.no_bid > 0 and self.no_ask > 0:
            return (self.no_bid + self.no_ask) / 2
        return self.no_price

    def has_discount_opportunity(self, threshold: float = 0.05) -> bool:
        """Check if there's a discount opportunity."""
        return self.yes_price <= threshold or self.no_price <= threshold


@dataclass
class Order:
    """Represents a trading order."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    market_id: str = ""
    side: Side = Side.YES
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: Optional[float] = None
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    strategy: Strategy = Strategy.MARKET_MAKER
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def remaining_quantity(self) -> float:
        """Calculate remaining unfilled quantity."""
        return self.quantity - self.filled_quantity


@dataclass
class Position:
    """Represents an open position."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    market_id: str = ""
    side: Side = Side.YES
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    strategy: Strategy = Strategy.MARKET_MAKER
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def cost_basis(self) -> float:
        """Calculate total cost basis."""
        return self.quantity * self.entry_price

    @property
    def current_value(self) -> float:
        """Calculate current position value."""
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized profit/loss."""
        return self.current_value - self.cost_basis

    @property
    def unrealized_pnl_percent(self) -> float:
        """Calculate unrealized P&L as percentage."""
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100

    @property
    def is_profitable(self) -> bool:
        """Check if position is currently profitable."""
        return self.unrealized_pnl > 0

    def should_stop_loss(self, threshold: float = 0.30) -> bool:
        """Check if position should be stopped out."""
        return self.unrealized_pnl_percent <= -threshold * 100


@dataclass
class Trade:
    """Represents a completed trade."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    market_id: str = ""
    side: Side = Side.YES
    quantity: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    profit: float = 0.0
    profit_percent: float = 0.0
    strategy: Strategy = Strategy.MARKET_MAKER
    entry_time: datetime = field(default_factory=datetime.utcnow)
    exit_time: datetime = field(default_factory=datetime.utcnow)
    holding_period: float = 0.0  # seconds

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.profit > 0


@dataclass
class PriceData:
    """Represents price data point."""
    timestamp: datetime
    price: float
    volume: float = 0.0
    side: Side = Side.YES


@dataclass
class MomentumData:
    """Represents momentum analysis data."""
    market_id: str
    yes_momentum: float = 0.0  # Price velocity for Yes
    no_momentum: float = 0.0  # Price velocity for No
    direction: Optional[Side] = None  # Winning side
    confidence: float = 0.0  # 0-1 confidence score
    price_history: list = field(default_factory=list)


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    total_capital: float = 0.0
    available_capital: float = 0.0
    invested_capital: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_positions: int = 0
    daily_pnl: float = 0.0
    drawdown: float = 0.0


@dataclass
class PerformanceMetrics:
    """Trading performance metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_profit: float = 0.0
    total_loss: float = 0.0
    net_profit: float = 0.0
    average_profit: float = 0.0
    average_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    average_holding_period: float = 0.0
