"""
OpenTrade Plugins Module
"""

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
    "PluginManager",
    "BasePlugin",
    "StrategyPlugin",
    "PluginMetadata",
    "Permission",
    "PermissionGrant",
    "BuiltInStrategies",
    "create_plugin_manager",
]
