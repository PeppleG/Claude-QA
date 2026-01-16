# Polymarket Trading Bot

A high-frequency trading bot for Polymarket prediction markets that implements three core strategies for capturing profits from Bitcoin-related markets.

## Performance Target

- **Win Rate:** 95%+
- **Trade Frequency:** High-frequency (WebSocket-based)
- **Focus:** Bitcoin-related prediction markets

## Strategy Overview

### Phase 1: Market Making
- Enter both sides of new markets when spreads are wide
- Capture spread profits with minimal directional risk
- Entry trigger: Spread > 10%

### Phase 2: Trend Following
- Monitor position momentum
- Abandon losing positions, scale into winners
- Reallocate 100% capital to winning side

### Phase 3: Discount Hunting (Major Profit Driver)
- Scan for extreme discounts ($0.01-$0.03)
- Aggressive accumulation during volatility spikes
- 30x+ return potential with minimal risk per share

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd polymarket-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your API credentials
```

## Configuration

Create a `.env` file with your credentials:

```env
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
PRIVATE_KEY=your_wallet_private_key
RPC_URL=https://polygon-rpc.com
```

## Usage

### Basic Usage

```bash
# Run with default settings ($1000 capital)
python -m polymarket_bot.main

# Run with custom capital
python -m polymarket_bot.main --capital 5000

# Run in dry-run mode (simulation)
python -m polymarket_bot.main --dry-run

# Run with debug logging
python -m polymarket_bot.main --log-level DEBUG
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--capital` | Initial trading capital (USD) | 1000 |
| `--config` | Path to configuration file | None |
| `--dry-run` | Run in simulation mode | False |
| `--log-level` | Logging level | INFO |
| `--log-file` | Path to log file | trading_bot.log |

## Project Structure

```
polymarket_bot/
├── __init__.py
├── main.py              # Entry point and CLI
├── bot.py               # Main bot orchestrator
├── config.py            # Configuration management
├── models.py            # Data models
├── risk_management.py   # Risk controls
├── analytics.py         # Performance metrics
├── api/
│   ├── __init__.py
│   ├── polymarket_client.py  # Polymarket API client
│   └── price_feeds.py        # Bitcoin price feeds
├── strategies/
│   ├── __init__.py
│   ├── base.py               # Base strategy class
│   ├── market_maker.py       # Phase 1: Market making
│   ├── trend_follower.py     # Phase 2: Trend following
│   └── discount_hunter.py    # Phase 3: Discount hunting
└── utils/
    ├── __init__.py
    ├── logging_config.py     # Logging setup
    └── database.py           # Trade persistence
```

## Risk Management

The bot includes comprehensive risk controls:

- **Position Limits:** Max 20% per market, 10 positions max
- **Stop Loss:** 30% position stop loss
- **Drawdown:** 20% max portfolio drawdown
- **Daily Limit:** 5% daily loss limit
- **Kill Switch:** Emergency stop on critical conditions

## Performance Metrics

The bot tracks:

- Win rate
- Profit factor
- Sharpe ratio
- Maximum drawdown
- Average trade profit/loss
- Strategy-specific performance

## Safety Features

- **Kill Switch:** Automatically stops trading on critical risk levels
- **Position Sizing:** Risk-based position sizing
- **Daily Limits:** Stops trading when daily loss limit reached
- **Consecutive Loss Tracking:** Alerts on losing streaks

## Important Warnings

⚠️ **HIGH RISK TRADING**

- Past performance does not guarantee future results
- You can lose all your capital quickly
- Start with small amounts you can afford to lose
- Monitor the bot constantly at first
- Have kill switch ready

## Legal & Compliance

Before using this bot:

1. Verify Polymarket is legal in your jurisdiction
2. Check if bot trading violates Polymarket ToS
3. Understand tax implications
4. Consult with legal counsel if needed

## Development

```bash
# Run tests
pytest

# Type checking
mypy polymarket_bot/

# Format code
black polymarket_bot/
```

## License

MIT License - Use at your own risk.

## Disclaimer

This software is for educational purposes only. Trading prediction markets carries significant risk. The authors are not responsible for any financial losses incurred from using this software.
