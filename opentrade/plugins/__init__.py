"""
OpenTrade Plugins Package
"""

from opentrade.plugins.base import BasePlugin, PluginRegistry
from opentrade.plugins.exchanges import ExchangePlugin, get_exchange

__all__ = [
    "BasePlugin",
    "PluginRegistry",
    "ExchangePlugin",
    "get_exchange",
]
