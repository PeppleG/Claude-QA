"""
Configuration settings for the Polymarket Trading Bot.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class APIConfig:
    """API configuration settings."""
    polymarket_api_key: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY", ""))
    polymarket_api_secret: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_SECRET", ""))
    polymarket_base_url: str = "https://clob.polymarket.com"
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws"

    # Blockchain settings
    private_key: str = field(default_factory=lambda: os.getenv("PRIVATE_KEY", ""))
    rpc_url: str = field(default_factory=lambda: os.getenv("RPC_URL", "https://polygon-rpc.com"))
    chain_id: int = 137  # Polygon mainnet


@dataclass
class TradingConfig:
    """Trading strategy configuration."""
    # Capital allocation
    initial_capital: float = 1000.0
    max_position_percent: float = 0.20  # Maximum 20% per market
    cash_reserve_percent: float = 0.30  # Reserve 30% for discount opportunities

    # Phase 1: Market Making
    spread_threshold: float = 0.10  # 10% spread threshold for entry
    market_maker_allocation: float = 0.50  # 50/50 split between Yes/No

    # Phase 2: Trend Following
    momentum_check_interval: int = 10  # seconds
    momentum_threshold: float = 0.05  # 5% price change to confirm trend
    trend_confirmation_periods: int = 3  # Number of periods to confirm trend

    # Phase 3: Discount Hunting
    discount_threshold: float = 0.05  # Alert when price drops below $0.05
    extreme_discount_threshold: float = 0.03  # Aggressive buy at $0.01-$0.03
    min_discount_price: float = 0.01
    max_discount_price: float = 0.03

    # Position sizing
    risk_per_trade: float = 0.05  # 5% risk per trade

    # Market selection
    min_market_volume: float = 10000.0  # $10K minimum volume
    min_spread_width: float = 0.05  # 5% minimum spread


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Stop-loss settings
    position_stop_loss: float = 0.30  # Exit if position down 30%
    max_portfolio_drawdown: float = 0.20  # 20% max portfolio drawdown
    daily_loss_limit: float = 0.05  # 5% daily loss limit

    # Position limits
    max_positions: int = 10  # Maximum 10 active positions
    max_single_market_exposure: float = 0.20  # 20% max per market

    # Emergency controls
    enable_kill_switch: bool = True
    max_consecutive_losses: int = 5


@dataclass
class PerformanceConfig:
    """Performance tracking configuration."""
    target_win_rate: float = 0.95  # 95% target win rate
    min_profit_target: float = 0.10  # 10% minimum profit target
    max_holding_period: int = 3600  # 1 hour max holding (seconds)


@dataclass
class BotConfig:
    """Main bot configuration combining all settings."""
    api: APIConfig = field(default_factory=APIConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    # Polling and timing
    main_loop_interval: float = 1.0  # Main loop interval in seconds
    websocket_reconnect_delay: float = 5.0  # Reconnect delay on disconnect

    # Logging
    log_level: str = "INFO"
    log_trades: bool = True
    log_file: str = "trading_bot.log"

    # Database
    db_path: str = "trades.db"


def load_config() -> BotConfig:
    """Load configuration from environment and defaults."""
    return BotConfig()
