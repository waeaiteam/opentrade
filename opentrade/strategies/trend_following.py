"""
OpenTrade Strategies - Trend Following Strategy

趋势跟踪策略
"""

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from opentrade.engine import BaseStrategy, Signal, Direction


@dataclass
class TrendFollowingConfig:
    """趋势跟踪配置"""
    fast_ema: int = 12
    slow_ema: int = 26
    atr_period: int = 14
    atr_multiplier: float = 2.0
    position_size: float = 0.1  # 10% 仓位
    stop_loss_atr: float = 2.0
    take_profit_atr: float = 4.0


class TrendFollowingStrategy(BaseStrategy):
    """
    趋势跟踪策略

    逻辑:
    - EMA 金叉做多，死叉做空
    - ATR 动态止损
    """

    def __init__(self, config: TrendFollowingConfig = None):
        self.config = config or TrendFollowingConfig()
        self.name = "Trend Following"
        self.description = "EMA crossover with ATR stops"

    @property
    def strategy_id(self) -> str:
        return "trend_following"

    async def analyze(self, market_data: dict) -> Signal:
        """分析市场数据，生成信号"""
        prices = market_data.get("prices", [])
        current_price = market_data.get("price", 0)

        if len(prices) < self.config.slow_ema + 5:
            return Signal.neutral()

        # 计算 EMA
        ema_fast = self._ema(prices, self.config.fast_ema)
        ema_slow = self._ema(prices, self.config.slow_ema)

        # 前一根K线的 EMA
        ema_fast_prev = self._ema(prices[:-1], self.config.fast_ema) if len(prices) > 1 else ema_fast
        ema_slow_prev = self._ema(prices[:-1], self.config.slow_ema) if len(prices) > 1 else ema_slow

        # 计算 ATR
        atr = self._atr(market_data, self.config.atr_period)

        # 生成信号
        signal = Signal.neutral()

        # 金叉: 短 EMA 从下方穿越长 EMA
        if ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow:
            stop_loss = current_price - atr * self.config.stop_loss_atr
            take_profit = current_price + atr * self.config.take_profit_atr
            signal = Signal(
                direction=Direction.LONG,
                confidence=0.65,
                size=self.config.position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="EMA Golden Cross",
            )

        # 死叉: 短 EMA 从上方穿越长 EMA
        elif ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow:
            stop_loss = current_price + atr * self.config.stop_loss_atr
            take_profit = current_price - atr * self.config.take_profit_atr
            signal = Signal(
                direction=Direction.SHORT,
                confidence=0.65,
                size=self.config.position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="EMA Death Cross",
            )

        return signal

    def _ema(self, prices: list[float], period: int) -> float:
        """计算 EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0

        multiplier = 2 / (period + 1)
        ema = prices[-period]

        for price in prices[-period:]:
            ema = price * multiplier + ema * (1 - multiplier)

        return ema

    def _atr(self, market_data: dict, period: int) -> float:
        """计算 ATR"""
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        closes = market_data.get("closes", [])

        if len(closes) < period + 1:
            return 0.001 * market_data.get("price", 50000)

        true_ranges = []
        for i in range(-period, 0):
            high = highs[i] if i >= -len(highs) else closes[i]
            low = lows[i] if i >= -len(lows) else closes[i]
            tr = max(
                high - low,
                abs(high - closes[i - 1]),
                abs(low - closes[i - 1]),
            )
            true_ranges.append(tr)

        return sum(true_ranges) / period

    def get_parameters(self) -> dict:
        return {
            "fast_ema": self.config.fast_ema,
            "slow_ema": self.config.slow_ema,
            "atr_period": self.config.atr_period,
            "position_size": self.config.position_size,
        }
