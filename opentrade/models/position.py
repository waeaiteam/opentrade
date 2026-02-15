"""
OpenTrade 数据模型 - 仓位相关
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from opentrade.core.database import Base


class PositionSide(str, Enum):
    """仓位方向"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class PositionStatus(str, Enum):
    """仓位状态"""
    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class Position(Base):
    """持仓记录"""
    
    __tablename__ = "positions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 基础信息
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(30), nullable=False, default="binance")
    
    # 仓位方向
    side = Column(SQLEnum(PositionSide), nullable=False, default=PositionSide.LONG)
    status = Column(SQLEnum(PositionStatus), nullable=False, default=PositionStatus.OPEN)
    
    # 持仓信息
    size = Column(Float, nullable=False, default=0.0)  # 持仓数量
    entry_price = Column(Float, nullable=False)  # 平均入场价
    mark_price = Column(Float)  # 标记价格
    liquidation_price = Column(Float)  # 强平价格
    
    # 杠杆与保证金
    leverage = Column(Integer, default=1)
    margin = Column(Float, default=0.0)  # 保证金
    isolated_margin = Column(Float, default=0.0)
    maintenance_margin = Column(Float, default=0.0)
    
    # 止盈止损
    stop_loss = Column(Float)
    take_profit = Column(Float)
    trailing_stop = Column(Float)
    trailing_stop_activation = Column(Float)
    trailing_stop_callback_rate = Column(Float)
    
    # 未实现盈亏
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_percent = Column(Float, default=0.0)
    accumulated_funding = Column(Float, default=0.0)  # 累计资金费
    
    # 时间信息
    opened_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime(timezone=True))
    
    # 策略信息
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    
    # 关联的交易
    trades = relationship("Trade", back_populates="position", lazy="dynamic")
    
    def __repr__(self):
        return f"<Position {self.symbol} {self.side.value} {self.size}@{self.entry_price}>"
    
    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG
    
    @property
    def is_short(self) -> bool:
        return self.side == PositionSide.SHORT
    
    @property
    def is_profitable(self) -> bool:
        return self.unrealized_pnl and self.unrealized_pnl > 0
    
    @property
    def is_loss(self) -> bool:
        return self.unrealized_pnl and self.unrealized_pnl < 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "status": self.status.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "leverage": self.leverage,
            "margin": self.margin,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_percent": self.unrealized_pnl_percent,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
