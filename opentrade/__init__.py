"""
OpenTrade - 开源自主进化 AI 交易系统

企业级量化交易解决方案 | 多Agent协同决策 | 全链路强风控 | 策略自主进化 | 7×24小时不间断运行

GitHub: https://github.com/1347415016/opentrade
"""

__version__ = "1.0.0a1"

# 核心模块
from opentrade.engine import (
    TradeExecutor,
    OrderRequest,
    OrderType,
    Position,
    PositionSide,
    create_simulated_executor,
    create_ccxt_executor,
)

from opentrade.agents.coordinator import AgentCoordinator, FinalDecision

from opentrade.evolution import (
    GeneticAlgorithm,
    StrategyGenome,
    RLTrainer,
    TradingEnv,
    quick_optimize,
    quick_train_rl,
)

from opentrade.services.lifecycle_manager import (
    LifecycleManager,
    LifecycleStage,
    create_lifecycle_manager,
)

from opentrade.data import (
    DataService,
    Timeframe,
    create_data_service,
)

from opentrade.web.bot import (
    OpenTradeSDK,
    connect,
)

from opentrade.plugins import (
    PluginManager,
    create_plugin_manager,
    BuiltInStrategies,
)

__all__ = [
    # 版本
    "__version__",
    # 引擎
    "TradeExecutor",
    "OrderRequest",
    "OrderType",
    "Position",
    "PositionSide",
    "create_simulated_executor",
    "create_ccxt_executor",
    # Agent
    "AgentCoordinator",
    "FinalDecision",
    # 进化
    "GeneticAlgorithm",
    "StrategyGenome",
    "RLTrainer",
    "TradingEnv",
    "quick_optimize",
    "quick_train_rl",
    # 生命周期
    "LifecycleManager",
    "LifecycleStage",
    "create_lifecycle_manager",
    # 数据
    "DataService",
    "Timeframe",
    "create_data_service",
    # SDK
    "OpenTradeSDK",
    "connect",
    # 插件
    "PluginManager",
    "create_plugin_manager",
    "BuiltInStrategies",
]
