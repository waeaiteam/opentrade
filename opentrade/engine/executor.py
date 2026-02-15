"""
OpenTrade 统一执行引擎

统一 Simulated/CCXT adapter，确�回测-实盘一致性。

设计原则:
1. 单一执行接口 - 回测和实盘使用相同代码
2. Adapter 模式 - 不同交易所/模拟通过 adapter 隔离
3. 完整审计 - 每笔订单可追溯
4. 事件驱动 - 支持实时状态更新
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


class PositionSide(str, Enum):
    """持仓方向"""
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


# ============ 数据模型 ============

class OrderRequest(BaseModel):
    """订单请求"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = 0.0  # 数量
    price: float | None = None  # 限价
    stop_price: float | None = None  # 止损价

    # 杠杆
    leverage: float = 1.0

    # 止盈止损
    take_profit: float | None = None
    stop_loss: float | None = None

    # 元数据
    client_order_id: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    trace_id: str | None = None

    # 时间
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class Fill(BaseModel):
    """成交记录"""
    fill_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float = 0.0
    fee_currency: str = "USDT"
    timestamp: str
    trade_id: str | None = None


class Order(BaseModel):
    """订单"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus

    # 数量
    quantity: float
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0

    # 价格
    price: float | None = None
    avg_fill_price: float | None = None

    # 止盈止损
    take_profit: float | None = None
    stop_loss: float | None = None

    # 杠杆
    leverage: float = 1.0

    # 成交
    fills: list[Fill] = field(default_factory=list)

    # 错误
    rejection_reason: str | None = None

    # 元数据
    client_order_id: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    trace_id: str | None = None

    # 时间
    created_at: str
    updated_at: str
    filled_at: str | None = None


class Position(BaseModel):
    """持仓"""
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    mark_price: float | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    leverage: float = 1.0
    liquidation_price: float | None = None

    # 时间
    opened_at: str
    updated_at: str


class AccountBalance(BaseModel):
    """账户余额"""
    total_balance: float
    available_balance: float
    margin_balance: float
    unrealized_pnl: float = 0.0

    # 各币种余额
    balances: dict[str, float] = field(default_factory=dict)


class Ticker(BaseModel):
    """行情"""
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume: float = 0.0
    timestamp: str


# ============ Adapter 接口 ============

class ExecutionAdapter(ABC):
    """执行 Adapter 基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter 名称"""
        pass

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        """是否模拟交易"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """连接交易所"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    async def create_order(self, request: OrderRequest) -> Order:
        """创建订单"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order | None:
        """查询订单"""
        pass

    @abstractmethod
    async def get_orders(self, symbol: str | None = None) -> list[Order]:
        """查询订单列表"""
        pass

    @abstractmethod
    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """查询持仓"""
        pass

    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """查询余额"""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker | None:
        """查询行情"""
        pass

    @abstractmethod
    async def get_tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        """批量查询行情"""
        pass


# ============ 统一执行器 ============

class TradeExecutor:
    """
    统一交易执行器

    封装所有交易所交互，向上提供统一接口
    """

    def __init__(self, adapter: ExecutionAdapter):
        self.adapter = adapter
        self._connected = False

    @property
    def name(self) -> str:
        return self.adapter.name

    @property
    def is_simulated(self) -> bool:
        return self.adapter.is_simulated

    # ============ 连接管理 ============

    async def connect(self) -> bool:
        """连接"""
        if self._connected:
            return True

        success = await self.adapter.connect()
        if success:
            self._connected = True
        return success

    async def disconnect(self):
        """断开"""
        await self.adapter.disconnect()
        self._connected = False

    async def ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            await self.connect()

    # ============ 订单操作 ============

    async def submit_order(self, request: OrderRequest) -> Order:
        """提交订单 (主入口)"""
        await self.ensure_connected()
        return await self.adapter.create_order(request)

    async def buy(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        leverage: float = 1.0,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        strategy_id: str | None = None,
        trace_id: str | None = None,
    ) -> Order:
        """买入"""
        request = OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
            quantity=quantity,
            price=price,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_id=strategy_id,
            trace_id=trace_id,
        )
        return await self.submit_order(request)

    async def sell(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        leverage: float = 1.0,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        strategy_id: str | None = None,
        trace_id: str | None = None,
    ) -> Order:
        """卖出"""
        request = OrderRequest(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
            quantity=quantity,
            price=price,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_id=strategy_id,
            trace_id=trace_id,
        )
        return await self.submit_order(request)

    async def close_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float | None = None,
        price: float | None = None,
        strategy_id: str | None = None,
        trace_id: str | None = None,
    ) -> Order:
        """平仓"""
        order_side = OrderSide.SELL if side == PositionSide.LONG else OrderSide.BUY
        request = OrderRequest(
            symbol=symbol,
            side=order_side,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
            quantity=quantity or 0,  # 全平
            price=price,
            strategy_id=strategy_id,
            trace_id=trace_id,
        )
        return await self.submit_order(request)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        await self.ensure_connected()
        return await self.adapter.cancel_order(order_id, symbol)

    async def cancel_all_orders(self, symbol: str | None = None) -> int:
        """取消所有订单"""
        await self.ensure_connected()
        orders = await self.adapter.get_orders(symbol)
        cancelled = 0
        for order in orders:
            if order.status in [OrderStatus.PENDING, OrderStatus.OPEN]:
                if await self.adapter.cancel_order(order.order_id, order.symbol):
                    cancelled += 1
        return cancelled

    # ============ 查询操作 ============

    async def get_order(self, order_id: str, symbol: str) -> Order | None:
        """查询订单"""
        await self.ensure_connected()
        return await self.adapter.get_order(order_id, symbol)

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """查询未完成订单"""
        await self.ensure_connected()
        orders = await self.adapter.get_orders(symbol)
        return [o for o in orders if o.status in [OrderStatus.PENDING, OrderStatus.OPEN]]

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """查询持仓"""
        await self.ensure_connected()
        return await self.adapter.get_positions(symbol)

    async def get_balance(self) -> AccountBalance:
        """查询余额"""
        await self.ensure_connected()
        return await self.adapter.get_balance()

    async def get_ticker(self, symbol: str) -> Ticker | None:
        """查询行情"""
        await self.ensure_connected()
        return await self.adapter.get_ticker(symbol)

    async def get_tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        """批量查询行情"""
        await self.ensure_connected()
        return await self.adapter.get_tickers(symbols)


# ============ 工厂函数 ============

def create_simulated_executor(
    initial_balance: float = 10000.0,
    fees: float = 0.001,
) -> TradeExecutor:
    """创建模拟交易执行器"""
    from opentrade.engine.adapters.simulated import SimulatedAdapter

    adapter = SimulatedAdapter(
        initial_balance=initial_balance,
        fees=fees,
    )
    return TradeExecutor(adapter)


def create_ccxt_executor(
    exchange: str,
    api_key: str,
    api_secret: str,
    password: str | None = None,
    testnet: bool = True,
) -> TradeExecutor:
    """创建 CCXT 交易所执行器"""
    from opentrade.engine.adapters.ccxt import CCXTAdapter

    adapter = CCXTAdapter(
        exchange=exchange,
        api_key=api_key,
        api_secret=api_secret,
        password=password,
        testnet=testnet,
    )
    return TradeExecutor(adapter)


# ============ 策略基类 ============

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    """交易方向"""
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


@dataclass
class Signal:
    """交易信号"""
    direction: Direction = Direction.HOLD
    confidence: float = 0.0
    size: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""

    @classmethod
    def neutral(cls) -> "Signal":
        return cls()

    @classmethod
    def long(cls, confidence: float = 0.5, size: float = 0.1, **kwargs) -> "Signal":
        return cls(
            direction=Direction.LONG,
            confidence=confidence,
            size=size,
            **kwargs
        )

    @classmethod
    def short(cls, confidence: float = 0.5, size: float = 0.1, **kwargs) -> "Signal":
        return cls(
            direction=Direction.SHORT,
            confidence=confidence,
            size=size,
            **kwargs
        )

    @classmethod
    def close(cls, confidence: float = 0.9, **kwargs) -> "Signal":
        return cls(
            direction=Direction.CLOSE,
            confidence=confidence,
            size=1.0,
            **kwargs
        )


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """策略 ID"""
        pass

    @abstractmethod
    async def analyze(self, market_data: dict) -> Signal:
        """
        分析市场数据，生成信号

        Args:
            market_data: 市场数据字典，包含:
                - price: 当前价格
                - prices: 历史价格列表
                - highs: 最高价列表
                - lows: 最低价列表
                - closes: 收盘价列表
                - volumes: 成交量列表

        Returns:
            Signal: 交易信号
        """
        pass

    def get_parameters(self) -> dict:
        """获取策略参数"""
        return {}

    async def on_order_update(self, order: dict):
        """订单更新回调"""
        pass

    async def on_position_update(self, position: dict):
        """持仓更新回调"""
        pass
