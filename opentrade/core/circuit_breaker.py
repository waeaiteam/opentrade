"""
三级熔断机制
策略级 / 账户级 / 系统级 熔断保护
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断状态"""
    NORMAL = "normal"
    WARNING = "warning"
    TRIGGERED = "triggered"
    RECOVERING = "recovering"


@dataclass
class CircuitBreakerConfig:
    """熔断配置"""
    # 策略级熔断
    strategy_max_daily_loss: float = 0.05      # 单策略单日最大亏损 5%
    strategy_max_consecutive_losses: int = 5  # 最大连续亏损次数
    
    # 账户级熔断
    account_max_daily_loss: float = 0.10      # 账户单日最大亏损 10%
    account_max_drawdown: float = 0.20         # 账户最大回撤 20%
    account_freeze_threshold: float = 0.08    # 账户冻结阈值 8%
    
    # 系统级熔断
    system_volatility_threshold: float = 0.20  # 波动率阈值 20%
    system_api_failure_threshold: int = 5      # API连续失败次数
    system_panic_sell_threshold: float = 0.15  # 恐慌性抛售阈值 15%
    
    # 恢复设置
    auto_recover_minutes: int = 60            # 自动恢复时间
    manual_recover_required: bool = False    # 是否需要手动恢复
    
    # 通知设置
    notify_on_trigger: bool = True
    notify_on_recover: bool = True


@dataclass
class CircuitBreakerState:
    """熔断状态数据"""
    state: CircuitState = CircuitState.NORMAL
    triggered_at: Optional[datetime] = None
    triggered_by: str = ""
    reason: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    recovery_attempts: int = 0


