"""
OpenTrade 配置管理
"""

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ExchangeConfig(BaseModel):
    """交易所配置"""
    name: str = "binance"
    api_key: str | None = None
    api_secret: str | None = None
    testnet: bool = False
    passphrase: str | None = None  # For exchanges like KuCoin


class AIConfig(BaseModel):
    """AI 配置"""
    model: str = "deepseek/deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096
    api_key: str | None = None
    base_url: str | None = None


class RiskConfig(BaseModel):
    """风险配置"""
    risk_level: str = "medium"  # low, medium, high
    max_position_pct: float = 0.1  # Max 10% per position
    max_leverage: float = 3.0
    max_daily_loss_pct: float = 0.05  # 5% daily stop
    max_open_positions: int = 3
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.1
    trailing_stop_pct: float | None = None


class NotificationConfig(BaseModel):
    """通知配置"""
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    email_enabled: bool = False
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_from: str | None = None
    email_to: str | None = None
    push_enabled: bool = False


class StorageConfig(BaseModel):
    """存储配置"""
    database_url: str = "postgresql+asyncpg://opentrade:password@localhost:5432/opentrade"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "~/.opentrade/data"
    log_dir: str = "~/.opentrade/logs"
    backup_dir: str = "~/.opentrade/backups"


class GatewayConfig(BaseModel):
    """网关配置"""
    host: str = "127.0.0.1"
    port: int = 18790
    web_port: int = 3000
    tailscale_enabled: bool = False


class WebConfig(BaseModel):
    """Web 配置"""
    enabled: bool = True
    title: str = "OpenTrade"
    theme: str = "dark"
    language: str = "zh-CN"


class OpenTradeConfig(BaseModel):
    """OpenTrade 主配置"""
    version: str = "1.0"

    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    web: WebConfig = Field(default_factory=WebConfig)

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.model_dump()

    def to_file(self, path: Path | str):
        """保存到文件"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)

    @classmethod
    def from_file(cls, path: Path | str) -> "OpenTradeConfig":
        """从文件加载"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(**data)

    @classmethod
    def generate_default(cls) -> "OpenTradeConfig":
        """生成默认配置"""
        return cls()


class ConfigManager:
    """配置管理器"""

    _instance: Optional["ConfigManager"] = None
    _config: OpenTradeConfig | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._config = self._load_default()

    @staticmethod
    def config_path() -> Path:
        """获取默认配置文件路径"""
        return Path.home() / ".opentrade" / "config.yaml"

    def _load_default(self) -> OpenTradeConfig:
        """加载默认配置"""
        path = self.config_path()
        if path.exists():
            try:
                return OpenTradeConfig.from_file(path)
            except Exception as e:
                print(f"加载配置失败: {e}")
                return OpenTradeConfig()
        return OpenTradeConfig()

    def load(self) -> OpenTradeConfig:
        """加载配置"""
        return self._config

    def save(self, config: OpenTradeConfig = None):
        """保存配置"""
        config = config or self._config
        config.to_file(self.config_path())

    def update(self, key: str, value: Any):
        """更新配置项 (支持点号分隔的路径)"""
        keys = key.split(".")
        obj = self._config

        for k in keys[:-1]:
            if hasattr(obj, k):
                obj = getattr(obj, k)

        if hasattr(obj, keys[-1]):
            setattr(obj, keys[-1], value)
            self.save()


# 全局访问点
def get_config() -> OpenTradeConfig:
    """获取当前配置"""
    return ConfigManager().load()


def settings():
    """获取配置 (兼容旧 API)"""
    return get_config()


# 环境变量支持
class EnvSettings(BaseSettings):
    """环境变量配置"""

    OPENTRADE_EXCHANGE: str = "binance"
    OPENTRADE_API_KEY: str | None = None
    OPENTRADE_API_SECRET: str | None = None
    OPENTRADE_AI_MODEL: str = "deepseek/deepseek-chat"
    OPENTRADE_AI_API_KEY: str | None = None

    class Config:
        env_prefix = "OPENTRADE_"
        extra = "ignore"
