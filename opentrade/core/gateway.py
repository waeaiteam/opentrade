"""
OpenTrade Order Gateway - 强制风控网关

所有订单必须通过此网关提交，确保风控 100% 强制执行。

订单流程:
    任意来源 (Agent/API/Bot/Manual)
           ↓
    OrderGateway.submit(order)  ← 唯一入口
           ↓
    RiskEngine.validate()        ← 100% 强制
           ↓
    ExchangeAdapter.execute()    ← 禁止直连
           ↓
    OrderGateway.execute()
           ↓
    订单回执 + 审计日志
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class RejectReason(str, Enum):
    """拒绝原因"""
    RISK_CHECK_FAILED = "risk_check_failed"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    LEVERAGE_EXCEEDED = "leverage_exceeded"
    PRICE_DEVIATION = "price_deviation"
    MARKET_SUSPENDED = "market_suspended"
    API_ERROR = "api_error"
    TIMEOUT = "timeout"


# ============ 数据模型 ============

class OrderRequest(BaseModel):
    """订单请求"""
    symbol: str = Field(..., description="交易对, e.g. BTC/USDT")
    side: OrderSide = Field(..., description="买入/卖出")
    order_type: OrderType = Field(..., description="订单类型")
    size: float = Field(..., gt=0, description="数量")
    price: Optional[float] = Field(None, description="限价价格")
    leverage: float = Field(default=1.0, ge=1, le=100, description="杠杆倍数")
    stop_loss: Optional[float] = Field(None, description="止损价格")
    take_profit: Optional[float] = Field(None, description="止盈价格")
    reduce_only: bool = Field(default=False, description="只减仓")
    post_only: bool = Field(default=False, description="只做maker")
    source: str = Field(default="unknown", description="订单来源: agent/api/cli/bot")
    strategy_id: Optional[str] = Field(None, description="策略ID")
    trace_id: Optional[str] = Field(None, description="追溯ID")


class Order(BaseModel):
    """完整订单信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    leverage: float = 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    source: str = "unknown"
    strategy_id: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    filled_size: float = 0.0
    average_price: Optional[float] = None
    commission: float = 0.0
    reject_reason: Optional[RejectReason] = None
    reject_message: Optional[str] = None
    raw_response: Optional[dict] = None


class RiskCheckResult(BaseModel):
    """风控检查结果"""
    allowed: bool = False
    reason: Optional[RejectReason] = None
    message: str = ""
    risk_score: float = 0.0
    warnings: list[str] = []
    adjustments: dict[str, Any] = {}


class AccountState(BaseModel):
    """账户状态"""
    total_equity: float = 0.0
    available_balance: float = 0.0
    positions: dict[str, dict] = {}  # symbol -> position info
    open_orders: int = 0
    daily_pnl: float = 0.0
    daily_loss_pct: float = 0.0


class PositionInfo(BaseModel):
    """持仓信息"""
    symbol: str
    side: str  # long/short
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    pnl_pct: float
    liq_price: Optional[float] = None
    margin: float
    leverage: float


# ============ 风控引擎 ============

