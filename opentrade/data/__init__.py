"""
OpenTrade Data Module

Data Layer + Web + Bot + SDK + Plugins
"""

from opentrade.data.service import (
    DataService,
    TimescaleDB,
    DataQualityMonitor,
    DataQualityReport,
    Candle,
    Tick,
    Timeframe,
    DataSource,
    create_data_service,
)

from opentrade.web.bot import (
    TelegramBot,
    OpenTradeSDK,
    connect,
)

from opentrade.plugins.manager import (
    PluginManager,
    BasePlugin,
    StrategyPlugin,
    PluginMetadata,
    Permission,
    PermissionGrant,
    BuiltInStrategies,
    create_plugin_manager,
)

__all__ = [
    # Data
    "DataService",
    "TimescaleDB",
    "DataQualityMonitor",
    "DataQualityReport",
    "Candle",
    "Tick",
    "Timeframe",
    "DataSource",
    "create_data_service",
    # Web/Bot/SDK
    "TelegramBot",
    "OpenTradeSDK",
    "connect",
    # Plugins
    "PluginManager",
    "BasePlugin",
    "StrategyPlugin",
    "PluginMetadata",
    "Permission",
    "PermissionGrant",
    "BuiltInStrategies",
    "create_plugin_manager",
]
