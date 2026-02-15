"""
OpenTrade 数据模型 - 交易相关
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID

from opentrade.core.database import Base


class TradeSide(str, Enum):
    """交易方向"""
    LONG = "long"
    SHORT = "short"


class TradeAction(str, Enum):
    """交易动作"""
    OPEN = "open"
    CLOSE = "close"
    ADD = "add"
    REDUCE = "reduce"


class TradeStatus(str, Enum):
    """交易状态"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class CloseReason(str, Enum):
    """平仓原因"""
    MANUAL = "manual"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    LIQUIDATION = "liquidation"
    TIMEOUT = "timeout"
    REVERSAL = "reversal"


class Trade(Base):
    """交易记录"""

    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 基础信息
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(30), nullable=False, default="binance")

    # 交易详情
    side = Column(SQLEnum(TradeSide), nullable=False)
    action = Column(SQLEnum(TradeAction), nullable=False)
    status = Column(SQLEnum(TradeStatus), nullable=False, default=TradeStatus.PENDING)

    # 价格与数量
    entry_price = Column(Float)
    exit_price = Column(Float)
    quantity = Column(Float)
    leverage = Column(Integer, default=1)

    # 盈亏
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    fee = Column(Float, default=0.0)

    # 时间
    entry_time = Column(DateTime(timezone=True))
    exit_time = Column(DateTime(timezone=True))
    duration_minutes = Column(Integer)

    # 平仓原因
    close_reason = Column(SQLEnum(CloseReason))

    # 策略信息
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    strategy_version = Column(String(20))

    # 市场快照 (JSON)
    market_snapshot = Column(Text)  # JSON string

    # 信号信息
    signal_id = Column(String(50))
    signal_confidence = Column(Float)

    # 备注
    notes = Column(Text)

    # 时间戳
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True)

    def __repr__(self):
        return f"<Trade {self.symbol} {self.side.value} {self.action.value} {self.quantity}@{self.entry_price}>"

    @property
    def is_long(self) -> bool:
        return self.side == TradeSide.LONG

    @property
    def is_short(self) -> bool:
        return self.side == TradeSide.SHORT

    @property
    def is_win(self) -> bool:
        return self.pnl and self.pnl > 0

    @property
    def is_loss(self) -> bool:
        return self.pnl and self.pnl < 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "action": self.action.value,
            "status": self.status.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "fee": self.fee,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "duration_minutes": self.duration_minutes,
            "close_reason": self.close_reason.value if self.close_reason else None,
            "strategy_id": str(self.strategy_id) if self.strategy_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
