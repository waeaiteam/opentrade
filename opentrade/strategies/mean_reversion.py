"""
OpenTrade Strategies - Mean Reversion Strategy

均值回归策略
"""

from dataclasses import dataclass
from typing import Any
from opentrade.engine import BaseStrategy, Signal, Direction


@dataclass
class MeanReversionConfig:
    """均值回归配置"""
    lookback: int = 20
    entry_threshold: float = 2.0  # 标准差倍数
    exit_threshold: float = 0.5
    position_size: float = 0.1
    holding_period: int = 24  # 最大持仓周期（小时）


class MeanReversionStrategy(BaseStrategy):
    """
    均值回归策略

    逻辑:
    - 价格偏离均值超过 N 个标准差时反向交易
    - 价格回归时平仓
    """

    def __init__(self, config: MeanReversionConfig = None):
        self.config = config or MeanReversionConfig()
        self.name = "Mean Reversion"
        self.description = "Bollinger Band mean reversion"

    @property
    def strategy_id(self) -> str:
        return "mean_reversion"

    async def analyze(self, market_data: dict) -> Signal:
        """分析市场数据，生成信号"""
        prices = market_data.get("prices", [])
        current_price = market_data.get("price", 0)

        if len(prices) < self.config.lookback + 5:
            return Signal.neutral()

        # 计算均值和标准差
        import statistics
        lookback_prices = prices[-self.config.lookback:]
        mean = statistics.mean(lookback_prices)
        std = statistics.stdev(lookback_prices) if len(lookback_prices) > 1 else 0

        if std == 0:
            return Signal.neutral()

        # 计算偏离度 (Z-score)
        z_score = (current_price - mean) / std

        signal = Signal.neutral()

        # 价格超卖 (负向偏离大)
        if z_score < -self.config.entry_threshold:
            signal = Signal(
                direction=Direction.LONG,
                confidence=0.70,
                size=self.config.position_size,
                stop_loss=mean - std * 2,
                take_profit=mean,
                reason=f"Oversold (z={z_score:.2f})",
            )

        # 价格超买 (正向偏离大)
        elif z_score > self.config.entry_threshold:
            signal = Signal(
                direction=Direction.SHORT,
                confidence=0.70,
                size=self.config.position_size,
                stop_loss=mean + std * 2,
                take_profit=mean,
                reason=f"Overbought (z={z_score:.2f})",
            )

        # 价格回归均值，平仓
        elif abs(z_score) < self.config.exit_threshold:
            signal = Signal(
                direction=Direction.CLOSE,
                confidence=0.90,
                size=1.0,
                reason=f"Mean reversion (z={z_score:.2f})",
            )

        return signal

    def get_parameters(self) -> dict:
        return {
            "lookback": self.config.lookback,
            "entry_threshold": self.config.entry_threshold,
            "position_size": self.config.position_size,
        }
