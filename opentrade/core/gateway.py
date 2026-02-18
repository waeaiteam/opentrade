"""
风控引擎 - 不可绕过的强制校验层
所有订单必须经过此模块校验，确保风控红线不可突破
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    allowed: bool
    risk_level: RiskLevel
    reason: str
    modifications: Dict[str, Any] = field(default_factory=dict)
    blocked_order: Optional[dict] = None


@dataclass
class RiskConfig:
    """风险配置"""
    # 仓位限制
    max_single_position: float = 0.1          # 单笔最大仓位 10%
    max_total_exposure: float = 0.25            # 总敞口 25%
    max_leverage: float = 2.0                    # 最大杠杆
    
    # 止损限制
    stop_loss_min: float = 0.02                  # 最小止损 2%
    stop_loss_max: float = 0.15                  # 最大止损 15%
    
    # 盈亏限制
    max_single_loss: float = 0.05               # 单笔最大亏损 5%
    max_daily_loss: float = 0.1                  # 单日最大亏损 10%
    max_profit_lock: float = 0.5                 # 止盈锁定 50%
    
    # 风险评分阈值
    risk_score_threshold: float = 70.0           # 风险评分阈值
    
    # 禁止交易时段
    blackout_hours: List[int] = field(default_factory=list)  # 禁止交易时段


class RiskEngine:
    """
    风控引擎 - 所有订单的强制校验层
    
    设计原则:
    1. 不可绕过 - 所有订单必须经过校验
    2. 即时生效 - 配置变更立即生效
    3. 可追溯 - 所有检查有日志
    """
    
    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self._daily_stats = {
            "total_trades": 0,
            "total_loss": 0.0,
            "blocked_orders": 0,
            "last_reset": datetime.now()
        }
        self._circuit_breakers = {}  # 熔断状态
    
    async def check_order(self, order: dict, account_info: dict) -> RiskCheckResult:
        """
        检查订单 - 强制入口
        
        Args:
            order: 订单信息
            account_info: 账户信息
        
        Returns:
            RiskCheckResult: 检查结果
        """
        # 1. 检查黑名单
        check = self._check_blacklist(order)
        if not check.allowed:
            return check
        
        # 2. 检查仓位限制
        check = self._check_position_limits(order, account_info)
        if not check.allowed:
            return check
        
        # 3. 检查杠杆限制
        check = self._check_leverage(order, account_info)
        if not check.allowed:
            return check
        
        # 4. 检查止损设置
        check = self._check_stop_loss(order)
        if not check.allowed:
            return check
        
        # 5. 检查盈亏限制
        check = self._check_profit_loss_limits(order, account_info)
        if not check.allowed:
            return check
        
        # 6. 检查交易时段
        check = self._check_trading_hours()
        if not check.allowed:
            return check
        
        # 7. 检查熔断状态
        check = self._check_circuit_breaker(order)
        if not check.allowed:
            return check
        
        # 8. 计算最终风险评分
        risk_score = self._calculate_risk_score(order, account_info)
        if risk_score > self.config.risk_score_threshold:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=f"风险评分({risk_score})超过阈值({self.config.risk_score_threshold})",
                blocked_order=order
            )
        
        logger.info(f"✅ 订单通过风控: {order.get('symbol', 'unknown')}")
        return RiskCheckResult(
            allowed=True,
            risk_level=RiskLevel.LOW,
            reason="订单通过所有风控检查"
        )
    
    def _check_blacklist(self, order: dict) -> RiskCheckResult:
        """检查黑名单"""
        symbol = order.get("symbol", "").upper()
        # 禁止交易的币种
        blacklist = ["USDT", "DAI", "TUSD"]  # 稳定币禁止杠杆
        
        if symbol in blacklist:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason=f"禁止交易 {symbol}",
                blocked_order=order
            )
        return RiskCheckResult(True, RiskLevel.LOW, "不在黑名单")
    
    def _check_position_limits(self, order: dict, account_info: dict) -> RiskCheckResult:
        """检查仓位限制"""
        size = order.get("size", 0)
        position_value = order.get("position_value", size)
        total_exposure = account_info.get("total_exposure", 0)
        
        # 单笔仓位限制
        if position_value > account_info.get("total_balance", 0) * self.config.max_single_position:
            new_size = account_info.get("total_balance", 0) * self.config.max_single_position
            return RiskCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                reason=f"单笔仓位超限，已调整为 {new_size}",
                modifications={"size": new_size}
            )
        
        # 总敞口限制
        if total_exposure + position_value > account_info.get("total_balance", 0) * self.config.max_total_exposure:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=f"总敞口超限 (当前: {total_exposure}, 限制: {self.config.max_total_exposure})",
                blocked_order=order
            )
        
        return RiskCheckResult(True, RiskLevel.LOW, "仓位检查通过")
    
    def _check_leverage(self, order: dict, account_info: dict) -> RiskCheckResult:
        """检查杠杆限制"""
        leverage = order.get("leverage", 1.0)
        
        if leverage > self.config.max_leverage:
            return RiskCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                reason=f"杠杆({leverage}x)超过限制({self.config.max_leVERAGE}x)，已调整为最大值",
                modifications={"leverage": self.config.max_leverage}
            )
        
        if leverage < 1.0:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason=f"杠杆不能低于1x",
                blocked_order=order
            )
        
        return RiskCheckResult(True, RiskLevel.LOW, "杠杆检查通过")
    
    def _check_stop_loss(self, order: dict) -> RiskCheckResult:
        """检查止损设置"""
        stop_loss = order.get("stop_loss", 0)
        
        if stop_loss == 0 and order.get("action", "").upper() == "BUY":
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason="买入订单必须设置止损",
                blocked_order=order
            )
        
        if 0 < stop_loss < self.config.stop_loss_min:
            return RiskCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                reason=f"止损({stop_loss*100:.1f}%)低于最小限制({self.config.stop_loss_min*100:.1f}%)，已调整",
                modifications={"stop_loss": self.config.stop_loss_min}
            )
        
        if stop_loss > self.config.stop_loss_max:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=f"止损({stop_loss*100:.1f}%)超过最大限制({self.config.stop_loss_max*100:.1f}%)",
                blocked_order=order
            )
        
        return RiskCheckResult(True, RiskLevel.LOW, "止损检查通过")
    
    def _check_profit_loss_limits(self, order: dict, account_info: dict) -> RiskCheckResult:
        """检查盈亏限制"""
        # 检查单日亏损
        if self._daily_stats["total_loss"] >= self.config.max_daily_loss:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason=f"单日亏损已达限制({self.config.max_daily_loss*100:.1f}%)，禁止新订单",
                blocked_order=order
            )
        
        # 检查单笔亏损
        if order.get("risk_amount", 0) > self.config.max_single_loss:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=f"单笔风险金额超限",
                blocked_order=order
            )
        
        return RiskCheckResult(True, RiskLevel.LOW, "盈亏限制检查通过")
    
    def _check_trading_hours(self) -> RiskCheckResult:
        """检查交易时段"""
        current_hour = datetime.now().hour
        
        if current_hour in self.config.blackout_hours:
            return RiskCheckResult(
                allowed=False,
                risk_level=RiskLevel.HIGH,
                reason=f"当前时段({current_hour}:00)禁止交易",
                blocked_order=None
            )
        
        return RiskCheckResult(True, RiskLevel.LOW, "交易时段允许")
    
    def _check_circuit_breaker(self, order: dict) -> RiskCheckResult:
        """检查熔断状态"""
        symbol = order.get("symbol", "")
        
        if symbol in self._circuit_breakers:
            cb = self._circuit_breakers[symbol]
            if cb["triggered"]:
                return RiskCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.CRITICAL,
                    reason=f"熔断触发: {cb['reason']}",
                    blocked_order=order
                )
        
        return RiskCheckResult(True, RiskLevel.LOW, "熔断检查通过")
    
    def _calculate_risk_score(self, order: dict, account_info: dict) -> float:
        """计算风险评分 (0-100)"""
        score = 0.0
        
        # 杠杆权重
        leverage = order.get("leverage", 1.0)
        if leverage > 1.5:
            score += 20
        elif leverage > 1.0:
            score += 10
        
        # 仓位权重
        position_ratio = order.get("size", 0) / account_info.get("total_balance", 1)
        if position_ratio > 0.05:
            score += 20
        elif position_ratio > 0.02:
            score += 10
        
        # 持仓时间权重
        if order.get("timeframe", "").endswith("1h"):
            score += 10
        
        # 市场状态权重
        fear_index = account_info.get("fear_index", 50)
        if fear_index < 20:  # 极度恐惧
            score += 30
        elif fear_index < 40:
            score += 20
        elif fear_index > 80:  # 极度贪婪
            score += 15
        
        # 历史表现权重
        daily_loss_ratio = self._daily_stats["total_loss"]
        if daily_loss_ratio > 0.05:
            score += 20
        
        return min(score, 100)
    
    async def apply_modifications(self, order: dict, result: RiskCheckResult) -> dict:
        """应用风控修改到订单"""
        if not result.modifications:
            return order
        
        modified_order = order.copy()
        for key, value in result.modifications.items():
            modified_order[key] = value
            logger.info(f"风控修改订单: {key} = {value}")
        
        return modified_order
    
    def record_trade_result(self, order: dict, pnl: float):
        """记录交易结果"""
        self._daily_stats["total_trades"] += 1
        if pnl < 0:
            self._daily_stats["total_loss"] += abs(pnl) / self._get_total_balance()
    
    def _get_total_balance(self) -> float:
        """获取总余额"""
        # 这里应该从账户信息获取
        return 100000.0
    
    def reset_daily_stats(self):
        """重置每日统计"""
        self._daily_stats = {
            "total_trades": 0,
            "total_loss": 0.0,
            "blocked_orders": 0,
            "last_reset": datetime.now()
        }
    
    def trigger_circuit_breaker(self, symbol: str, reason: str, duration_minutes: int = 60):
        """触发熔断"""
        self._circuit_breakers[symbol] = {
            "triggered": True,
            "reason": reason,
            "triggered_at": datetime.now(),
            "duration": duration_minutes
        }
        logger.warning(f"⚡ 熔断触发: {symbol} - {reason}")
    
    def reset_circuit_breaker(self, symbol: str):
        """重置熔断"""
        if symbol in self._circuit_breakers:
            del self._circuit_breakers[symbol]
            logger.info(f"✅ 熔断重置: {symbol}")
    
    def update_config(self, **kwargs):
        """更新风控配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"风控配置更新: {key} = {value}")
    
    def get_status(self) -> dict:
        """获取风控状态"""
        return {
            "daily_trades": self._daily_stats["total_trades"],
            "daily_loss": self._daily_stats["total_loss"],
            "blocked_orders": self._daily_stats["blocked_orders"],
            "active_circuit_breakers": list(self._circuit_breakers.keys()),
            "config": {
                "max_leverage": self.config.max_leverage,
                "max_position": self.config.max_single_position,
                "max_exposure": self.config.max_total_exposure,
            }
        }


# 单例实例
_risk_engine: Optional[RiskEngine] = None


def get_risk_engine() -> RiskEngine:
    """获取风控引擎单例"""
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
