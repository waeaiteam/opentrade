"""
OpenTrade Strategies - Scalping Strategy

高频剥头皮策略
"""

from dataclasses import dataclass
from typing import Any
from opentrade.engine import BaseStrategy, Signal, Direction


@dataclass
class ScalpingConfig:
    """剥头皮配置"""
    rsi_period: int = 2
    rsi_overbought: int = 85
    rsi_oversold: int = 15
    ema_fast: int = 5
    ema_slow: int = 20
    position_size: float = 0.05
    profit_target: float = 0.002  # 0.2%
    stop_loss: float = 0.001  # 0.1%


class ScalpingStrategy(BaseStrategy):
    """
    高频剥头皮策略

    逻辑:
    - 短周期 RSI + EMA 确认
    - 快速进出，获取小利润
    - 严格止损
    """

    def __init__(self, config: ScalpingConfig = None):
        self.config = config or ScalpingConfig()
        self.name = "Scalping"
        self.description = "High-frequency short-term trading"

    @property
    def strategy_id(self) -> str:
        return "scalping"

    async def analyze(self, market_data: dict) -> Signal:
        """分析市场数据，生成信号"""
        prices = market_data.get("prices", [])
        current_price = market_data.get("price", 0)

        if len(prices) < self.config.ema_slow + 5:
            return Signal.neutral()

        # 计算 RSI
        rsi = self._rsi(prices, self.config.rsi_period)

        # 计算 EMA
        ema_fast = self._ema(prices, self.config.ema_fast)
        ema_slow = self._ema(prices, self.config.ema_slow)

        signal = Signal.neutral()

        # 买入条件: RSI 超卖 + EMA 金叉
        if rsi < self.config.rsi_oversold and ema_fast > ema_slow:
            signal = Signal(
                direction=Direction.LONG,
                confidence=0.65,
                size=self.config.position_size,
                stop_loss=current_price * (1 - self.config.stop_loss),
                take_profit=current_price * (1 + self.config.profit_target),
                reason=f"RSI={rsi:.0f} oversold",
            )

        # 卖出条件: RSI 超买 + EMA 死叉
        elif rsi > self.config.rsi_overbought and ema_fast < ema_slow:
            signal = Signal(
                direction=Direction.SHORT,
                confidence=0.65,
                size=self.config.position_size,
                stop_loss=current_price * (1 + self.config.stop_loss),
                take_profit=current_price * (1 - self.config.profit_target),
                reason=f"RSI={rsi:.0f} overbought",
            )

        return signal

    def _rsi(self, prices: list[float], period: int) -> float:
        """计算 RSI"""
        if len(prices) < period + 1:
            return 50.0

        gains = []
        losses = []

        for i in range(-period, 0):
            change = prices[i + 1] - prices[i]
            if change > 0:
                gains.append(change)
            else:
                losses.append(-change)

        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _ema(self, prices: list[float], period: int) -> float:
        """计算 EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0

        multiplier = 2 / (period + 1)
        ema = prices[-period]

        for price in prices[-period:]:
            ema = price * multiplier + ema * (1 - multiplier)

        return ema

    def get_parameters(self) -> dict:
        return {
            "rsi_period": self.config.rsi_period,
            "position_size": self.config.position_size,
        }