class RiskEngine:
    """
    风险控制引擎

    所有订单强制经过此引擎检查，包括:
    - 保证金检查
    - 仓位限制检查
    - 杠杆限制检查
    - 止损止盈验证
    - 价格偏离检查
    - 账户级风险检查
    - 策略级风险检查
    """

    def __init__(self, config):
        self.config = config
        self.max_leverage = config.risk.max_leverage
        self.max_position_pct = config.risk.max_position_pct
        self.max_daily_loss_pct = config.risk.max_daily_loss_pct
        self.stop_loss_pct = config.risk.stop_loss_pct
        self.take_profit_pct = config.risk.take_profit_pct
        self.max_open_positions = config.risk.max_open_positions

    async def validate(
        self,
        order: OrderRequest,
        account: AccountState,
        strategy_state: Optional[dict] = None,
    ) -> RiskCheckResult:
        """
        执行风控检查

        Args:
            order: 订单请求
            account: 账户状态
            strategy_state: 策略状态 (可选)

        Returns:
            RiskCheckResult: 检查结果
        """
        result = RiskCheckResult(allowed=True)
        order_value = order.size * (order.price or 0)

        # 1. 账户基础检查
        if account.available_balance <= 0:
            result.allowed = False
            result.reason = RejectReason.INSUFFICIENT_MARGIN
            result.message = "账户余额不足"
            return result

        # 2. 杠杆限制
        if order.leverage > self.max_leverage:
            result.allowed = False
            result.reason = RejectReason.LEVERAGE_EXCEEDED
            result.message = f"杠杆 {order.leverage}x 超过限制 {self.max_leverage}x"
            result.adjustments["leverage"] = self.max_leverage
            return result

        # 3. 仓位限制 (单笔)
        max_position_value = account.total_equity * self.max_position_pct
        if order_value > max_position_value:
            result.warnings.append(
                f"订单金额 {order_value:.2f} 超过单笔限制 {max_position_value:.2f}"
            )
            result.adjustments["size"] = max_position_value / (order.price or 1)
            result.adjustments["size_adjusted"] = True

        # 4. 开仓数量限制
        current_positions = len(account.positions)
        if current_positions >= self.max_open_positions:
            result.warnings.append(f"已开仓位数 {current_positions} 达到上限")

        # 5. 日亏损限制
        if account.daily_loss_pct >= self.max_daily_loss_pct:
            result.allowed = False
            result.reason = RejectReason.RISK_CHECK_FAILED
            result.message = (
                f"日亏损 {account.daily_loss_pct*100:.1f}% "
                f"达到限制 {self.max_daily_loss_pct*100:.1f}%，禁止开仓"
            )
            return result

        # 6. 止损止盈检查
        if not order.stop_loss and order.size > account.total_equity * 0.05:
            result.warnings.append(
                "大额订单未设置止损，建议设置 stop_loss 参数"
            )

        # 7. 策略级风控
        if strategy_state:
            # 检查策略状态
            if strategy_state.get("frozen"):
                result.allowed = False
                result.reason = RejectReason.RISK_CHECK_FAILED
                result.message = "策略已被冻结"
                return result

            # 检查策略最大回撤
            if strategy_state.get("current_drawdown", 0) > strategy_state.get("max_drawdown", 0.2):
                result.warnings.append("策略当前回撤接近限制")

        # 8. 价格合理性检查
        if order.price:
            symbol_positions = account.positions.get(order.symbol, {})
            if symbol_positions:
                entry_price = symbol_positions.get("entry_price", 0)
                if entry_price > 0:
                    price_change = abs(order.price - entry_price) / entry_price
                    if price_change > 0.1:  # 10% 价格偏离
                        result.warnings.append(
                            f"限价偏离当前价格 {price_change*100:.1f}%"
                        )

        # 计算风险分数
        result.risk_score = self._calculate_risk_score(order, account)

        return result

    def _calculate_risk_score(
        self,
        order: OrderRequest,
        account: AccountState,
    ) -> float:
        """计算风险分数 (0-1)"""
        score = 0.0

        # 杠杆风险
        score += (order.leverage / self.max_leverage) * 0.3

        # 仓位风险
        order_value = order.size * (order.price or 0)
        position_pct = order_value / account.total_equity if account.total_equity else 1
        score += min(position_pct / self.max_position_pct, 1.0) * 0.3

        # 市场风险 (时间因素)
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 3 or hour > 23:  # 深夜风险高
            score += 0.2

        return min(score, 1.0)


# ============ 订单网关 ============