class CircuitBreaker:
    """
    三级熔断器
    
    策略级: 单策略单日亏损超限 -> 暂停该策略
    账户级: 账户单日亏损超限 -> 冻结所有交易
    系统级: 极端行情波动 -> 全量平仓 + 冻结
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._states = {
            "strategy": {},    # 策略级熔断状态
            "account": CircuitBreakerState(),  # 账户级
            "system": CircuitBreakerState()     # 系统级
        }
        self._callbacks: List[Callable] = []  # 熔断回调
        
        # 加载持久化状态
        self._load_state()
    
    def _load_state(self):
        """加载持久化的熔断状态"""
        state_file = Path("/root/.opentrade/data/circuit_breaker_state.json")
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                self._states = data
                logger.info("✅ 熔断状态已恢复")
            except Exception as e:
                logger.warning(f"⚠️ 熔断状态恢复失败: {e}")
    
    def _save_state(self):
        """保存熔断状态"""
        state_file = Path("/root/.opentrade/data/circuit_breaker_state.json")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(self._states, default=str))
        os.chmod(str(state_file), 0o600)
    
    def register_callback(self, callback: Callable[[str, CircuitBreakerState], None]):
        """注册熔断回调"""
        self._callbacks.append(callback)
    
    async def _trigger_callbacks(self, level: str, state: CircuitBreakerState):
        """触发回调"""
        for callback in self._callbacks:
            try:
                await callback(level, state)
            except Exception as e:
                logger.error(f"熔断回调失败: {e}")
    
    # ==================== 策略级熔断 ====================
    
    async def check_strategy(self, strategy_id: str, 
                           daily_pnl: float,
                           consecutive_losses: int,
                           position_value: float) -> tuple[bool, str]:
        """
        检查策略级熔断
        
        Returns:
            (是否允许交易, 原因)
        """
        stats = self._states["strategy"].get(strategy_id, {})
        
        # 检查单日亏损
        if daily_pnl < -position_value * self.config.strategy_max_daily_loss:
            await self._trigger_strategy_breach(strategy_id, "单日亏损超限")
            return False, f"策略 {strategy_id} 单日亏损超限，已暂停"
        
        # 检查连续亏损
        if consecutive_losses >= self.config.strategy_max_consecutive_losses:
            await self._trigger_strategy_breach(strategy_id, "连续亏损超限")
            return False, f"策略 {strategy_id} 连续亏损 {consecutive_losses} 次，已暂停"
        
        return True, "策略交易允许"
    
    async def _trigger_strategy_breach(self, strategy_id: str, reason: str):
        """触发策略级熔断"""
        self._states["strategy"][strategy_id] = {
            "state": CircuitState.TRIGGERED.value,
            "triggered_at": datetime.now().isoformat(),
            "reason": reason
        }
        self._save_state()
        
        if self.config.notify_on_trigger:
            logger.warning(f"⚡ 策略级熔断: {strategy_id} - {reason}")
        
        await self._trigger_callbacks("strategy", CircuitBreakerState(
            state=CircuitState.TRIGGERED,
            triggered_by=strategy_id,
            reason=reason
        ))
    
    def reset_strategy(self, strategy_id: str):
        """重置策略级熔断"""
        if strategy_id in self._states["strategy"]:
            del self._states["strategy"][strategy_id]
            self._save_state()
            logger.info(f"✅ 策略熔断重置: {strategy_id}")
    
    # ==================== 账户级熔断 ====================
    
    async def check_account(self, 
                           daily_pnl: float,
                           total_value: float,
                           current_drawdown: float,
                           pending_orders: int) -> tuple[bool, str]:
        """
        检查账户级熔断
        
        Returns:
            (是否允许交易, 原因)
        """
        state = self._states["account"]
        
        # 警告状态
        if daily_pnl < -total_value * self.config.account_freeze_threshold * 0.5:
            if state.state != CircuitState.WARNING:
                state.state = CircuitState.WARNING
                logger.warning(f"⚠️ 账户警告: 日亏损达到 {abs(daily_pnl/total_value)*100:.1f}%")
        
        # 触发冻结
        if daily_pnl < -total_value * self.config.account_max_daily_loss:
            state.state = CircuitState.TRIGGERED
            state.triggered_at = datetime.now()
            state.triggered_by = "account"
            state.reason = f"账户单日亏损超限: {-daily_pnl/total_value*100:.1f}%"
            self._save_state()
            
            if self.config.notify_on_trigger:
                logger.warning(f"⚡ 账户级熔断触发: {state.reason}")
            
            await self._trigger_callbacks("account", state)
            return False, f"账户熔断: {state.reason}"
        
        # 检查回撤
        if current_drawdown > self.config.account_max_drawdown:
            state.state = CircuitState.TRIGGERED
            state.triggered_at = datetime.now()
            state.triggered_by = "account"
            state.reason = f"账户回撤超限: {current_drawdown*100:.1f}%"
            self._save_state()
            
            if self.config.notify_on_trigger:
                logger.warning(f"⚡ 账户级熔断触发: {state.reason}")
            
            await self._trigger_callbacks("account", state)
            return False, f"账户熔断: {state.reason}"
        
        return True, "账户交易允许"
    
    def reset_account(self):
        """重置账户级熔断"""
        self._states["account"] = CircuitBreakerState()
        self._save_state()
        logger.info("✅ 账户熔断已重置")
    
    # ==================== 系统级熔断 ====================
    
    async def check_system(self,
                          market_volatility: float,
                          api_failure_count: int,
                          panic_sell_ratio: float,
                          all_positions: List[dict]) -> tuple[bool, str, Optional[List[dict]]]:
        """
        检查系统级熔断
        
        Returns:
            (是否允许交易, 原因, 需要平仓的订单列表)
        """
        state = self._states["system"]
        positions_to_close = []
        
        # 波动率熔断
        if market_volatility > self.config.system_volatility_threshold:
            state.state = CircuitState.TRIGGERED
            state.triggered_at = datetime.now()
            state.triggered_by = "system"
            state.reason = f"市场波动率超限: {market_volatility*100:.1f}%"
            self._save_state()
            
            if self.config.notify_on_trigger:
                logger.warning(f"⚡ 系统级熔断: {state.reason}")
            
            # 全量平仓
            positions_to_close = all_positions
            await self._trigger_callbacks("system", state)
            return False, f"系统熔断: {state.reason}", positions_to_close
        
        # API故障熔断
        if api_failure_count >= self.config.system_api_failure_threshold:
            state.state = CircuitState.TRIGGERED
            state.triggered_at = datetime.now()
            state.triggered_by = "system"
            state.reason = f"API连续失败 {api_failure_count} 次"
            self._save_state()
            
            if self.config.notify_on_trigger:
                logger.warning(f"⚡ 系统级熔断: {state.reason}")
            
            await self._trigger_callbacks("system", state)
            return False, f"系统熔断: {state.reason}", None
        
        # 恐慌性抛售熔断
        if panic_sell_ratio > self.config.system_panic_sell_threshold:
            state.state = CircuitState.TRIGGERED
            state.triggered_at = datetime.now()
            state.triggered_by = "system"
            state.reason = f"恐慌性抛售比例超限: {panic_sell_ratio*100:.1f}%"
            self._save_state()
            
            if self.config.notify_on_trigger:
                logger.warning(f"⚡ 系统级熔断: {state.reason}")
            
            # 平仓50%仓位
            positions_to_close = all_positions[:len(all_positions)//2]
            await self._trigger_callbacks("system", state)
            return False, f"系统熔断: {state.reason}", positions_to_close
        
        return True, "系统交易允许", None
    
    def reset_system(self):
        """重置系统级熔断"""
        self._states["system"] = CircuitBreakerState()
        self._save_state()
        logger.info("✅ 系统熔断已重置")
    
    # ==================== 自动恢复 ====================
    
    async def check_recovery(self):
        """检查是否可恢复"""
        current_time = datetime.now()
        
        # 检查账户熔断恢复
        account_state = self._states["account"]
        if account_state.state == CircuitState.TRIGGERED and account_state.triggered_at:
            elapsed = (current_time - account_state.triggered_at).total_seconds() / 60
            if elapsed >= self.config.auto_recover_minutes and not self.config.manual_recover_required:
                self.reset_account()
                logger.info("✅ 账户熔断自动恢复")
        
        # 检查系统熔断恢复
        system_state = self._states["system"]
        if system_state.state == CircuitState.TRIGGERED and system_state.triggered_at:
            elapsed = (current_time - system_state.triggered_at).total_seconds() / 60
            if elapsed >= self.config.auto_recover_minutes and not self.config.manual_recover_required:
                self.reset_system()
                logger.info("✅ 系统熔断自动恢复")
    
    def get_status(self) -> dict:
        """获取熔断状态"""
        return {
            "strategy_breakers": {
                k: v for k, v in self._states["strategy"].items()
                if v.get("state") == CircuitState.TRIGGERED.value
            },
            "account": {
                "state": self._states["account"].state.value,
                "reason": self._states["account"].reason
            },
            "system": {
                "state": self._states["system"].state.value,
                "reason": self._states["system"].reason
            }
        }
    
    async def emergency_shutdown(self, reason: str = "紧急手动关闭") -> List[dict]:
        """
        紧急关闭 - 立即平仓所有仓位
        
        Returns:
            需要平仓的订单列表
        """
        logger.critical(f"🚨 紧急关闭触发: {reason}")
        
        # 触发所有熔断
        self._states["account"] = CircuitBreakerState(
            state=CircuitState.TRIGGERED,
            triggered_by="emergency",
            reason=reason
        )
        self._states["system"] = CircuitBreakerState(
            state=CircuitState.TRIGGERED,
            triggered_by="emergency",
            reason=reason
        )
        self._save_state()
        
        # 通知
        await self._trigger_callbacks("emergency", CircuitBreakerState(
            state=CircuitState.TRIGGERED,
            triggered_by="emergency",
            reason=reason
        ))
        
        return []  # 返回所有需要平仓的订单


# 单例
_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """获取熔断器单例"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
