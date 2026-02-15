"""
OpenTrade Plugin System - 插件系统

实现:
1. 插件发现和安装
2. 插件生命周期管理
3. Skills 权限模型
4. 内置策略库

插件结构:
    plugins/
    ├── my_strategy/
    │   ├── plugin.yaml      # 插件元数据
    │   ├── strategy.py      # 策略实现
    │   ├── requirements.txt # 依赖
    │   └── __init__.py
    ├── technical_indicator/
    │   ├── ...
    └── ...

权限模型:
- skills.yaml 定义权限
- 插件声明所需权限
- 用户授权后运行
"""

import asyncio
import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


# ============ 权限模型 ============

class Permission(str, Enum):
    """插件权限"""
    # 网络权限
    NETWORK = "network"           # 允许网络请求
    EXCHANGE_API = "exchange_api" # 允许调用交易所 API

    # 数据权限
    READ_MARKET_DATA = "read_market_data"   # 读取市场数据
    READ_ACCOUNT = "read_account"            # 读取账户数据
    WRITE_ACCOUNT = "write_account"           # 修改账户 (下单)

    # 系统权限
    FILE_READ = "file_read"   # 读取文件
    FILE_WRITE = "file_write" # 写入文件
    EXECUTE = "execute"       # 执行代码

    # 高级权限
    STRATEGY_EXEC = "strategy_exec"  # 执行交易策略
    RISK_MODIFY = "risk_modify"      # 修改风控参数


@dataclass
class PermissionGrant:
    """权限授予"""
    permission: Permission
    granted_at: datetime = field(default_factory=datetime.utcnow)
    granted_by: str = "system"
    expires_at: datetime | None = None
    limits: dict[str, Any] = field(default_factory=dict)  # 速率限制等


# ============ 插件元数据 ============

