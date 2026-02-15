"""
OpenTrade
=========

开源 AI 加密货币交易系统。

https://github.com/opentrade-ai/opentrade
"""

__version__ = "1.0.0a1"

from opentrade.core.config import get_config, settings
from opentrade.core.database import db, init_db
from opentrade.agents.coordinator import CoordinatorAgent
from opentrade.services.trade_executor import TradeExecutor
from opentrade.services.data_service import data_service
from opentrade.services.notification_service import notification_service

__all__ = [
    # 版本
    "__version__",
    # 配置
    "get_config",
    "settings",
    # 数据库
    "db",
    "init_db",
    # Agent
    "CoordinatorAgent",
    # 服务
    "TradeExecutor",
    "data_service",
    "notification_service",
]
