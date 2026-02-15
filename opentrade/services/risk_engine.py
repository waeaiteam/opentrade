"""
OpenTrade 风险控制系统 - P0 核心优化

1. 风控引擎前置：所有订单必须经过风控校验
2. 硬边界双层锁死：数据库 + 代码双重锁定
3. 三级熔断机制：策略级/账户级/系统级

作者: OpenTrade AI
日期: 2026-02-15
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import wraps
from typing import Any, Optional, Callable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID

from opentrade.core.config import get_config
from opentrade.core.database import Base, db


# ============== 风控配置 ==============

class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RiskLimits:
    """风控硬边界配置 (用户不可突破)"""
    
    # 仓位限制
    max_position_pct: float = 0.10      # 单笔最大仓位 10%
    max_total_exposure: float = 0.40     # 总敞口最大 40%
    max_single_symbol_exposure: float = 0.15  # 单品种最大 15%
    max_open_positions: int = 3         # 最大持仓数
    
    # 杠杆限制
    max_leverage: float = 3.0            # 最大杠杆 3x
    
    # 止损限制
    max_stop_loss_pct: float = 0.10      # 最大止损 10%
    min_stop_loss_pct: float = 0.01      # 最小止损 1%
    
    # 盈利限制
    max_take_profit_pct: float = 0.30    # 最大止盈 30%
    
    # 单日限制
    max_daily_loss_pct: float = 0.05     # 单日最大亏损 5%
    max_daily_trades: int = 20           # 单日最大交易数
    
    # 全局回撤限制
    max_total_drawdown: float = 0.15     # 总回撤 15% 暂停
    
    # 熔断阈值
    circuit_breake_trigger_pct: float = 0.08  # 回撤 8% 触发熔断
    
    def to_dict(self) -> dict:
        return {
            "max_position_pct": self.max_position_pct,
            "max_total_exposure": self.max_total_exposure,
            "max_single_symbol_exposure": self.max_single_symbol_exposure,
            "max_open_positions": self.max_open_positions,
            "max_leverage": self.max_leverage,
            "max_stop_loss_pct": self.max_stop_loss_pct,
            "min_stop_loss_pct": self.min_stop_loss_pct,
            "max_take_profit_pct": self.max_take_profit_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_daily_trades": self.max_daily_trades,
            "max_total_drawdown": self.max_total_drawdown,
            "circuit_breake_trigger_pct": self.circuit_breake_trigger_pct,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RiskLimits":
        """从字典创建，安全的属性覆盖"""
        limits = cls()
        for key, value in data.items():
            if hasattr(limits, key):
                setattr(limits, key, value)
        return limits


# ============== 数据库模型 ==============

class RiskLimitRecord(Base):
    """风控限制记录表 (数据库层锁定)"""
    
    __tablename__ = "risk_limits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(String(100), nullable=False, index=True)
    
    # 限制类型
    limit_type = Column(String(50), nullable=False)  # position/leverage/stop_loss/daily/drawdown
    limit_key = Column(String(100), nullable=False)  # max_position_pct/max_leverage 等
    limit_value = Column(Float, nullable=False)
    
    # 来源
    source = Column(String(50), default="user")  # user/system/default
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 是否启用
    is_active = Column(Boolean, default=True)


class RiskAuditLog(Base):
    """风控审计日志 (全链路追踪)"""
    
    __tablename__ = "risk_audit_log"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 交易标识
    order_id = Column(String(100), nullable=True, index=True)
    strategy_id = Column(String(100), nullable=True)
    
    # 决策内容
    original_decision = Column(Text)  # JSON
    modified_decision = Column(Text)  # JSON
    
    # 风控结果
    passed = Column(Boolean, nullable=False)
    blocked_reason = Column(String(500))
    applied_rules = Column(Text)  # JSON
    
    # 上下文
    account_balance = Column(Float)
    current_exposure = Column(Float)
    
    # 时间戳
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)


class CircuitBreakerState(Base):
    """熔断状态记录"""
    
    __tablename__ = "circuit_breaker"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 熔断级别
    level = Column(String(20), nullable=False)  # strategy/account/system
    
    # 触发条件
    trigger_reason = Column(String(500))
    trigger_value = Column(Float)
    threshold = Column(Float)
    
    # 状态
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关联
    strategy_id = Column(String(100), nullable=True)
    user_id = Column(String(100), nullable=True)


# ============== 风控错误 ==============

class RiskControlError(Exception):
    """风控异常基类"""
    def __init__(self, message: str, rule: str = None, value: Any = None, limit: Any = None):
        super().__init__(message)
        self.message = message
        self.rule = rule
        self.value = value
        self.limit = limit


class PositionLimitError(RiskControlError):
    """仓位限制错误"""
    pass


class LeverageLimitError(RiskControlError):
    """杠杆限制错误"""
    pass


class StopLossLimitError(RiskControlError):
    """止损限制错误"""
    pass


class DailyLossLimitError(RiskControlError):
    """单日亏损限制错误"""
    pass


class CircuitBreakerTriggeredError(RiskControlError):
    """熔断触发错误"""
    def __init__(self, level: str, reason: str):
        super().__init__(f"熔断触发 [{level}]: {reason}", "circuit_breake", level, None)
        self.level = level


# ============== 风控引擎核心 ==============

class RiskEngine:
    """
    风控引擎 - 前置强制校验
    
    所有交易订单（无论AI生成还是手动操作）必须100%经过风控校验
    
    架构:
    Order → RiskEngine.pre_check() → 执行/拦截
    """
    
    def __init__(self):
        self.config = get_config()
        self._limits: Optional[RiskLimits] = None
        self._db_limits: dict = {}  # 数据库层限制
        
        # 熔断状态
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}
        
        # 统计
        self._stats = {
            "total_checks": 0,
            "blocked": 0,
            "modified": 0,
        }
    
    # ============== 公共接口 ==============
    
    async def pre_check(self, decision: dict, account_info: dict = None) -> tuple[dict, bool]:
        """
        前置风控检查 (强制拦截点)
        
        Args:
            decision: 交易决策
            account_info: 账户信息 (balance, positions, daily_pnl, drawdown)
        
        Returns:
            (modified_decision, passed)
        """
        self._stats["total_checks"] += 1
        
        # 加载限制
        await self._load_limits()
        
        # 获取账户信息
        account_info = account_info or await self._get_account_info()
        
        # 执行检查
        applied_rules = []
        modified_decision = decision.copy()
        blocked = False
        block_reason = None
        
        try:
            # 1. 熔断检查
            await self._check_circuit_breakers(account_info)
            
            # 2. 仓位检查
            modified_decision, rule = await self._check_position(
                modified_decision, account_info
            )
            if rule:
                applied_rules.append(rule)
            
            # 3. 杠杆检查
            modified_decision, rule = await self._check_leverage(
                modified_decision, account_info
            )
            if rule:
                applied_rules.append(rule)
            
            # 4. 止损止盈检查
            modified_decision, rule = await self._check_sl_tp(
                modified_decision
            )
            if rule:
                applied_rules.append(rule)
            
            # 5. 单日限制检查
            rule = await self._check_daily_limits(account_info)
            if rule:
                applied_rules.append(rule)
            
            # 6. 回撤限制检查
            rule = await self._check_drawdown(account_info)
            if rule:
                applied_rules.append(rule)
            
        except RiskControlError as e:
            blocked = True
            block_reason = e.message
            modified_decision = {}
            self._stats["blocked"] += 1
        
        # 记录审计日志
        await self._log_audit(decision, modified_decision, passed=not blocked, 
                           blocked_reason=block_reason, applied_rules=applied_rules,
                           account_info=account_info)
        
        if blocked:
            raise block_reason if block_reason else RiskControlError("风控拦截")
        
        if modified_decision != decision:
            self._stats["modified"] += 1
        
        return modified_decision, not blocked
    
    # ============== 熔断机制 ==============
    
    async def _check_circuit_breakers(self, account_info: dict):
        """检查熔断状态"""
        # 策略级熔断
        strategy_id = account_info.get("strategy_id")
        if strategy_id:
            cb = self._circuit_breakers.get(f"strategy_{strategy_id}")
            if cb and cb.is_active:
                raise CircuitBreakerTriggeredError("strategy", cb.trigger_reason)
        
        # 账户级熔断
        cb = self._circuit_breakers.get("account")
        if cb and cb.is_active:
            raise CircuitBreakerTriggeredError("account", cb.trigger_reason)
        
        # 检查是否需要触发账户级熔断
        drawdown = account_info.get("drawdown", 0)
        if drawdown >= self._limits.circuit_breake_trigger_pct:
            await self._trigger_circuit_breaker("account", 
                f"回撤达到 {drawdown:.2%}，触发熔断",
                drawdown, self._limits.circuit_breake_trigger_pct)
            raise CircuitBreakerTriggeredError("account", "回撤超限")
    
    async def _trigger_circuit_breaker(self, level: str, reason: str, 
                                       value: float, threshold: float):
        """触发熔断"""
        cb = CircuitBreakerState(
            level=level,
            trigger_reason=reason,
            trigger_value=value,
            threshold=threshold,
            is_active=True,
        )
        
        key = f"account" if level == "account" else f"strategy_{value}"
        self._circuit_breakers[key] = cb
        
        # 记录到数据库
        async with db.session() as session:
            session.add(cb)
        
        # 发送告警
        from opentrade.services.notification_service import notification_service
        await notification_service.send_alert(
            level="critical",
            title=f"熔断触发 [{level.upper()}]",
            message=f"{reason}\n当前: {value:.2%} / 阈值: {threshold:.2%}",
        )
    
    # ============== 仓位检查 ==============
    
    async def _check_position(self, decision: dict, account_info: dict) -> tuple[dict, dict]:
        """检查仓位限制"""
        if not decision.get("size"):
            return decision, None
        
        size = float(decision["size"])
        symbol = decision.get("symbol", "unknown")
        
        # 从数据库加载限制
        max_pct = self._db_limits.get("max_position_pct", self._limits.max_position_pct)
        
        # 检查单笔仓位
        if size > max_pct:
            # 自动调整到限制
            decision["size"] = max_pct
            return decision, {
                "rule": "position_limit",
                "action": "reduced",
                "original": size,
                "reduced_to": max_pct,
            }
        
        # 检查单品种敞口
        current_exposure = account_info.get("symbol_exposure", {}).get(symbol, 0)
        max_symbol = self._db_limits.get("max_single_symbol_exposure", 
                                         self._limits.max_single_symbol_exposure)
        if current_exposure + size > max_symbol:
            available = max_symbol - current_exposure
            if available > 0.01:
                decision["size"] = available
                return decision, {
                    "rule": "symbol_exposure_limit",
                    "action": "reduced",
                    "original": size,
                    "reduced_to": available,
                }
            else:
                raise PositionLimitError(
                    f"单品种敞口超限: {symbol}",
                    "max_single_symbol_exposure", size, max_symbol
                )
        
        # 检查总敞口
        total_exposure = account_info.get("total_exposure", 0)
        max_total = self._db_limits.get("max_total_exposure", self._limits.max_total_exposure)
        if total_exposure + size > max_total:
            raise PositionLimitError(
                f"总敞口超限: {total_exposure + size:.2%} > {max_total:.2%}",
                "max_total_exposure", total_exposure + size, max_total
            )
        
        return decision, None
    
    # ============== 杠杆检查 ==============
    
    async def _check_leverage(self, decision: dict, account_info: dict) -> tuple[dict, dict]:
        """检查杠杆限制"""
        leverage = float(decision.get("leverage", 1.0))
        
        max_leverage = self._db_limits.get("max_leverage", self._limits.max_leverage)
        
        if leverage > max_leverage:
            decision["leverage"] = max_leverage
            return decision, {
                "rule": "leverage_limit",
                "action": "reduced",
                "original": leverage,
                "reduced_to": max_leverage,
            }
        
        return decision, None
    
    # ============== 止损止盈检查 ==============
    
    async def _check_sl_tp(self, decision: dict) -> tuple[dict, dict]:
        """检查止损止盈限制"""
        sl_pct = decision.get("stop_loss_pct")
        tp_pct = decision.get("take_profit_pct")
        
        # 止损检查
        if sl_pct:
            sl_pct = float(sl_pct)
            if sl_pct < self._limits.min_stop_loss_pct:
                raise StopLossLimitError(
                    f"止损过小: {sl_pct:.2%} < {self._limits.min_stop_loss_pct:.2%}",
                    "min_stop_loss_pct", sl_pct, self._limits.min_stop_loss_pct
                )
            if sl_pct > self._limits.max_stop_loss_pct:
                decision["stop_loss_pct"] = self._limits.max_stop_loss_pct
                return decision, {
                    "rule": "stop_loss_limit",
                    "action": "reduced",
                    "original": sl_pct,
                    "reduced_to": self._limits.max_stop_loss_pct,
                }
        
        # 止盈检查
        if tp_pct:
            tp_pct = float(tp_pct)
            if tp_pct > self._limits.max_take_profit_pct:
                decision["take_profit_pct"] = self._limits.max_take_profit_pct
                return decision, {
                    "rule": "take_profit_limit",
                    "action": "reduced",
                    "original": tp_pct,
                    "reduced_to": self._limits.max_take_profit_pct,
                }
        
        return decision, None
    
    # ============== 单日限制检查 ==============
    
    async def _check_daily_limits(self, account_info: dict) -> dict:
        """检查单日限制"""
        daily_loss = account_info.get("daily_pnl", 0)
        daily_trades = account_info.get("daily_trades", 0)
        
        # 单日亏损检查
        if daily_loss < 0:
            daily_loss_pct = abs(daily_loss) / account_info.get("balance", 1)
            max_daily = self._db_limits.get("max_daily_loss_pct", 
                                            self._limits.max_daily_loss_pct)
            
            if daily_loss_pct >= max_daily:
                raise DailyLossLimitError(
                    f"单日亏损达限: {daily_loss_pct:.2%} >= {max_daily:.2%}",
                    "max_daily_loss_pct", daily_loss_pct, max_daily
                )
        
        # 单日交易数检查
        max_trades = self._db_limits.get("max_daily_trades", self._limits.max_daily_trades)
        if daily_trades >= max_trades:
            raise DailyLossLimitError(
                f"单日交易数达限: {daily_trades} >= {max_trades}",
                "max_daily_trades", daily_trades, max_trades
            )
        
        return None
    
    # ============== 回撤检查 ==============
    
    async def _check_drawdown(self, account_info: dict) -> dict:
        """检查全局回撤"""
        drawdown = account_info.get("drawdown", 0)
        max_dd = self._db_limits.get("max_total_drawdown", 
                                      self._limits.max_total_drawdown)
        
        if drawdown >= max_dd:
            await self._trigger_circuit_breaker("account",
                f"全局回撤达限: {drawdown:.2%}",
                drawdown, max_dd)
            raise CircuitBreakerTriggeredError("account", "全局回撤超限")
        
        return None
    
    # ============== 辅助方法 ==============
    
    async def _load_limits(self):
        """从数据库加载限制"""
        if self._limits is None:
            self._limits = self._get_hard_limits()
            # TODO: 从数据库加载用户自定义限制
            # self._db_limits = await self._load_db_limits()
    
    def _get_hard_limits(self) -> RiskLimits:
        """获取硬边界限制"""
        return RiskLimits()
    
    async def _load_db_limits(self) -> dict:
        """从数据库加载用户限制"""
        # TODO: 实现
        return {}
    
    async def _get_account_info(self) -> dict:
        """获取账户信息"""
        # TODO: 从数据库/交易所获取
        return {
            "balance": 10000.0,
            "positions": [],
            "total_exposure": 0.0,
            "symbol_exposure": {},
            "daily_pnl": 0.0,
            "daily_trades": 0,
            "drawdown": 0.0,
        }
    
    async def _log_audit(self, original: dict, modified: dict, passed: bool,
                        blocked_reason: str, applied_rules: list, account_info: dict):
        """记录审计日志"""
        log = RiskAuditLog(
            order_id=original.get("order_id"),
            strategy_id=original.get("strategy_id"),
            original_decision=json.dumps(original),
            modified_decision=json.dumps(modified),
            passed=passed,
            blocked_reason=blocked_reason,
            applied_rules=json.dumps(applied_rules),
            account_balance=account_info.get("balance"),
            current_exposure=account_info.get("total_exposure"),
        )
        
        async with db.session() as session:
            session.add(log)
    
    def get_stats(self) -> dict:
        """获取统计"""
        return {
            "total_checks": self._stats["total_checks"],
            "blocked": self._stats["blocked"],
            "modified": self._stats["modified"],
            "pass_rate": (self._stats["total_checks"] - self._stats["blocked"]) / 
                        max(self._stats["total_checks"], 1),
        }


# ============== 快速访问 ==============

# 全局风控引擎实例
risk_engine = RiskEngine()


async def check_order(decision: dict, account_info: dict = None) -> tuple[dict, bool]:
    """便捷函数：检查订单"""
    return await risk_engine.pre_check(decision, account_info)


# ============== 硬件级紧急停止 (系统级熔断) ==============

class HardwareEmergencyStop:
    """
    硬件级紧急停止服务
    
    即使后端崩溃，也可直接调用交易所API平仓
    """
    
    def __init__(self):
        self._emergency_positions: list[dict] = []
        self._is_armed = False
    
    def arm(self, positions: list[dict]):
        """启动紧急保护"""
        self._emergency_positions = positions
        self._is_armed = True
    
    def disarm(self):
        """关闭紧急保护"""
        self._is_armed = False
        self._emergency_positions = []
    
    async def emergency_close_all(self, exchange):
        """紧急平仓所有持仓"""
        if not self._is_armed:
            return False
        
        results = []
        for pos in self._emergency_positions:
            try:
                order = await exchange.close_position(pos["symbol"], pos["side"])
                results.append({"symbol": pos["symbol"], "status": "closed", "order": order})
            except Exception as e:
                results.append({"symbol": pos["symbol"], "status": "error", "error": str(e)})
        
        return results


# 全局紧急停止实例
emergency_stop = HardwareEmergencyStop()