@dataclass
class PluginMetadata:
    """插件元数据"""
    plugin_id: str
    name: str
    version: str
    description: str

    # 作者
    author: str = ""
    repository: str = ""

    # 版本要求
    min_opentrade_version: str = "1.0.0"

    # 依赖
    dependencies: dict[str, str] = field(default_factory=dict)

    # 权限需求
    required_permissions: list[Permission] = field(default_factory=list)

    # 类型
    plugin_type: str = "strategy"  # strategy, indicator, signal, utility

    # 入口
    entry_point: str = "main"  # Python 模块入口

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "repository": self.repository,
            "min_opentrade_version": self.min_opentrade_version,
            "dependencies": self.dependencies,
            "required_permissions": [p.value for p in self.required_permissions],
            "plugin_type": self.plugin_type,
            "entry_point": self.entry_point,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PluginMetadata":
        return cls(
            plugin_id=data.get("plugin_id", ""),
            name=data.get("name", "Unnamed Plugin"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            repository=data.get("repository", ""),
            min_opentrade_version=data.get("min_opentrade_version", "1.0.0"),
            dependencies=data.get("dependencies", {}),
            required_permissions=[Permission(p) for p in data.get("required_permissions", [])],
            plugin_type=data.get("plugin_type", "strategy"),
            entry_point=data.get("entry_point", "main"),
        )


# ============ 插件基类 ============

class BasePlugin(ABC):
    """插件基类"""

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self._enabled = False
        self._grants: dict[Permission, PermissionGrant] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def id(self) -> str:
        return self.metadata.plugin_id

    @property
    def name(self) -> str:
        return self.metadata.name

    # ============ 生命周期 ============

    @abstractmethod
    async def install(self):
        """安装插件"""
        pass

    @abstractmethod
    async def uninstall(self):
        """卸载插件"""
        pass

    @abstractmethod
    async def enable(self):
        """启用插件"""
        pass

    @abstractmethod
    async def disable(self):
        """禁用插件"""
        pass

    # ============ 核心功能 ============

    @abstractmethod
    async def initialize(self, context: dict):
        """初始化 (运行时)"""
        pass

    @abstractmethod
    async def shutdown(self):
        """关闭 (运行时)"""
        pass

    # ============ 权限管理 ============

    def request_permission(self, permission: Permission) -> bool:
        """请求权限"""
        return permission in self.metadata.required_permissions

    def grant_permission(self, permission: Permission, grant: PermissionGrant):
        """授予权限"""
        self._grants[permission] = grant

    def has_permission(self, permission: Permission) -> bool:
        """检查权限"""
        return permission in self._grants

    def check_permission(self, permission: Permission) -> bool:
        """带检查的权限验证"""
        if not self.has_permission(permission):
            raise PermissionError(f"Permission denied: {permission}")
        return True


# ============ 内置策略模板 ============

class StrategyPlugin(BasePlugin):
    """策略插件基类"""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        self.executor = None
        self.running = False

    async def execute(self, market_data: dict) -> dict:
        """执行策略 (返回信号)"""
        raise NotImplementedError

    async def on_order_update(self, order: dict):
        """订单更新回调"""
        pass

    async def on_position_update(self, position: dict):
        """持仓更新回调"""
        pass


# ============ 插件管理器 ============

class PluginManager:
    """
    插件管理器

    功能:
    1. 插件发现和安装
    2. 插件启用/禁用
    3. 权限验证
    4. 依赖解析
    """

    def __init__(self, plugins_dir: str = "./plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins: dict[str, BasePlugin] = {}
        self.enabled_plugins: dict[str, BasePlugin] = {}
        self.permission_grants: dict[str, dict[Permission, PermissionGrant]] = {}

        # 权限配置
        self._default_permissions: dict[Permission, bool] = {
            Permission.NETWORK: True,
            Permission.READ_MARKET_DATA: True,
            Permission.READ_ACCOUNT: True,
        }

    def discover_plugins(self) -> list[PluginMetadata]:
        """发现插件"""
        discovered = []

        if not self.plugins_dir.exists():
            return discovered

        for plugin_path in self.plugins_dir.iterdir():
            if plugin_path.is_dir():
                metadata_file = plugin_path / "plugin.yaml"
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            data = json.load(f)
                        metadata = PluginMetadata.from_dict(data)
                        discovered.append(metadata)
                    except Exception as e:
                        print(f"[Plugin] Failed to load {plugin_path}: {e}")

        return discovered

    async def install_plugin(self, plugin: BasePlugin) -> bool:
        """安装插件"""
        try:
            # 检查版本
            if not self._check_version_compatibility(plugin.metadata):
                return False

            # 安装依赖
            await self._install_dependencies(plugin.metadata.dependencies)

            # 运行安装
            await plugin.install()

            # 注册
            self.plugins[plugin.id] = plugin

            return True
        except Exception as e:
            print(f"[Plugin] Install failed: {e}")
            return False

    async def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        # 权限检查
        for permission in plugin.metadata.required_permissions:
            if not self._is_permission_allowed(plugin_id, permission):
                print(f"[Plugin] Permission denied: {permission}")
                return False

        # 授予权限
        for permission in plugin.metadata.required_permissions:
            plugin.grant_permission(permission, PermissionGrant(permission=permission))

        # 启用
        await plugin.enable()
        plugin._enabled = True
        self.enabled_plugins[plugin_id] = plugin

        return True

    async def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件"""
        plugin = self.enabled_plugins.get(plugin_id)
        if not plugin:
            return False

        await plugin.disable()
        plugin._enabled = False
        del self.enabled_plugins[plugin_id]

        return True

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        """获取插件"""
        return self.enabled_plugins.get(plugin_id)

    def get_enabled_plugins(self) -> list[BasePlugin]:
        """获取已启用插件"""
        return list(self.enabled_plugins.values())

    def get_all_plugins(self) -> list[BasePlugin]:
        """获取所有插件"""
        return list(self.plugins.values())

    # ============ 权限管理 ============

    def _is_permission_allowed(self, plugin_id: str, permission: Permission) -> bool:
        """检查权限是否允许"""
        # 检查全局默认
        if self._default_permissions.get(permission, False):
            return True

        # 检查用户配置
        grants = self.permission_grants.get(plugin_id, {})
        return permission in grants

    def grant_plugin_permission(
        self,
        plugin_id: str,
        permission: Permission,
        limits: dict | None = None,
    ):
        """授予插件权限"""
        if plugin_id not in self.permission_grants:
            self.permission_grants[plugin_id] = {}

        self.permission_grants[plugin_id][permission] = PermissionGrant(
            permission=permission,
            limits=limits or {},
        )

    def revoke_plugin_permission(self, plugin_id: str, permission: Permission):
        """撤销插件权限"""
        if plugin_id in self.permission_grants:
            self.permission_grants[plugin_id].pop(permission, None)

    def configure_permissions(self, config: dict):
        """配置权限"""
        for plugin_id, permissions in config.items():
            for perm, limits in permissions.items():
                self.grant_plugin_permission(plugin_id, Permission(perm), limits)

    # ============ 辅助方法 ============

    def _check_version_compatibility(self, metadata: PluginMetadata) -> bool:
        """检查版本兼容性"""
        import opentrade
        current_version = opentrade.__version__ or "1.0.0"

        # 简化版本比较
        return metadata.min_opentrade_version <= current_version

    async def _install_dependencies(self, dependencies: dict[str, str]):
        """安装依赖"""
        if not dependencies:
            return

        # 使用 pip 安装
        for package, version in dependencies.items():
            pkg = f"{package}=={version}" if version else package
            # 实际安装需要处理
            print(f"[Plugin] Would install: {pkg}")

    def save_config(self, path: str = "./data/plugin_config.json"):
        """保存配置"""
        import json
        config = {
            "enabled_plugins": list(self.enabled_plugins.keys()),
            "permission_grants": {
                pid: {
                    p.value: {
                        "granted_at": g.granted_at.isoformat(),
                        "limits": g.limits,
                    }
                    for p, g in grants.items()
                }
                for pid, grants in self.permission_grants.items()
            },
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(config, f, indent=2)

    def load_config(self, path: str = "./data/plugin_config.json"):
        """加载配置"""
        import json

        if not Path(path).exists():
            return

        with open(path) as f:
            config = json.load(f)

        # 恢复启用插件
        for plugin_id in config.get("enabled_plugins", []):
            asyncio.run(self.enable_plugin(plugin_id))


# ============ 内置策略库 ============

class BuiltInStrategies:
    """内置策略库"""

    @staticmethod
    def get_sma_crossover() -> dict:
        """SMA 交叉策略"""
        return {
            "strategy_id": "sma_crossover",
            "name": "SMA Crossover",
            "description": "Simple moving average crossover strategy",
            "parameters": {
                "fast_period": {"default": 10, "type": "int", "range": [2, 50]},
                "slow_period": {"default": 20, "type": "int", "range": [5, 200]},
                "position_size": {"default": 0.1, "type": "float", "range": [0.01, 1.0]},
            },
        }

    @staticmethod
    def get_rsi_strategy() -> dict:
        """RSI 策略"""
        return {
            "strategy_id": "rsi_strategy",
            "name": "RSI Strategy",
            "description": "RSI overbought/oversold strategy",
            "parameters": {
                "rsi_period": {"default": 14, "type": "int", "range": [5, 30]},
                "overbought": {"default": 70, "type": "int", "range": [50, 90]},
                "oversold": {"default": 30, "type": "int", "range": [10, 50]},
            },
        }

    @staticmethod
    def get_bollinger_strategy() -> dict:
        """布林带策略"""
        return {
            "strategy_id": "bollinger_strategy",
            "name": "Bollinger Band Strategy",
            "description": "Bollinger band mean reversion",
            "parameters": {
                "bb_period": {"default": 20, "type": "int", "range": [10, 100]},
                "bb_std": {"default": 2, "type": "float", "range": [1, 4]},
            },
        }

    @staticmethod
    def get_all() -> list[dict]:
        """获取所有内置策略"""
        return [
            BuiltInStrategies.get_sma_crossover(),
            BuiltInStrategies.get_rsi_strategy(),
            BuiltInStrategies.get_bollinger_strategy(),
        ]


# ============ 便捷函数 ============

def create_plugin_manager(plugins_dir: str = "./plugins") -> PluginManager:
    """创建插件管理器"""
    return PluginManager(plugins_dir=plugins_dir)
