"""
Risk Management Framework

Monitors portfolio exposure, drawdown, and implements
safety controls to protect capital.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .config import RiskConfig
from .models import Position, Trade, PortfolioSnapshot

logger = logging.getLogger(__name__)


@dataclass
class RiskAlert:
    """Risk management alert."""
    level: str  # "warning", "critical", "emergency"
    message: str
    action: str  # Recommended action
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DailyPnL:
    """Daily profit/loss tracking."""
    date: datetime
    starting_capital: float
    current_capital: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_count: int = 0
    wins: int = 0
    losses: int = 0

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def pnl_percent(self) -> float:
        if self.starting_capital == 0:
            return 0.0
        return (self.total_pnl / self.starting_capital) * 100


class RiskManager:
    """
    Risk Management System

    Responsibilities:
    1. Monitor portfolio exposure
    2. Track drawdown levels
    3. Enforce position limits
    4. Implement emergency controls (kill switch)
    5. Calculate position sizing
    6. Track daily P&L
    """

    def __init__(self, config: RiskConfig, initial_capital: float):
        self.config = config
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.peak_capital = initial_capital

        self.positions: dict[str, Position] = {}
        self.trade_history: list[Trade] = []
        self.alerts: list[RiskAlert] = []
        self.snapshots: list[PortfolioSnapshot] = []

        # Daily tracking
        self.daily_pnl = DailyPnL(
            date=datetime.utcnow().date(),
            starting_capital=initial_capital,
            current_capital=initial_capital
        )

        # Kill switch state
        self.kill_switch_active = False
        self.consecutive_losses = 0

        # Trading state
        self.trading_enabled = True
        self.last_snapshot_time = datetime.utcnow()

    # ==================== Position Management ====================

    def can_open_position(self, market_id: str, position_value: float) -> tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            market_id: Market identifier
            position_value: Value of proposed position

        Returns:
            Tuple of (allowed, reason)
        """
        # Check kill switch
        if self.kill_switch_active:
            return False, "Kill switch is active"

        # Check if trading is enabled
        if not self.trading_enabled:
            return False, "Trading is disabled"

        # Check maximum positions
        if len(self.positions) >= self.config.max_positions:
            return False, f"Maximum positions ({self.config.max_positions}) reached"

        # Check single market exposure
        market_exposure = position_value / self.current_capital
        if market_exposure > self.config.max_single_market_exposure:
            return False, f"Position exceeds max market exposure ({self.config.max_single_market_exposure:.0%})"

        # Check total portfolio exposure
        total_exposure = self._calculate_total_exposure()
        if total_exposure + market_exposure > 0.70:  # Max 70% invested
            return False, f"Would exceed maximum portfolio exposure"

        # Check daily loss limit
        if self.daily_pnl.pnl_percent <= -self.config.daily_loss_limit * 100:
            return False, "Daily loss limit reached"

        return True, "Position allowed"

    def register_position(self, position: Position):
        """Register a new position."""
        self.positions[position.id] = position
        logger.info(f"Position registered: {position.id} in {position.market_id}")

    def update_position(self, position: Position):
        """Update an existing position."""
        if position.id in self.positions:
            self.positions[position.id] = position

    def close_position(self, position_id: str, exit_price: float) -> Optional[Trade]:
        """
        Close a position and record the trade.

        Args:
            position_id: Position to close
            exit_price: Exit price

        Returns:
            Completed Trade object
        """
        position = self.positions.get(position_id)
        if not position:
            return None

        # Create trade record
        trade = Trade(
            market_id=position.market_id,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            profit=position.quantity * (exit_price - position.entry_price),
            profit_percent=((exit_price - position.entry_price) / position.entry_price) * 100,
            strategy=position.strategy,
            entry_time=position.created_at,
            exit_time=datetime.utcnow(),
        )
        trade.holding_period = (trade.exit_time - trade.entry_time).total_seconds()

        # Update tracking
        self.trade_history.append(trade)
        self._update_daily_pnl(trade)
        self._update_consecutive_losses(trade)

        # Remove position
        del self.positions[position_id]

        logger.info(
            f"Position closed: {position_id}, "
            f"P&L: ${trade.profit:.2f} ({trade.profit_percent:.1f}%)"
        )

        return trade

    # ==================== Risk Calculations ====================

    def _calculate_total_exposure(self) -> float:
        """Calculate total portfolio exposure as percentage of capital."""
        if self.current_capital == 0:
            return 1.0

        total_invested = sum(p.cost_basis for p in self.positions.values())
        return total_invested / self.current_capital

    def calculate_drawdown(self) -> float:
        """
        Calculate current drawdown from peak.

        Returns:
            Drawdown as decimal (0.15 = 15% drawdown)
        """
        if self.peak_capital == 0:
            return 0.0

        current_value = self.current_capital + sum(
            p.unrealized_pnl for p in self.positions.values()
        )

        drawdown = (self.peak_capital - current_value) / self.peak_capital
        return max(0, drawdown)

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        risk_percent: Optional[float] = None
    ) -> float:
        """
        Calculate appropriate position size based on risk.

        Args:
            entry_price: Proposed entry price
            stop_loss_price: Stop loss price (optional)
            risk_percent: Risk per trade as decimal (optional)

        Returns:
            Number of shares to buy
        """
        if risk_percent is None:
            risk_percent = 0.05  # Default 5%

        risk_amount = self.current_capital * risk_percent

        if stop_loss_price and stop_loss_price < entry_price:
            # Risk per share = entry - stop loss
            risk_per_share = entry_price - stop_loss_price
            position_size = risk_amount / risk_per_share
        else:
            # Simple calculation: risk_amount / entry_price
            position_size = risk_amount / entry_price if entry_price > 0 else 0

        return position_size

    # ==================== Monitoring ====================

    def check_risk_levels(self) -> list[RiskAlert]:
        """
        Check all risk levels and generate alerts.

        Returns:
            List of risk alerts
        """
        alerts = []

        # Check drawdown
        drawdown = self.calculate_drawdown()
        if drawdown >= self.config.max_portfolio_drawdown:
            alerts.append(RiskAlert(
                level="emergency",
                message=f"Maximum drawdown exceeded: {drawdown:.1%}",
                action="Activate kill switch"
            ))
            self._activate_kill_switch("Max drawdown exceeded")
        elif drawdown >= self.config.max_portfolio_drawdown * 0.8:
            alerts.append(RiskAlert(
                level="critical",
                message=f"Approaching max drawdown: {drawdown:.1%}",
                action="Reduce position sizes"
            ))
        elif drawdown >= self.config.max_portfolio_drawdown * 0.5:
            alerts.append(RiskAlert(
                level="warning",
                message=f"Elevated drawdown: {drawdown:.1%}",
                action="Monitor closely"
            ))

        # Check daily loss limit
        if self.daily_pnl.pnl_percent <= -self.config.daily_loss_limit * 100:
            alerts.append(RiskAlert(
                level="critical",
                message=f"Daily loss limit reached: {self.daily_pnl.pnl_percent:.1f}%",
                action="Stop trading for the day"
            ))
            self.trading_enabled = False

        # Check consecutive losses
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            alerts.append(RiskAlert(
                level="warning",
                message=f"Consecutive losses: {self.consecutive_losses}",
                action="Review strategy"
            ))

        # Check position-level stop losses
        for position in self.positions.values():
            if position.should_stop_loss(self.config.position_stop_loss):
                alerts.append(RiskAlert(
                    level="critical",
                    message=f"Stop loss triggered for {position.market_id}",
                    action=f"Close position {position.id}"
                ))

        self.alerts.extend(alerts)
        return alerts

    def get_positions_to_close(self) -> list[Position]:
        """
        Get list of positions that should be closed due to risk rules.

        Returns:
            List of positions to close
        """
        to_close = []

        for position in self.positions.values():
            # Check stop loss
            if position.should_stop_loss(self.config.position_stop_loss):
                to_close.append(position)
                continue

        return to_close

    # ==================== Kill Switch ====================

    def _activate_kill_switch(self, reason: str):
        """Activate emergency kill switch."""
        if not self.config.enable_kill_switch:
            logger.warning(f"Kill switch disabled, but would activate: {reason}")
            return

        self.kill_switch_active = True
        self.trading_enabled = False

        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        self.alerts.append(RiskAlert(
            level="emergency",
            message=f"Kill switch activated: {reason}",
            action="Close all positions immediately"
        ))

    def deactivate_kill_switch(self):
        """Manually deactivate kill switch."""
        self.kill_switch_active = False
        logger.info("Kill switch deactivated")

    def enable_trading(self):
        """Re-enable trading after being disabled."""
        if not self.kill_switch_active:
            self.trading_enabled = True
            logger.info("Trading re-enabled")

    # ==================== Tracking ====================

    def _update_daily_pnl(self, trade: Trade):
        """Update daily P&L after a trade."""
        self.daily_pnl.realized_pnl += trade.profit
        self.daily_pnl.trades_count += 1

        if trade.is_winner:
            self.daily_pnl.wins += 1
        else:
            self.daily_pnl.losses += 1

        self.current_capital += trade.profit
        self.daily_pnl.current_capital = self.current_capital

        # Update peak capital
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital

    def _update_consecutive_losses(self, trade: Trade):
        """Track consecutive losses."""
        if trade.is_winner:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    def reset_daily_tracking(self):
        """Reset daily tracking (call at start of new day)."""
        self.daily_pnl = DailyPnL(
            date=datetime.utcnow().date(),
            starting_capital=self.current_capital,
            current_capital=self.current_capital
        )
        self.trading_enabled = True
        self.consecutive_losses = 0
        logger.info("Daily tracking reset")

    def take_snapshot(self) -> PortfolioSnapshot:
        """
        Take a snapshot of current portfolio state.

        Returns:
            PortfolioSnapshot object
        """
        unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        invested = sum(p.cost_basis for p in self.positions.values())

        snapshot = PortfolioSnapshot(
            timestamp=datetime.utcnow(),
            total_capital=self.current_capital + unrealized_pnl,
            available_capital=self.current_capital - invested,
            invested_capital=invested,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=self.daily_pnl.realized_pnl,
            total_positions=len(self.positions),
            daily_pnl=self.daily_pnl.total_pnl,
            drawdown=self.calculate_drawdown(),
        )

        self.snapshots.append(snapshot)
        self.last_snapshot_time = datetime.utcnow()

        return snapshot

    def get_status(self) -> dict:
        """
        Get comprehensive risk management status.

        Returns:
            Status dictionary
        """
        return {
            "capital": {
                "initial": self.initial_capital,
                "current": self.current_capital,
                "peak": self.peak_capital,
            },
            "exposure": {
                "total_positions": len(self.positions),
                "max_positions": self.config.max_positions,
                "exposure_percent": self._calculate_total_exposure() * 100,
            },
            "risk": {
                "drawdown": self.calculate_drawdown() * 100,
                "max_drawdown": self.config.max_portfolio_drawdown * 100,
                "consecutive_losses": self.consecutive_losses,
            },
            "daily": {
                "pnl": self.daily_pnl.total_pnl,
                "pnl_percent": self.daily_pnl.pnl_percent,
                "trades": self.daily_pnl.trades_count,
                "win_rate": (
                    self.daily_pnl.wins / self.daily_pnl.trades_count * 100
                    if self.daily_pnl.trades_count > 0 else 0
                ),
            },
            "controls": {
                "trading_enabled": self.trading_enabled,
                "kill_switch_active": self.kill_switch_active,
            },
            "alerts": [
                {"level": a.level, "message": a.message}
                for a in self.alerts[-5:]  # Last 5 alerts
            ],
        }
