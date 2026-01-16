"""
Polymarket Trading Bot - Entry Point

Usage:
    python -m polymarket_bot.main [OPTIONS]

Options:
    --capital FLOAT     Initial trading capital (default: 1000)
    --config PATH       Path to config file
    --dry-run           Run in simulation mode without real trades
    --log-level LEVEL   Logging level (DEBUG, INFO, WARNING, ERROR)
    --log-file PATH     Path to log file
"""

import argparse
import asyncio
import signal
import sys
from datetime import datetime

from .bot import PolymarketTradingBot
from .config import BotConfig, load_config
from .utils import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Polymarket Trading Bot - High-frequency prediction market trading"
    )

    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Initial trading capital in USD (default: 1000)"
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in simulation mode (no real trades)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default="trading_bot.log",
        help="Path to log file (default: trading_bot.log)"
    )

    return parser.parse_args()


def print_banner():
    """Print startup banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ██████╗  ██████╗ ██╗  ██╗   ██╗███╗   ███╗ █████╗ ██████╗ ██╗  ██╗███████╗████████╗ ║
║   ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝██╔════╝╚══██╔══╝ ║
║   ██████╔╝██║   ██║██║   ╚████╔╝ ██╔████╔██║███████║██████╔╝█████╔╝ █████╗     ██║    ║
║   ██╔═══╝ ██║   ██║██║    ╚██╔╝  ██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗ ██╔══╝     ██║    ║
║   ██║     ╚██████╔╝███████╗██║   ██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗███████╗   ██║    ║
║   ╚═╝      ╚═════╝ ╚══════╝╚═╝   ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝    ║
║                                                                               ║
║                     TRADING BOT v1.0.0                                        ║
║                                                                               ║
║   Strategy Performance Target: 95%+ Win Rate                                  ║
║   Strategies: Market Making | Trend Following | Discount Hunting              ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config(config: BotConfig, capital: float, dry_run: bool):
    """Print configuration summary."""
    print(f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│ CONFIGURATION                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Mode:              {'DRY RUN (Simulation)' if dry_run else 'LIVE TRADING'}
│ Initial Capital:   ${capital:,.2f}
│ Max Position Size: {config.trading.max_position_percent:.0%} per market
│ Risk Per Trade:    {config.trading.risk_per_trade:.0%}
│ Spread Threshold:  {config.trading.spread_threshold:.0%}
│ Discount Alert:    ${config.trading.discount_threshold:.2f}
│ Extreme Discount:  ${config.trading.extreme_discount_threshold:.2f}
├─────────────────────────────────────────────────────────────────────────────┤
│ RISK LIMITS                                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Max Drawdown:      {config.risk.max_portfolio_drawdown:.0%}
│ Daily Loss Limit:  {config.risk.daily_loss_limit:.0%}
│ Position Stop:     {config.risk.position_stop_loss:.0%}
│ Max Positions:     {config.risk.max_positions}
│ Kill Switch:       {'Enabled' if config.risk.enable_kill_switch else 'Disabled'}
└─────────────────────────────────────────────────────────────────────────────┘
""")


async def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    logger = setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        console=True
    )

    # Print banner
    print_banner()

    # Load configuration
    config = load_config()
    config.trading.initial_capital = args.capital

    # Print configuration
    print_config(config, args.capital, args.dry_run)

    # Create bot instance
    bot = PolymarketTradingBot(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    # Start the bot
    print(f"\n{'='*77}")
    print(f"  Starting bot at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*77}\n")

    try:
        if args.dry_run:
            logger.info("Running in DRY RUN mode - no real trades will be executed")
            # In dry run mode, we could run a simulation
            await simulate_trading(bot)
        else:
            await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        # Print final report
        print("\n" + bot.generate_report())

    return 0


async def simulate_trading(bot: PolymarketTradingBot):
    """
    Run trading simulation for testing.

    This mode simulates market data and trade execution
    without connecting to real APIs.
    """
    import logging
    import random

    logger = logging.getLogger(__name__)
    logger.info("Starting trading simulation...")

    # Simulate some market activity
    for i in range(10):
        logger.info(f"Simulation cycle {i+1}/10")

        # Simulate market data updates
        status = bot.get_status()
        logger.info(f"Bot status: {status['positions']}")

        await asyncio.sleep(2)

    logger.info("Simulation complete")


def run():
    """Entry point for console script."""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
