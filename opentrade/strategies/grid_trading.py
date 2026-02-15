"""
OpenTrade Strategies - Grid Trading Strategy

网格交易策略
"""

from dataclasses import dataclass
from typing import Any
from opentrade.engine import BaseStrategy, Signal, Direction


@dataclass
class GridTradingConfig:
    """网格交易配置"""
    grid_levels: int = 10
    grid_spacing_pct: float = 0.01  # 1% 间隔
    position_size: float = 0.01  # 每次下单量
    upper_bound: float = 0.0
    lower_bound: float = 0.0


class GridTradingStrategy(BaseStrategy):
    """
    网格交易策略

    逻辑:
    - 在价格区间内设置多个网格
    - 价格触及网格线时自动下单
    - 适合震荡市场
    """

    def __init__(self, config: GridTradingConfig = None):
        self.config = config or GridTradingConfig()
        self.name = "Grid Trading"
        self.description = "Automated grid trading"

    @property
    def strategy_id(self) -> str:
        return "grid_trading"

    async def analyze(self, market_data: dict) -> Signal:
        """分析市场数据，生成信号"""
        current_price = market_data.get("price", 0)

        if current_price == 0:
            return Signal.neutral()

        # 设置默认边界
        if self.config.upper_bound == 0:
            self.config.upper_bound = current_price * 1.05
        if self.config.lower_bound == 0:
            self.config.lower_bound = current_price * 0.95

        signal = Signal.neutral()

        # 计算当前网格位置
        grid_range = self.config.upper_bound - self.config.lower_bound
        grid_size = grid_range / self.config.grid_levels

        if grid_size == 0:
            return Signal.neutral()

        # 价格高于上界，清仓
        if current_price >= self.config.upper_bound:
            signal = Signal(
                direction=Direction.CLOSE,
                confidence=0.95,
                size=1.0,
                reason="Above upper grid",
            )

        # 价格低于下界，建仓
        elif current_price <= self.config.lower_bound:
            signal = Signal(
                direction=Direction.LONG,
                confidence=0.80,
                size=0.2,
                reason="Below lower grid",
            )

        # 震荡区间内，网格交易
        else:
            current_grid = int((current_price - self.config.lower_bound) / grid_size)
            next_grid_up = current_grid + 1
            next_grid_down = current_grid - 1

            price_up = self.config.lower_bound + next_grid_up * grid_size
            price_down = self.config.lower_bound + next_grid_down * grid_size

            # 接近下网格，买入
            if current_price - price_down < grid_size * 0.3:
                signal = Signal(
                    direction=Direction.LONG,
                    confidence=0.60,
                    size=self.config.position_size,
                    reason=f"Grid {next_grid_down} touch",
                )

            # 接近上网格，卖出
            elif price_up - current_price < grid_size * 0.3:
                signal = Signal(
                    direction=Direction.SHORT,
                    confidence=0.60,
                    size=self.config.position_size,
                    reason=f"Grid {next_grid_up} touch",
                )

        return signal

    def get_parameters(self) -> dict:
        return {
            "grid_levels": self.config.grid_levels,
            "grid_spacing_pct": self.config.grid_spacing_pct,
            "position_size": self.config.position_size,
        }