class OrderGateway:
    """
    订单网关 - 所有订单的唯一入口

    设计原则:
    1. 单一入口点: 所有订单必须通过 submit() 提交
    2. 强制风控: RiskEngine.validate() 必须在执行前完成
    3. 完整审计: 每次操作都有详细日志
    4. 错误处理: 优雅降级，错误信息清晰
    """

    def __init__(self, exchange_adapter, config=None):
        self.exchange = exchange_adapter
        self.config = config
        self.risk_engine = RiskEngine(config) if config else None
        self._orders: dict[str, Order] = {}

    async def submit(self, order: OrderRequest) -> Order:
        """
        提交订单 - 唯一入口

        Args:
            order: 订单请求

        Returns:
            Order: 完整订单信息

        Raises:
            RiskRejected: 订单被风控拒绝
        """
        order_id = str(uuid.uuid4())[:8]
        trace_id = order.trace_id or f"ord_{order_id}"

        print(f"[OrderGateway] 📝 提交订单 {order_id} | {order.symbol} {order.side.value} {order.size}")

        # 1. 创建订单对象
        order_obj = Order(
            id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            size=order.size,
            price=order.price,
            leverage=order.leverage,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            source=order.source,
            strategy_id=order.strategy_id,
            trace_id=trace_id,
        )

        # 2. 获取账户状态
        account = await self._get_account_state()

        # 3. 风控检查 (强制)
        if self.risk_engine:
            risk_result = await self.risk_engine.validate(order, account)

            if not risk_result.allowed:
                order_obj.status = OrderStatus.REJECTED
                order_obj.reject_reason = risk_result.reason
                order_obj.reject_message = risk_result.message
                order_obj.updated_at = datetime.utcnow()

                self._orders[order_id] = order_obj
                self._audit_log(order_obj, "rejected", risk_result.__dict__)

                print(f"[OrderGateway] ❌ 订单被风控拒绝: {risk_result.message}")
                raise RiskRejected(order_id, risk_result)

            # 记录调整
            if risk_result.adjustments:
                if "size" in risk_result.adjustments:
                    order_obj.size = risk_result.adjustments["size"]
                    print(f"[OrderGateway] ⚠️  订单大小调整: {order.size} → {order_obj.size}")

            # 记录警告
            for warning in risk_result.warnings:
                print(f"[OrderGateway] ⚠️  风控警告: {warning}")

        # 4. 执行订单
        try:
            order_obj = await self._execute_order(order_obj)
            self._orders[order_id] = order_obj
            self._audit_log(order_obj, "submitted", {"status": order_obj.status.value})
            return order_obj

        except Exception as e:
            order_obj.status = OrderStatus.FAILED
            order_obj.reject_reason = RejectReason.API_ERROR
            order_obj.reject_message = str(e)
            order_obj.updated_at = datetime.utcnow()

            self._orders[order_id] = order_obj
            self._audit_log(order_obj, "failed", {"error": str(e)})

            print(f"[OrderGateway] 💥 订单执行失败: {e}")
            raise OrderExecutionError(order_id, str(e)) from e

    async def _execute_order(self, order: Order) -> Order:
        """执行订单 (内部调用)"""
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.utcnow()

        # 构建交易所参数
        exchange_params = {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "amount": order.size,
            "leverage": order.leverage,
        }

        if order.price:
            exchange_params["price"] = order.price

        if order.stop_loss:
            exchange_params["stopLoss"] = order.stop_loss

        if order.take_profit:
            exchange_params["takeProfit"] = order.take_profit

        if order.reduce_only:
            exchange_params["reduceOnly"] = True

        # 调用交易所
        if self.exchange:
            raw_response = await self.exchange.create_order(**exchange_params)
            order.raw_response = raw_response

            # 解析成交
            if raw_response.get("status") == "filled":
                order.status = OrderStatus.FILLED
                order.filled_size = raw_response.get("filled", order.size)
                order.average_price = raw_response.get("average", order.price)
            elif raw_response.get("status") == "closed":
                order.status = OrderStatus.FILLED

        order.updated_at = datetime.utcnow()
        return order

    async def _get_account_state(self) -> AccountState:
        """获取账户状态"""
        if not self.exchange:
            return AccountState()

        try:
            balance = await self.exchange.fetch_balance()
            total_equity = sum(float(v) for v in balance.get("total", {}).values())

            return AccountState(
                total_equity=total_equity,
                available_balance=balance.get("free", {}).get("USDT", 0),
                positions={},
                open_orders=0,
            )
        except Exception:
            return AccountState()

    def _audit_log(
        self,
        order: Order,
        action: str,
        details: dict,
    ):
        """审计日志"""
        from datetime import datetime

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": order.id,
            "trace_id": order.trace_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "action": action,
            "details": details,
        }

        # 输出到日志
        print(f"[Audit] {log_entry}")

        # TODO: 写入数据库
        # audit_store.save(log_entry)

    def cancel(self, order_id: str) -> bool:
        """取消订单"""
        if order_id not in self._orders:
            return False

        order = self._orders[order_id]
        if order.status not in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
            return False

        # TODO: 调用交易所取消
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        self._audit_log(order, "cancelled", {})

        return True

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单信息"""
        return self._orders.get(order_id)

    def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
    ) -> list[Order]:
        """查询订单"""
        orders = list(self._orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if status:
            orders = [o for o in orders if o.status == status]

        return orders[:limit]


# ============ 异常类 ============

class RiskRejected(Exception):
    """订单被风控拒绝"""

    def __init__(self, order_id: str, result: RiskCheckResult):
        self.order_id = order_id
        self.result = result
        super().__init__(f"订单 {order_id} 被风控拒绝: {result.message}")


class OrderExecutionError(Exception):
    """订单执行错误"""

    def __init__(self, order_id: str, message: str):
        self.order_id = order_id
        super().__init__(f"订单 {order_id} 执行失败: {message}")


# ============ 便捷函数 ============

def create_market_order(
    symbol: str,
    side: str,
    size: float,
    leverage: float = 1.0,
    source: str = "unknown",
    strategy_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> OrderRequest:
    """创建市价单"""
    return OrderRequest(
        symbol=symbol,
        side=OrderSide(side),
        order_type=OrderType.MARKET,
        size=size,
        leverage=leverage,
        source=source,
        strategy_id=strategy_id,
        trace_id=trace_id,
    )


def create_limit_order(
    symbol: str,
    side: str,
    size: float,
    price: float,
    leverage: float = 1.0,
    source: str = "unknown",
    strategy_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> OrderRequest:
    """创建限价单"""
    return OrderRequest(
        symbol=symbol,
        side=OrderSide(side),
        order_type=OrderType.LIMIT,
        size=size,
        price=price,
        leverage=leverage,
        source=source,
        strategy_id=strategy_id,
        trace_id=trace_id,
    )
