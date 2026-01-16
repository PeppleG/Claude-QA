"""
Database utilities for persisting trades and analytics.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from ..models import Trade, Position, PortfolioSnapshot


class TradeDatabase:
    """
    SQLite database for trade persistence.

    Stores:
    - Completed trades
    - Position history
    - Portfolio snapshots
    - Performance metrics
    """

    def __init__(self, db_path: str = "trades.db"):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    profit REAL NOT NULL,
                    profit_percent REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    holding_period REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_capital REAL NOT NULL,
                    available_capital REAL NOT NULL,
                    invested_capital REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    total_positions INTEGER NOT NULL,
                    daily_pnl REAL NOT NULL,
                    drawdown REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS daily_summary (
                    date TEXT PRIMARY KEY,
                    starting_capital REAL NOT NULL,
                    ending_capital REAL NOT NULL,
                    total_trades INTEGER NOT NULL,
                    winning_trades INTEGER NOT NULL,
                    losing_trades INTEGER NOT NULL,
                    gross_profit REAL NOT NULL,
                    gross_loss REAL NOT NULL,
                    net_pnl REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
                CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
            """)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==================== Trade Operations ====================

    def save_trade(self, trade: Trade):
        """Save a completed trade."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades (
                    id, market_id, side, strategy, quantity,
                    entry_price, exit_price, profit, profit_percent,
                    entry_time, exit_time, holding_period
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id,
                trade.market_id,
                trade.side.value,
                trade.strategy.value,
                trade.quantity,
                trade.entry_price,
                trade.exit_price,
                trade.profit,
                trade.profit_percent,
                trade.entry_time.isoformat(),
                trade.exit_time.isoformat(),
                trade.holding_period,
            ))

    def get_trades(
        self,
        market_id: Optional[str] = None,
        strategy: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> list[dict]:
        """
        Query trades with optional filters.

        Args:
            market_id: Filter by market
            strategy: Filter by strategy
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum results

        Returns:
            List of trade dictionaries
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if market_id:
            query += " AND market_id = ?"
            params.append(market_id)
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if start_date:
            query += " AND entry_time >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND entry_time <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_trade_stats(self) -> dict:
        """Get aggregate trade statistics."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN profit <= 0 THEN 1 ELSE 0 END) as losses,
                    SUM(profit) as total_profit,
                    AVG(profit) as avg_profit,
                    AVG(CASE WHEN profit > 0 THEN profit END) as avg_win,
                    AVG(CASE WHEN profit < 0 THEN profit END) as avg_loss,
                    MAX(profit) as best_trade,
                    MIN(profit) as worst_trade,
                    AVG(holding_period) as avg_holding_period
                FROM trades
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}

    # ==================== Position Operations ====================

    def save_position(self, position: Position):
        """Save or update a position."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO positions (
                    id, market_id, side, strategy, quantity,
                    entry_price, current_price, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id,
                position.market_id,
                position.side.value,
                position.strategy.value,
                position.quantity,
                position.entry_price,
                position.current_price,
                position.status.value,
                position.created_at.isoformat(),
                position.updated_at.isoformat(),
            ))

    def get_open_positions(self) -> list[dict]:
        """Get all open positions."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM positions WHERE status = 'open'"
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_position(self, position_id: str):
        """Delete a position (on close)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))

    # ==================== Snapshot Operations ====================

    def save_snapshot(self, snapshot: PortfolioSnapshot):
        """Save a portfolio snapshot."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO snapshots (
                    timestamp, total_capital, available_capital,
                    invested_capital, unrealized_pnl, realized_pnl,
                    total_positions, daily_pnl, drawdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.timestamp.isoformat(),
                snapshot.total_capital,
                snapshot.available_capital,
                snapshot.invested_capital,
                snapshot.unrealized_pnl,
                snapshot.realized_pnl,
                snapshot.total_positions,
                snapshot.daily_pnl,
                snapshot.drawdown,
            ))

    def get_snapshots(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> list[dict]:
        """Get portfolio snapshots."""
        query = "SELECT * FROM snapshots WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Daily Summary ====================

    def save_daily_summary(
        self,
        date: datetime,
        starting_capital: float,
        ending_capital: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        gross_profit: float,
        gross_loss: float,
        net_pnl: float
    ):
        """Save daily trading summary."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO daily_summary (
                    date, starting_capital, ending_capital,
                    total_trades, winning_trades, losing_trades,
                    gross_profit, gross_loss, net_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date.strftime("%Y-%m-%d"),
                starting_capital,
                ending_capital,
                total_trades,
                winning_trades,
                losing_trades,
                gross_profit,
                gross_loss,
                net_pnl,
            ))

    def get_daily_summaries(self, days: int = 30) -> list[dict]:
        """Get recent daily summaries."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM daily_summary
                ORDER BY date DESC
                LIMIT ?
            """, (days,))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Export ====================

    def export_to_json(self, output_path: str):
        """Export all data to JSON file."""
        data = {
            "trades": self.get_trades(limit=10000),
            "positions": self.get_open_positions(),
            "snapshots": self.get_snapshots(limit=10000),
            "daily_summaries": self.get_daily_summaries(days=365),
            "stats": self.get_trade_stats(),
            "exported_at": datetime.utcnow().isoformat(),
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
