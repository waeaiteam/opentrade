"""
OpenTrade 数据模型 - 策略相关
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from opentrade.core.database import Base


class StrategyStatus(str, Enum):
    """策略状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    TESTING = "testing"
    ARCHIVED = "archived"


class StrategyType(str, Enum):
    """策略类型"""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    GRID_TRADING = "grid_trading"
    SCALPING = "scalping"
    CUSTOM = "custom"


class Strategy(Base):
    """交易策略"""
    
    __tablename__ = "strategies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 基础信息
    name = Column(String(100), nullable=False)
    version = Column(String(20), nullable=False, default="1.0.0")
    description = Column(Text)
    strategy_type = Column(SQLEnum(StrategyType), nullable=False)
    status = Column(SQLEnum(StrategyStatus), nullable=False, default=StrategyStatus.INACTIVE)
    
    # 策略配置 (JSON)
    parameters = Column(Text)  # JSON string
    
    # 性能指标
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    
    # 版本控制
    parent_id = Column(UUID(as_uuid=True), nullable=True)
    mutation_log = Column(Text)  # JSON string
    
    # 时间
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True))
    
    # 激活状态
    is_default = Column(Boolean, default=False)
    
    # 代码位置 (对于自定义策略)
    code_path = Column(String(255))
    
    def __repr__(self):
        return f"<Strategy {self.name} v{self.version}>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        import json
        
        return {
            "id": str(self.id),
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.strategy_type.value,
            "status": self.status.value,
            "parameters": json.loads(self.parameters) if self.parameters else {},
            "performance": {
                "win_rate": self.win_rate,
                "profit_factor": self.profit_factor,
                "sharpe_ratio": self.sharpe_ratio,
                "max_drawdown": self.max_drawdown,
                "total_trades": self.total_trades,
                "total_pnl": self.total_pnl,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class StrategyVersion(Base):
    """策略版本历史"""
    
    __tablename__ = "strategy_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 关联策略
    strategy_id = Column(UUID(as_uuid=True), nullable=False)
    
    # 版本信息
    version = Column(String(20), nullable=False)
    
    # 配置快照
    parameters = Column(Text)  # JSON string
    
    # 性能快照
    performance = Column(Text)  # JSON string
    
    # 变更说明
    change_notes = Column(Text)
    
    # 血缘
    parent_version = Column(String(20))
    genetic_parents = Column(Text)  # JSON string array
    
    # 时间
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class StrategyEvolution(Base):
    """策略进化记录"""
    
    __tablename__ = "strategy_evolutions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 关联策略
    strategy_id = Column(UUID(as_uuid=True), nullable=False)
    
    # 进化代数
    generation = Column(Integer, nullable=False)
    
    # 进化类型
    evolution_type = Column(String(50))  # mutation, crossover, selection
    
    # 变更详情
    changes = Column(Text)  # JSON string
    
    # 性能变化
    before_performance = Column(Text)  # JSON
    after_performance = Column(Text)  # JSON
    
    # 评估结果
    improved = Column(Boolean)
    improvement_percent = Column(Float)
    
    # 时间
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
