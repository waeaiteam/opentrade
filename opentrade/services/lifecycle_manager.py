"""
OpenTrade 策略生命周期管理 - P1 优化

核心优化: 策略全流程管控
- 孵化期: 模拟盘验证
- 观察期: 小资金实盘
- 运行期: 实时监控
- 淘汰期: 自动下线

作者: OpenTrade AI
日期: 2026-02-15
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ============== 策略状态 ==============

class StrategyStatus(Enum):
    """策略状态"""
    DRAFT = "draft"           # 草稿
    INCUBATING = "incubating"  # 孵化期 (模拟盘)
    OBSERVING = "observing"    # 观察期 (小资金)
    ACTIVE = "active"          # 运行期 (全量)
    MONITORING = "monitoring"  # 监控中
    DEGRADED = "degraded"      # 降级 (异常)
    RETIRED = "retired"        # 淘汰
    ARCHIVED = "archived"      # 归档


# ============== 策略元数据 ==============

@dataclass
class StrategyMetrics:
    """策略绩效指标"""
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade: float = 0.0
    trade_count: int = 0
    avg_holding_period: float = 0.0  # 小时
    
    def to_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade": self.avg_trade,
            "trade_count": self.trade_count,
            "avg_holding_period": self.avg_holding_period,
        }


@dataclass
class StrategyVersion:
    """策略版本"""
    version: str
    created_at: datetime
    parameters: dict
    metrics: StrategyMetrics
    parent_version: Optional[str] = None
    evolution_type: str = "manual"  # manual/genetic/mutation
    
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "parameters": self.parameters,
            "metrics": self.metrics.to_dict(),
            "parent_version": self.parent_version,
            "evolution_type": self.evolution_type,
        }


@dataclass
class Strategy:
    """策略实体"""
    id: str
    name: str
    type: str  # trend/mean_reversion/scalping/arbitrage
    status: StrategyStatus
    
    # 当前版本
    current_version: StrategyVersion
    
    # 历史版本
    versions: list[StrategyVersion] = field(default_factory=list)
    
    # 生命周期数据
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # 运行时数据
    paper_metrics: StrategyMetrics = None
    live_metrics: StrategyMetrics = None
    simulation_live_deviation: float = 0.0  # 模拟-实盘偏差
    
    # 孵化/观察期数据
    incubation_end: datetime = None
    observation_end: datetime = None
    
    # 配置
    config: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": self.status.value,
            "current_version": self.current_version.to_dict(),
            "versions_count": len(self.versions),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "paper_metrics": self.paper_metrics.to_dict() if self.paper_metrics else None,
            "live_metrics": self.live_metrics.to_dict() if self.live_metrics else None,
            "deviation": self.simulation_live_deviation,
        }


# ============== 生命周期管理器 ==============

class LifecycleManager:
    """
    策略生命周期管理器
    
    管理策略从创建到淘汰的全流程
    """
    
    def __init__(self):
        self._strategies: dict[str, Strategy] = {}
        
        # 配置
        self.config = {
            # 孵化期配置
            "incubation_days": 14,      # 模拟盘至少2周
            "incubation_min_trades": 20,  # 最少20笔交易
            
            # 观察期配置
            "observation_days_min": 30,   # 最短1个月
            "observation_days_max": 90,   # 最长3个月
            "observation_cap": 0.1,       # 小资金上限 10% 仓位
            "deviation_threshold": 0.20,   # 模拟-实盘偏差阈值 20%
            
            # 运行期配置
            "monitoring_check_interval_hours": 6,  # 每6小时检查
            "degradation_threshold": 0.15,  # 绩效下降 15% 降级
            
            # 淘汰期配置
            "retirement_trades_min": 100,   # 最少100笔交易才能判定失效
            "retirement_consecutive_loss_days": 30,  # 连续30天亏损
            "retirement_performance_threshold": -0.10,  # 累计亏损 10%
        }
    
    def create_strategy(self, name: str, type: str, 
                       parameters: dict = None) -> Strategy:
        """创建新策略 (进入孵化期)"""
        strategy_id = str(uuid4())
        
        version = StrategyVersion(
            version="v1.0",
            created_at=datetime.utcnow(),
            parameters=parameters or {},
            metrics=StrategyMetrics(),
            parent_version=None,
            evolution_type="manual",
        )
        
        strategy = Strategy(
            id=strategy_id,
            name=name,
            type=type,
            status=StrategyStatus.INCUBATING,
            current_version=version,
            versions=[version],
            config=self._get_default_config(type),
        )
        
        self._strategies[strategy_id] = strategy
        
        # 设置孵化期结束时间
        strategy.incubation_end = datetime.utcnow() + timedelta(
            days=self.config["incubation_days"]
        )
        
        return strategy
    
    def _get_default_config(self, type: str) -> dict:
        """获取默认配置"""
        configs = {
            "trend": {"stop_loss": 0.05, "take_profit": 0.15, "timeframe": "1h"},
            "mean_reversion": {"stop_loss": 0.03, "take_profit": 0.08, "timeframe": "15m"},
            "scalping": {"stop_loss": 0.01, "take_profit": 0.02, "timeframe": "1m"},
            "arbitrage": {"spread_threshold": 0.005, "execution_timeout": 5},
        }
        return configs.get(type, {})
    
    async def complete_incubation(self, strategy_id: str, 
                                  paper_metrics: StrategyMetrics) -> bool:
        """
        完成孵化期
        
        条件:
        - 孵化时间 >= 14天
        - 交易数 >= 20
        - 夏普比率 > 0.5 或 正收益
        """
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        if strategy.status != StrategyStatus.INCUBATING:
            return False
        
        # 检查条件
        now = datetime.utcnow()
        days_passed = (now - strategy.created_at).days
        trades_ok = paper_metrics.trade_count >= self.config["incubation_min_trades"]
        time_ok = days_passed >= self.config["incubation_days"]
        perf_ok = paper_metrics.sharpe_ratio > 0.5 or paper_metrics.total_return > 0
        
        if not (trades_ok and time_ok and perf_ok):
            # 退回修改
            strategy.status = StrategyStatus.DRAFT
            strategy.updated_at = now
            return False
        
        # 进入观察期
        strategy.status = StrategyStatus.OBSERVING
        strategy.paper_metrics = paper_metrics
        strategy.incubation_end = now
        strategy.observation_end = now + timedelta(days=self.config["observation_days_min"])
        
        return True
    
    async def complete_observation(self, strategy_id: str,
                                   live_metrics: StrategyMetrics) -> bool:
        """
        完成观察期
        
        条件:
        - 观察时间 >= 1个月
        - 模拟-实盘偏差 < 20%
        - 实盘绩效不差
        """
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        if strategy.status != StrategyStatus.OBSERVING:
            return False
        
        # 计算偏差
        if strategy.paper_metrics:
            deviation = self._calculate_deviation(
                strategy.paper_metrics, live_metrics
            )
            strategy.simulation_live_deviation = deviation
        else:
            deviation = 0
        
        # 检查条件
        now = datetime.utcnow()
        time_ok = now >= strategy.observation_end
        deviation_ok = deviation < self.config["deviation_threshold"]
        perf_ok = live_metrics.total_return > -0.10  # 亏损不超10%
        
        if not (time_ok and deviation_ok and perf_ok):
            # 延长观察或降级
            if deviation > self.config["deviation_threshold"]:
                strategy.status = StrategyStatus.DEGRADED
            else:
                # 延长观察期
                strategy.observation_end = now + timedelta(days=30)
            strategy.updated_at = now
            return False
        
        # 进入运行期
        strategy.status = StrategyStatus.ACTIVE
        strategy.live_metrics = live_metrics
        strategy.updated_at = now
        
        return True
    
    async def check_monitoring(self, strategy_id: str,
                              current_metrics: StrategyMetrics) -> str:
        """
        检查运行中的策略
        
        Returns:
            状态: "ok" / "degraded" / "retired"
        """
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return "unknown"
        
        if strategy.status not in [StrategyStatus.ACTIVE, StrategyStatus.MONITORING]:
            return "ok"
        
        # 计算绩效变化
        if strategy.live_metrics:
            performance_change = self._calculate_performance_change(
                strategy.live_metrics, current_metrics
            )
        else:
            performance_change = 0
        
        now = datetime.utcnow()
        
        # 降级条件
        if performance_change < -self.config["degradation_threshold"]:
            strategy.status = StrategyStatus.DEGRADED
            strategy.updated_at = now
            return "degraded"
        
        # 检查连续亏损
        if self._check_consecutive_losses(strategy, current_metrics):
            strategy.status = StrategyStatus.RETIRED
            strategy.updated_at = now
            return "retired"
        
        # 更新指标
        strategy.live_metrics = current_metrics
        strategy.status = StrategyStatus.MONITORING
        strategy.updated_at = now
        
        return "ok"
    
    def _calculate_deviation(self, paper: StrategyMetrics, live: StrategyMetrics) -> float:
        """计算模拟-实盘偏差"""
        if not paper or not live:
            return 0
        
        # 使用总收益偏差
        return abs(paper.total_return - live.total_return)
    
    def _calculate_performance_change(self, old: StrategyMetrics, 
                                      new: StrategyMetrics) -> float:
        """计算绩效变化"""
        if not old or not new:
            return 0
        
        return (new.total_return - old.total_return) / max(abs(old.total_return), 0.01)
    
    def _check_consecutive_losses(self, strategy: Strategy,
                                  metrics: StrategyMetrics) -> bool:
        """检查连续亏损"""
        # 简化: 检查累计亏损
        return metrics.total_return < self.config["retirement_performance_threshold"]
    
    def retire_strategy(self, strategy_id: str, reason: str = None) -> bool:
        """淘汰策略"""
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        strategy.status = StrategyStatus.RETIRED
        strategy.updated_at = datetime.utcnow()
        
        # 记录原因
        if not hasattr(strategy, "retirement_reason"):
            strategy.retirement_reason = []
        strategy.retirement_reason.append({
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        return True
    
    def archive_strategy(self, strategy_id: str) -> bool:
        """归档策略"""
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        if strategy.status != StrategyStatus.RETIRED:
            return False
        
        strategy.status = StrategyStatus.ARCHIVED
        strategy.updated_at = datetime.utcnow()
        
        return True
    
    def evolve_strategy(self, strategy_id: str, 
                       new_parameters: dict,
                       evolution_type: str = "mutation") -> Optional[StrategyVersion]:
        """进化策略"""
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return None
        
        # 创建新版本
        old_version = strategy.current_version.version
        
        # 解析版本号
        major, minor = old_version.lstrip("v").split(".")
        new_minor = int(minor) + 1
        new_version_str = f"v{major}.{new_minor}"
        
        version = StrategyVersion(
            version=new_version_str,
            created_at=datetime.utcnow(),
            parameters=new_parameters,
            metrics=StrategyMetrics(),
            parent_version=old_version,
            evolution_type=evolution_type,
        )
        
        strategy.versions.append(version)
        strategy.current_version = version
        strategy.status = StrategyStatus.INCUBATING  # 重新孵化
        strategy.updated_at = datetime.utcnow()
        
        # 重置孵化期
        strategy.incubation_end = datetime.utcnow() + timedelta(
            days=self.config["incubation_days"]
        )
        
        return version
    
    def get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """获取策略"""
        return self._strategies.get(strategy_id)
    
    def list_strategies(self, status: StrategyStatus = None) -> list[Strategy]:
        """列出策略"""
        if status:
            return [s for s in self._strategies.values() if s.status == status]
        return list(self._strategies.values())
    
    def get_lifecycle_summary(self) -> dict:
        """获取生命周期汇总"""
        summary = {
            "total": len(self._strategies),
            "by_status": {},
        }
        
        for status in StrategyStatus:
            count = sum(1 for s in self._strategies.values() if s.status == status)
            summary["by_status"][status.value] = count
        
        return summary


# ============== 向量经验存储 ==============

class StrategyExperienceStore:
    """
    策略经验存储
    
    将有效策略、失效模式存入向量数据库
    进化时通过 RAG 检索历史经验
    """
    
    def __init__(self):
        self._experiences: list[dict] = []
    
    async def store(self, strategy: Strategy, outcome: str, 
                   lessons: list[str]):
        """存储经验"""
        experience = {
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "type": strategy.type,
            "parameters": strategy.current_version.parameters,
            "outcome": outcome,  # "success" / "failure" / "partial"
            "metrics": strategy.current_version.metrics.to_dict(),
            "lessons": lessons,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self._experiences.append(experience)
    
    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """检索相似经验 (简化版，实际用向量数据库)"""
        # 简单关键词匹配
        results = []
        for exp in self._experiences:
            if any(query.lower() in str(v).lower() for v in exp.values()):
                results.append(exp)
        
        return results[:top_k]
    
    async def get_failure_patterns(self) -> list[dict]:
        """获取失效模式"""
        return [e for e in self._experiences if e["outcome"] == "failure"]
    
    async def get_success_patterns(self) -> list[dict]:
        """获取成功模式"""
        return [e for e in self._experiences if e["outcome"] == "success"]


# ============== 全局实例 ==============

lifecycle_manager = LifecycleManager()
experience_store = StrategyExperienceStore()
