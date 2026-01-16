"""
Logging configuration for the trading bot.
"""

import logging
import sys
from datetime import datetime
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    Configure logging for the trading bot.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging
        console: Whether to log to console

    Returns:
        Root logger
    """
    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    simple_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    return root_logger


class TradeLogger:
    """
    Specialized logger for trade events.

    Formats trade information in a standardized way.
    """

    def __init__(self):
        self.logger = logging.getLogger("trades")
        self.trade_count = 0

    def log_entry(
        self,
        market_id: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str
    ):
        """Log a trade entry."""
        self.trade_count += 1
        self.logger.info(
            f"ENTRY #{self.trade_count:04d} | {strategy.upper():15s} | "
            f"{market_id[:20]:20s} | {side.upper():3s} | "
            f"Qty: {quantity:10.2f} | Price: ${price:.4f}"
        )

    def log_exit(
        self,
        market_id: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_percent: float
    ):
        """Log a trade exit."""
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        pnl_pct_str = f"+{pnl_percent:.1f}%" if pnl_percent >= 0 else f"{pnl_percent:.1f}%"

        self.logger.info(
            f"EXIT  | {market_id[:20]:20s} | {side.upper():3s} | "
            f"Qty: {quantity:10.2f} | Entry: ${entry_price:.4f} | "
            f"Exit: ${exit_price:.4f} | P&L: {pnl_str} ({pnl_pct_str})"
        )

    def log_alert(self, level: str, message: str):
        """Log a risk alert."""
        if level == "emergency":
            self.logger.critical(f"🚨 EMERGENCY: {message}")
        elif level == "critical":
            self.logger.error(f"⚠️  CRITICAL: {message}")
        else:
            self.logger.warning(f"⚡ WARNING: {message}")

    def log_opportunity(
        self,
        market_id: str,
        opportunity_type: str,
        details: str
    ):
        """Log a detected opportunity."""
        self.logger.info(
            f"💡 OPPORTUNITY | {opportunity_type.upper():15s} | "
            f"{market_id[:20]:20s} | {details}"
        )
