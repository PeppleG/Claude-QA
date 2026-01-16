"""
Bitcoin price feeds from multiple exchanges.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


@dataclass
class BTCPrice:
    """Bitcoin price data."""
    price: float
    timestamp: datetime
    source: str
    volume_24h: float = 0.0
    change_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0


class PriceFeedClient:
    """
    Multi-source Bitcoin price feed client.

    Aggregates price data from multiple exchanges for accuracy.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._price_cache: dict[str, BTCPrice] = {}
        self._cache_ttl = 5  # seconds

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        """Initialize connections to exchanges."""
        self._session = aiohttp.ClientSession()

        # Initialize exchange clients
        self._exchanges = {
            "binance": ccxt.binance({"enableRateLimit": True}),
            "coinbase": ccxt.coinbase({"enableRateLimit": True}),
            "kraken": ccxt.kraken({"enableRateLimit": True}),
        }

        logger.info("Price feed client connected")

    async def disconnect(self):
        """Close all connections."""
        if self._session:
            await self._session.close()
            self._session = None

        for exchange in self._exchanges.values():
            await exchange.close()

        self._exchanges.clear()
        logger.info("Price feed client disconnected")

    async def get_btc_price(self, source: str = "binance") -> BTCPrice:
        """
        Get current BTC price from specified exchange.

        Args:
            source: Exchange name (binance, coinbase, kraken)

        Returns:
            BTCPrice object
        """
        # Check cache
        if source in self._price_cache:
            cached = self._price_cache[source]
            age = (datetime.utcnow() - cached.timestamp).total_seconds()
            if age < self._cache_ttl:
                return cached

        exchange = self._exchanges.get(source)
        if not exchange:
            raise ValueError(f"Unknown exchange: {source}")

        try:
            ticker = await exchange.fetch_ticker("BTC/USDT")

            price = BTCPrice(
                price=ticker["last"],
                timestamp=datetime.utcnow(),
                source=source,
                volume_24h=ticker.get("quoteVolume", 0),
                change_24h=ticker.get("percentage", 0),
                high_24h=ticker.get("high", 0),
                low_24h=ticker.get("low", 0),
            )

            self._price_cache[source] = price
            return price

        except Exception as e:
            logger.error(f"Failed to fetch price from {source}: {e}")
            raise

    async def get_aggregated_price(self) -> BTCPrice:
        """
        Get aggregated BTC price from multiple exchanges.

        Returns:
            BTCPrice with median price from all sources
        """
        prices = []
        sources = []

        for source in self._exchanges.keys():
            try:
                price_data = await self.get_btc_price(source)
                prices.append(price_data.price)
                sources.append(source)
            except Exception as e:
                logger.warning(f"Skipping {source}: {e}")

        if not prices:
            raise RuntimeError("No price data available from any exchange")

        # Use median price for robustness
        prices.sort()
        median_price = prices[len(prices) // 2]

        return BTCPrice(
            price=median_price,
            timestamp=datetime.utcnow(),
            source=",".join(sources),
            volume_24h=sum(
                self._price_cache.get(s, BTCPrice(0, datetime.utcnow(), "")).volume_24h
                for s in sources
            ),
        )

    async def get_price_from_coingecko(self) -> BTCPrice:
        """
        Fallback price fetch from CoinGecko API.

        Returns:
            BTCPrice object
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }

        async with self._session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            btc_data = data.get("bitcoin", {})
            return BTCPrice(
                price=btc_data.get("usd", 0),
                timestamp=datetime.utcnow(),
                source="coingecko",
                volume_24h=btc_data.get("usd_24h_vol", 0),
                change_24h=btc_data.get("usd_24h_change", 0),
            )

    async def get_price_change(self, interval_seconds: int = 60) -> float:
        """
        Calculate BTC price change over interval.

        Args:
            interval_seconds: Time interval in seconds

        Returns:
            Price change percentage
        """
        # Get current price
        current = await self.get_aggregated_price()

        # For short intervals, we estimate from 24h data
        # In production, you'd store historical prices
        if current.change_24h:
            # Estimate based on 24h change
            hourly_change = current.change_24h / 24
            return hourly_change * (interval_seconds / 3600)

        return 0.0

    async def is_volatile(self, threshold: float = 3.0) -> bool:
        """
        Check if BTC is currently volatile.

        Args:
            threshold: Percentage threshold for volatility

        Returns:
            True if volatile
        """
        try:
            price = await self.get_aggregated_price()
            return abs(price.change_24h) > threshold
        except Exception:
            return False

    async def get_price_history(
        self,
        source: str = "binance",
        timeframe: str = "1m",
        limit: int = 100
    ) -> list[dict]:
        """
        Fetch historical OHLCV data.

        Args:
            source: Exchange name
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, etc.)
            limit: Number of candles

        Returns:
            List of OHLCV data
        """
        exchange = self._exchanges.get(source)
        if not exchange:
            raise ValueError(f"Unknown exchange: {source}")

        try:
            ohlcv = await exchange.fetch_ohlcv("BTC/USDT", timeframe, limit=limit)

            return [
                {
                    "timestamp": datetime.fromtimestamp(candle[0] / 1000),
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                }
                for candle in ohlcv
            ]
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV from {source}: {e}")
            raise

    async def watch_price(self, callback, interval: float = 1.0):
        """
        Continuously watch BTC price and call callback on updates.

        Args:
            callback: Function to call with BTCPrice
            interval: Update interval in seconds
        """
        while True:
            try:
                price = await self.get_aggregated_price()
                await callback(price)
            except Exception as e:
                logger.error(f"Price watch error: {e}")

            await asyncio.sleep(interval)
