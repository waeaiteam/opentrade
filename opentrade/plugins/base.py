"""
OpenTrade 插件基类和注册表
"""

from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """插件基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本"""
        pass

    @property
    def description(self) -> str:
        """插件描述"""
        return ""

    @property
    def dependencies(self) -> list[str]:
        """依赖"""
        return []

    def __init__(self, config: dict = None):
        """初始化"""
        self.config = config or {}
        self._enabled = True

    async def initialize(self):
        """初始化插件"""
        pass

    async def shutdown(self):
        """关闭插件"""
        pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value


class PluginRegistry:
    """插件注册表"""

    _instance: "PluginRegistry" = None
    _plugins: dict[str, BasePlugin] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._registry: dict[str, type[BasePlugin]] = {}

    def register(self, plugin_class: type[BasePlugin]):
        """注册插件类"""
        name = plugin_class.__name__
        self._registry[name] = plugin_class
        print(f"已注册插件: {name}")

    def create(self, name: str, config: dict = None) -> BasePlugin:
        """创建插件实例"""
        if name not in self._registry:
            raise ValueError(f"插件未注册: {name}")

        plugin_class = self._registry[name]
        return plugin_class(config)

    def list_plugins(self) -> list[str]:
        """列出已注册的插件"""
        return list(self._registry.keys())

    def enable(self, name: str):
        """启用插件"""
        if name in self._plugins:
            self._plugins[name].enabled = True

    def disable(self, name: str):
        """禁用插件"""
        if name in self._plugins:
            self._plugins[name].enabled = False

    async def initialize_all(self):
        """初始化所有插件"""
        for plugin in self._plugins.values():
            if plugin.enabled:
                await plugin.initialize()

    async def shutdown_all(self):
        """关闭所有插件"""
        for plugin in self._plugins.values():
            await plugin.shutdown()


# 全局注册表
plugin_registry = PluginRegistry()
