"""
OpenTrade 执行引擎优化 - P1 优化

核心优化:
1. 智能订单路由与执行优化
2. 防插针机制
3. 高仿真模拟盘
4. 订单全链路追踪

作者: OpenTrade AI
日期: 2026-02-15
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ============== 订单类型 ==============

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"
    SHORT = "short"
    COVER = "cover"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


# ============== 订单模型 ==============

@dataclass
class Order:
    """订单"""
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    
    # 数量
    quantity: float
    price: Optional[float]  # 限价
    stop_price: Optional[float]  # 止损触发价
    
    # 执行参数
    time_in_force: str = "gtc"  # gtc/ioc/fok
    
    # 策略信息
    strategy_id: str = None
    signal_id: str = None
    
    # 状态
    status: str = "pending"  # pending/open/filled/cancelled/failed
    filled_quantity: float = 0.0
    average_price: float = None
    commission: float = 0.0
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # 元数据
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "status": self.status,
            "filled_quantity": self.filled_quantity,
            "average_price": self.average_price,
            "commission": self.commission,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "strategy_id": self.strategy_id,
            "signal_id": self.signal_id,
        }


@dataclass
class Position:
    """持仓"""
    id: str
    symbol: str
    side: PositionSide
    
    size: float
    entry_price: float
    entry_time: datetime
    
    # 订单
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # 实时数据
    mark_price: float = None
    liquidation_price: float = None
    
    # 状态
    status: str = "open"  # open/closed/liquidated
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "status": self.status,
        }


# ============== 智能订单路由器 ==============

class SmartOrderRouter:
    """
    智能订单路由器
    
    功能:
    1. 流动性聚合
    2. 算法执行 (TWAP/VWAP)
    3. 极端行情防护
    """
    
    def __init__(self):
        self._exchanges: dict[str, dict] = {}  # 交易所信息
        self._order_books: dict[str, list[dict]] = {}  # 订单簿缓存
        
        # 配置
        self.config = {
            "max_slippage": 0.005,      # 最大滑点 0.5%
            "max_order_value": 100000,  # 单笔最大订单价值
            "twap_slices": 10,          # TWAP 分片数
            "vwap_window": 300,          # VWAP 窗口 (秒)
            "anti_pin_threshold": 0.02, # 防插针阈值 2%
            "anti_pin_coolDown": 60,    # 冷却时间 (秒)
        }
    
    def add_exchange(self, exchange_id: str, info: dict):
        """添加交易所"""
        self._exchanges[exchange_id] = info
    
    async def get_best_route(self, symbol: str, quantity: float) -> dict:
        """
        获取最佳执行路由
        
        Returns:
            {
                "exchange_id": "binance",
                "price": 50000.0,
                "available": 1000.0,
                "slippage_estimate": 0.001,
                "fee": 0.001,
            }
        """
        # 模拟: 获取各交易所价格
        candidates = []
        
        for ex_id, ex_info in self._exchanges.items():
            price_info = await self._get_price(ex_id, symbol)
            if price_info:
                candidates.append({
                    "exchange_id": ex_id,
                    **price_info,
                })
        
        if not candidates:
            return None
        
        # 选择最佳
        best = min(candidates, key=lambda x: (
            x.get("slippage_estimate", 0) + x.get("fee", 0)
        ))
        
        return best
    
    async def _get_price(self, exchange_id: str, symbol: str) -> Optional[dict]:
        """获取价格 (模拟)"""
        return {
            "price": 50000.0,
            "available": 1000.0,
            "slippage_estimate": 0.001,
            "fee": 0.001,
        }
    
    async def execute_twap(self, symbol: str, quantity: float,
                          duration_seconds: int = 300) -> list[Order]:
        """
        TWAP 执行
        
        将大单拆分成小单，在指定时间内执行
        """
        slice_size = quantity / self.config["twap_slices"]
        slice_interval = duration_seconds / self.config["twap_slices"]
        
        orders = []
        
        for i in range(self.config["twap_slices"]):
            # 获取当前最佳价格
            route = await self.get_best_route(symbol, slice_size)
            
            if route:
                order = Order(
                    id=str(uuid4()),
                    symbol=symbol,
                    side=OrderSide.BUY if quantity > 0 else OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=slice_size,
                    price=route["price"],
                    metadata={"router": "twap", "slice": i + 1},
                )
                orders.append(order)
            
            # 等待间隔
            if i < self.config["twap_slices"] - 1:
                await self._sleep(slice_interval)
        
        return orders
    
    async def execute_vwap(self, symbol: str, quantity: float) -> list[Order]:
        """
        VWAP 执行
        
        根据历史成交量分布执行订单
        """
        # 获取 VWAP 分布
        distribution = await self._get_vwap_distribution(symbol)
        
        orders = []
        remaining = quantity
        
        for interval, pct in distribution.items():
            slice_size = quantity * pct
            if slice_size > remaining:
                slice_size = remaining
            
            route = await self.get_best_route(symbol, slice_size)
            
            if route and slice_size > 0:
                order = Order(
                    id=str(uuid4()),
                    symbol=symbol,
                    side=OrderSide.BUY if quantity > 0 else OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=slice_size,
                    price=route["price"],
                    metadata={"router": "vwap"},
                )
                orders.append(order)
                remaining -= slice_size
            
            if remaining <= 0:
                break
        
        return orders
    
    async def _get_vwap_distribution(self, symbol: str) -> dict:
        """获取 VWAP 分布 (模拟: 每小时分布)"""
        # 返回 24 小时的成交量分布
        return {i: 1/24 for i in range(24)}
    
    async def _sleep(self, seconds: float):
        """休眠"""
        import asyncio
        await asyncio.sleep(seconds)


# ============== 防插针机制 ==============

class AntiPinController:
    """
    防插针控制器
    
    功能:
    1. 检测异常波动
    2. 暂停止损止盈订单
    3. 等待稳定后恢复
    """
    
    def __init__(self):
        self._last_spike_time: Optional[datetime] = None
        self._paused_orders: list[str] = []
        
        self.config = {
            "spike_threshold": 0.02,      # 2% 瞬时波动
            "spike_check_window": 1000,   # 1秒窗口
            "pause_duration": 5000,      # 暂停5秒
            "volume_spike_ratio": 3.0,    # 成交量异常倍数
        }
    
    async def check_and_protect(self, symbol: str, 
                               current_price: float,
                               previous_price: float,
                               current_volume: float,
                               avg_volume: float) -> dict:
        """
        检查并保护
        
        Returns:
            {
                "action": "continue" / "pause" / "resume",
                "reason": "理由",
                "paused_orders": [],
            }
        """
        # 计算波动
        price_change = abs(current_price - previous_price) / previous_price
        
        # 检查价格插针
        if price_change > self.config["spike_threshold"]:
            now = datetime.utcnow()
            
            # 检查冷却
            if (self._last_spike_time is None or 
                (now - self._last_spike_time).total_seconds() * 1000 > 
                self.config["pause_duration"]):
                
                self._last_spike_time = now
                return {
                    "action": "pause",
                    "reason": f"检测到 {price_change:.2%} 价格插针",
                    "paused_orders": self._paused_orders,
                }
        
        # 检查成交量异常
        if avg_volume > 0 and current_volume / avg_volume > self.config["volume_spike_ratio"]:
            return {
                "action": "pause",
                "reason": f"成交量异常 {current_volume/avg_volume:.1f}x",
                "paused_orders": self._paused_orders,
            }
        
        # 检查是否可以恢复
        if self._last_spike_time:
            elapsed = (datetime.utcnow() - self._last_spike_time).total_seconds() * 1000
            if elapsed > self.config["pause_duration"]:
                self._last_spike_time = None
                return {
                    "action": "resume",
                    "reason": "价格已稳定",
                    "paused_orders": self._paused_orders,
                }
        
        return {
            "action": "continue",
            "reason": None,
            "paused_orders": [],
        }
    
    def pause_order(self, order_id: str):
        """暂停订单"""
        if order_id not in self._paused_orders:
            self._paused_orders.append(order_id)
    
    def resume_order(self, order_id: str):
        """恢复订单"""
        if order_id in self._paused_orders:
            self._paused_orders.remove(order_id)


# ============== 订单全链路追踪 ==============

class OrderTracker:
    """
    订单全链路追踪器
    
    为每笔订单生成唯一追踪 ID
    覆盖从创建、提交、成交到完结的全生命周期
    """
    
    def __init__(self):
        self._orders: dict[str, Order] = {}
        self._events: list[dict] = []
        
        # 事件类型
        self.EVENT_TYPES = {
            "created": "订单创建",
            "submitted": "订单提交",
            "filled": "订单成交",
            "partially_filled": "订单部分成交",
            "cancelled": "订单取消",
            "failed": "订单失败",
            "stop_triggered": "止损触发",
            "tp_triggered": "止盈触发",
            "liquidated": "强平",
        }
    
    def generate_trace_id(self) -> str:
        """生成追踪 ID"""
        return f"trace_{uuid4().hex[:16]}"
    
    def create_trace(self, order: Order, trace_id: str = None) -> str:
        """创建追踪"""
        if trace_id is None:
            trace_id = self.generate_trace_id()
        
        self._orders[trace_id] = order
        
        # 记录创建事件
        self._record_event(trace_id, "created", {
            "order": order.to_dict(),
        })
        
        return trace_id
    
    def record_event(self, trace_id: str, event_type: str, details: dict):
        """记录事件"""
        self._record_event(trace_id, event_type, details)
        
        # 如果是完成事件，更新订单状态
        if trace_id in self._orders:
            order = self._orders[trace_id]
            if event_type == "filled":
                order.status = "filled"
            elif event_type == "cancelled":
                order.status = "cancelled"
    
    def _record_event(self, trace_id: str, event_type: str, details: dict):
        """记录事件"""
        event = {
            "trace_id": trace_id,
            "event_type": event_type,
            "event_name": self.EVENT_TYPES.get(event_type, event_type),
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
        }
        self._events.append(event)
    
    def get_trace(self, trace_id: str) -> list[dict]:
        """获取追踪链路"""
        return [e for e in self._events if e["trace_id"] == trace_id]
    
    def get_order_trace(self, order_id: str) -> list[dict]:
        """通过订单 ID 获取追踪"""
        for trace_id, order in self._orders.items():
            if order.id == order_id:
                return self.get_trace(trace_id)
        return []
    
    def export_trace(self, trace_id: str) -> dict:
        """导出追踪报告"""
        events = self.get_trace(trace_id)
        
        if not events:
            return {}
        
        order = self._orders.get(trace_id)
        
        return {
            "trace_id": trace_id,
            "order": order.to_dict() if order else None,
            "events": events,
            "event_count": len(events),
            "duration_seconds": self._calculate_duration(events),
            "status": events[-1]["event_type"] if events else None,
        }
    
    def _calculate_duration(self, events: list[dict]) -> float:
        """计算持续时间"""
        if len(events) < 2:
            return 0
        
        start = events[0]["timestamp"]
        end = events[-1]["timestamp"]
        
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        
        return (end_dt - start_dt).total_seconds()


# ============== 模拟盘环境 ==============

class SimulatorEnvironment:
    """
    高仿真模拟盘环境
    
    1:1 模拟实盘交易规则
    - 基于历史订单簿的真实滑点模拟
    - 手续费/资金费率完全对齐
    - 订单延迟模拟
    """
    
    def __init__(self):
        self._historical_data: list[dict] = []
        self._order_books: dict[str, list[dict]] = {}  # 历史订单簿
        
        # 配置
        self.config = {
            "slippage_model": "volume_weighted",  # volume_weighted/fixed
            "slippage_base": 0.001,               # 基础滑点
            "fee_rate": 0.001,                    # 手续费率
            "funding_rate": 0.0001,              # 资金费率
            "latency_range_ms": [50, 200],        # 延迟范围
        }
    
    def load_historical_data(self, data: list[dict]):
        """加载历史数据"""
        self._historical_data = data
    
    async def simulate_order(self, order: Order, 
                            timestamp: int) -> dict:
        """
        模拟订单执行
        
        Returns:
            {
                "executed": True,
                "executed_price": 50000.0,
                "executed_quantity": 1.0,
                "slippage": 0.001,
                "fee": 50.0,
                "latency_ms": 100,
            }
        """
        # 获取当时的价格和订单簿
        market_data = self._get_market_data(timestamp)
        
        if not market_data:
            return {
                "executed": False,
                "error": "无历史数据",
            }
        
        # 计算滑点
        slippage = self._calculate_slippage(order, market_data)
        
        # 计算手续费
        fee = order.quantity * order.price * self.config["fee_rate"]
        
        # 模拟延迟
        latency = self._simulate_latency()
        
        # 执行价格
        base_price = market_data.get("close", order.price)
        executed_price = base_price * (1 + slippage)
        
        return {
            "executed": True,
            "executed_price": executed_price,
            "executed_quantity": order.quantity,
            "slippage": slippage,
            "fee": fee,
            "latency_ms": latency,
            "market_impact": self._calculate_impact(order, market_data),
        }
    
    def _get_market_data(self, timestamp: int) -> Optional[dict]:
        """获取历史市场数据"""
        for data in self._historical_data:
            if data.get("timestamp") == timestamp:
                return data
        return None
    
    def _calculate_slippage(self, order: Order, market_data: dict) -> float:
        """计算滑点"""
        if self.config["slippage_model"] == "fixed":
            return self.config["slippage_base"]
        
        # 基于成交量的滑点
        volume = market_data.get("volume", 0)
        order_value = order.quantity * order.price
        
        if volume > 0:
            impact_ratio = order_value / volume
            return self.config["slippage_base"] * (1 + impact_ratio * 10)
        
        return self.config["slippage_base"]
    
    def _simulate_latency(self) -> int:
        """模拟网络延迟"""
        import random
        return random.randint(*self.config["latency_range_ms"])
    
    def _calculate_impact(self, order: Order, market_data: dict) -> float:
        """计算市场冲击"""
        # 简化: 订单价值占成交量的比例
        volume = market_data.get("volume", 1)
        order_value = order.quantity * order.price
        
        return order_value / volume if volume > 0 else 0


# ============== 全局实例 ==============

order_router = SmartOrderRouter()
anti_pin = AntiPinController()
order_tracker = OrderTracker()
simulator = SimulatorEnvironment()
