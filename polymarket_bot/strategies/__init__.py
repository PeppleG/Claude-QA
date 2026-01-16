"""
Trading strategies for the Polymarket bot.
"""

from .market_maker import MarketMakerStrategy
from .trend_follower import TrendFollowerStrategy
from .discount_hunter import DiscountHunterStrategy

__all__ = [
    "MarketMakerStrategy",
    "TrendFollowerStrategy",
    "DiscountHunterStrategy",
]
