"""
Performance Analytics and Metrics

Tracks and calculates trading performance metrics.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import math

from .models import Trade, PerformanceMetrics, Strategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyMetrics:
    """Performance metrics for a specific strategy."""
    strategy: Strategy
    metrics: PerformanceMetrics
    trade_count: int = 0


class Analytics:
    """
    Trading Analytics Engine

    Calculates and tracks:
    - Win rate
    - Average profit/loss
    - Sharpe ratio
    - Maximum drawdown
    - Strategy-specific performance
    """

    def __init__(self):
        self.trades: list[Trade] = []
        self.daily_returns: list[float] = []
        self.equity_curve: list[tuple[datetime, float]] = []
        self.initial_capital: float = 0.0
        self.current_capital: float = 0.0

    def record_trade(self, trade: Trade):
        """Record a completed trade."""
        self.trades.append(trade)
        logger.debug(f"Trade recorded: {trade.id}")

    def set_initial_capital(self, capital: float):
        """Set initial capital for metrics calculation."""
        self.initial_capital = capital
        self.current_capital = capital
        self.equity_curve.append((datetime.utcnow(), capital))

    def update_equity(self, capital: float):
        """Update equity curve."""
        self.current_capital = capital
        self.equity_curve.append((datetime.utcnow(), capital))

    def record_daily_return(self, return_pct: float):
        """Record daily return for Sharpe calculation."""
        self.daily_returns.append(return_pct)

    # ==================== Core Metrics ====================

    def calculate_metrics(
        self,
        trades: Optional[list[Trade]] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Args:
            trades: Trades to analyze (default: all trades)

        Returns:
            PerformanceMetrics object
        """
        if trades is None:
            trades = self.trades

        if not trades:
            return PerformanceMetrics()

        # Basic counts
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.is_winner)
        losing_trades = total_trades - winning_trades

        # Win rate
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # Profit/loss calculations
        profits = [t.profit for t in trades if t.profit > 0]
        losses = [t.profit for t in trades if t.profit < 0]

        total_profit = sum(profits) if profits else 0
        total_loss = abs(sum(losses)) if losses else 0
        net_profit = total_profit - total_loss

        average_profit = total_profit / len(profits) if profits else 0
        average_loss = total_loss / len(losses) if losses else 0

        # Profit factor
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # Max drawdown
        max_drawdown = self._calculate_max_drawdown()

        # Sharpe ratio
        sharpe_ratio = self._calculate_sharpe_ratio()

        # Average holding period
        holding_periods = [t.holding_period for t in trades]
        avg_holding = sum(holding_periods) / len(holding_periods) if holding_periods else 0

        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=net_profit,
            average_profit=average_profit,
            average_loss=average_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            average_holding_period=avg_holding,
        )

    def _calculate_max_drawdown(self) -> float:
        """
        Calculate maximum drawdown from equity curve.

        Returns:
            Maximum drawdown as decimal
        """
        if not self.equity_curve:
            return 0.0

        peak = self.equity_curve[0][1]
        max_drawdown = 0.0

        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate annualized Sharpe ratio.

        Args:
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Sharpe ratio
        """
        if len(self.daily_returns) < 2:
            return 0.0

        # Calculate mean daily return
        mean_return = sum(self.daily_returns) / len(self.daily_returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in self.daily_returns) / len(self.daily_returns)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return 0.0

        # Annualize
        daily_risk_free = risk_free_rate / 252
        sharpe = (mean_return - daily_risk_free) / std_dev * math.sqrt(252)

        return sharpe

    # ==================== Strategy Analysis ====================

    def get_strategy_metrics(self, strategy: Strategy) -> StrategyMetrics:
        """
        Get metrics for a specific strategy.

        Args:
            strategy: Strategy to analyze

        Returns:
            StrategyMetrics object
        """
        strategy_trades = [t for t in self.trades if t.strategy == strategy]
        metrics = self.calculate_metrics(strategy_trades)

        return StrategyMetrics(
            strategy=strategy,
            metrics=metrics,
            trade_count=len(strategy_trades)
        )

    def get_all_strategy_metrics(self) -> dict[Strategy, StrategyMetrics]:
        """
        Get metrics for all strategies.

        Returns:
            Dictionary of strategy metrics
        """
        results = {}
        for strategy in Strategy:
            results[strategy] = self.get_strategy_metrics(strategy)
        return results

    def get_best_strategy(self) -> Optional[Strategy]:
        """
        Determine the best performing strategy.

        Returns:
            Best Strategy or None
        """
        all_metrics = self.get_all_strategy_metrics()

        best_strategy = None
        best_profit = float('-inf')

        for strategy, sm in all_metrics.items():
            if sm.metrics.net_profit > best_profit:
                best_profit = sm.metrics.net_profit
                best_strategy = strategy

        return best_strategy

    # ==================== Time-based Analysis ====================

    def get_hourly_performance(self) -> dict[int, PerformanceMetrics]:
        """
        Analyze performance by hour of day.

        Returns:
            Dictionary of hour -> metrics
        """
        hourly_trades: dict[int, list[Trade]] = {}

        for trade in self.trades:
            hour = trade.entry_time.hour
            if hour not in hourly_trades:
                hourly_trades[hour] = []
            hourly_trades[hour].append(trade)

        return {
            hour: self.calculate_metrics(trades)
            for hour, trades in hourly_trades.items()
        }

    def get_recent_performance(self, hours: int = 24) -> PerformanceMetrics:
        """
        Get performance for recent time period.

        Args:
            hours: Number of hours to look back

        Returns:
            PerformanceMetrics for period
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent_trades = [t for t in self.trades if t.entry_time >= cutoff]
        return self.calculate_metrics(recent_trades)

    # ==================== Reporting ====================

    def generate_report(self) -> str:
        """
        Generate text performance report.

        Returns:
            Formatted report string
        """
        metrics = self.calculate_metrics()

        report = f"""
═══════════════════════════════════════════════════════════════
                    TRADING PERFORMANCE REPORT
═══════════════════════════════════════════════════════════════

OVERALL PERFORMANCE
───────────────────
Total Trades:        {metrics.total_trades}
Win Rate:            {metrics.win_rate:.1%}
Net Profit:          ${metrics.net_profit:,.2f}
Profit Factor:       {metrics.profit_factor:.2f}
Sharpe Ratio:        {metrics.sharpe_ratio:.2f}
Max Drawdown:        {metrics.max_drawdown:.1%}

PROFIT/LOSS BREAKDOWN
─────────────────────
Winning Trades:      {metrics.winning_trades} (${metrics.total_profit:,.2f})
Losing Trades:       {metrics.losing_trades} (${metrics.total_loss:,.2f})
Avg Win:             ${metrics.average_profit:,.2f}
Avg Loss:            ${metrics.average_loss:,.2f}
Avg Holding Period:  {metrics.average_holding_period:.1f}s

STRATEGY BREAKDOWN
──────────────────"""

        for strategy in Strategy:
            sm = self.get_strategy_metrics(strategy)
            if sm.trade_count > 0:
                report += f"""
{strategy.value.upper()}:
  Trades: {sm.trade_count}  |  Win Rate: {sm.metrics.win_rate:.1%}  |  P&L: ${sm.metrics.net_profit:,.2f}"""

        report += """

═══════════════════════════════════════════════════════════════
"""

        return report

    def get_summary(self) -> dict:
        """
        Get summary statistics as dictionary.

        Returns:
            Summary dictionary
        """
        metrics = self.calculate_metrics()

        return {
            "total_trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "net_profit": metrics.net_profit,
            "profit_factor": metrics.profit_factor,
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown": metrics.max_drawdown,
            "average_profit": metrics.average_profit,
            "average_loss": metrics.average_loss,
            "total_capital": self.current_capital,
            "return_pct": (
                (self.current_capital - self.initial_capital) / self.initial_capital * 100
                if self.initial_capital > 0 else 0
            ),
        }

    def export_trades(self) -> list[dict]:
        """
        Export all trades as list of dictionaries.

        Returns:
            List of trade dictionaries
        """
        return [
            {
                "id": t.id,
                "market_id": t.market_id,
                "side": t.side.value,
                "strategy": t.strategy.value,
                "quantity": t.quantity,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit": t.profit,
                "profit_percent": t.profit_percent,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "holding_period": t.holding_period,
            }
            for t in self.trades
        ]
