"""
OpenTrade Strategies

内置策略库
"""

from opentrade.strategies.trend_following import TrendFollowingStrategy, TrendFollowingConfig
from opentrade.strategies.mean_reversion import MeanReversionStrategy, MeanReversionConfig
from opentrade.strategies.grid_trading import GridTradingStrategy, GridTradingConfig
from opentrade.strategies.scalping import ScalpingStrategy, ScalpingConfig

__all__ = [
    "TrendFollowingStrategy",
    "TrendFollowingConfig",
    "MeanReversionStrategy",
    "MeanReversionConfig",
    "GridTradingStrategy",
    "GridTradingConfig",
    "ScalpingStrategy",
    "ScalpingConfig",
]
