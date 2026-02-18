"""
OpenTrade CLI - init command

初始化配置文件和数据库
"""

import os
import json
from pathlib import Path
from datetime import datetime
import typer
from rich import print as rprint
from rich.prompt import Prompt
from rich.console import Console

app = typer.Typer(help="Initialize OpenTrade configuration and database")

# 市面主流 AI 模型提供商配置
AI_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "features": "便宜高效，适合日常交易分析",
        "pricing": "¥ 1-2 / 1M tokens",
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4"],
        "default_model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "features": "质量稳定，响应快速",
        "pricing": "$2.5-30 / 1M tokens",
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "default_model": "claude-3-5-sonnet-20241022",
        "base_url": "https://api.anthropic.com/v1",
        "features": "长上下文，推理能力强",
        "pricing": "$3-15 / 1M tokens",
    },
    "google": {
        "name": "Google (Gemini)",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
        "default_model": "gemini-1.5-pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "features": "多模态，支持长上下文",
        "pricing": "$0.075-1.25 / 1M tokens",
    },
    "azure": {
        "name": "Azure OpenAI",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-35-turbo"],
        "default_model": "gpt-4o",
        "base_url": "https://{resource}.openai.azure.com/openai/v1",
        "features": "企业级，稳定可靠",
        "pricing": "同 OpenAI",
    },
    "aws": {
        "name": "AWS Bedrock",
        "models": ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku", "anthropic.claude-v2"],
        "default_model": "claude-3-5-sonnet",
        "base_url": "https://bedrock-runtime.{region}.amazonaws.com",
        "features": "AWS 生态集成，企业首选",
        "pricing": "$3-15 / 1M tokens",
    },
    "doubao": {
        "name": "字节跳动 (Doubao)",
        "models": ["doubao-pro-32k", "doubao-pro-128k"],
        "default_model": "doubao-pro-32k",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "features": "国内访问快，性价比高",
        "pricing": "¥ 0.8-1.5 / 1M tokens",
    },
    "yi": {
        "name": "零一万物 (Yi)",
        "models": ["yi-lightning", "yi-spark", "yi-34b-chat"],
        "default_model": "yi-lightning",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "features": "开源背景，中文优化",
        "pricing": "¥ 1-3 / 1M tokens",
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "default_model": "moonshot-v1-32k",
        "base_url": "https://api.moonshot.cn/v1",
        "features": "超长上下文，中文优化",
        "pricing": "¥ 12-60 / 1M tokens",
    },
    "zhipu": {
        "name": "智谱 AI (ChatGLM)",
        "models": ["glm-4-plus", "glm-4v", "glm-4-air"],
        "default_model": "glm-4-plus",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "features": "清华技术，中文能力强",
        "pricing": "¥ 1-5 / 1M tokens",
    },
    "tongyi": {
        "name": "阿里云 (Tongyi)",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "default_model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "features": "阿里生态，中文优化",
        "pricing": "¥ 0.8-2 / 1M tokens",
    },
    "hunyuan": {
        "name": "腾讯云 (Hunyuan)",
        "models": ["hunyuan-pro", "hunyuan-standard", "hunyuan-lite"],
        "default_model": "hunyuan-pro",
        "base_url": "https://hunyuan.cn-shanghai.ivolces.com/v1",
        "features": "腾讯生态，稳定可靠",
        "pricing": "¥ 1-3 / 1M tokens",
    },
    "ollama": {
        "name": "Ollama (本地部署)",
        "models": ["llama3.1:70b", "llama3.1:8b", "qwen2.5:72b", "mistral:7b", "deepseek-coder:33b"],
        "default_model": "llama3.1:70b",
        "base_url": "http://localhost:11434/v1",
        "features": "完全本地化，隐私保护，无 API 费用",
        "pricing": "本地 GPU 成本",
    },
    "together": {
        "name": "Together AI",
        "models": ["meta-llama/Llama-3.1-405B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "DeepSeek-R1"],
        "default_model": "meta-llama/Llama-3.1-70B-Instruct",
        "base_url": "https://api.together.ai/v1",
        "features": "开源模型聚合，便宜大模型",
        "pricing": "$0.2-1 / 1M tokens",
    },
    "groq": {
        "name": "Groq",
        "models": ["llama-3.1-405b", "llama-3.1-70b", "mixtral-8x7b-32768"],
        "default_model": "llama-3.1-70b",
        "base_url": "https://api.groq.com/openai/v1",
        "features": "极速推理，响应最快",
        "pricing": "$0.27-0.59 / 1M tokens",
    },
    "xai": {
        "name": "xAI (Grok)",
        "models": ["grok-beta", "grok-2"],
        "default_model": "grok-beta",
        "base_url": "https://api.x.ai/v1",
        "features": "X 生态集成，实时信息",
        "pricing": "$5 / 1M tokens",
    },
    "perplexity": {
        "name": "Perplexity (Sonar)",
        "models": ["sonar", "sonar-pro", "sonar-reasoning"],
        "default_model": "sonar",
        "base_url": "https://api.perplexity.ai",
        "features": "联网搜索，实时数据",
        "pricing": "$1-20 / 1M tokens",
    },
    "custom": {
        "name": "自定义 API",
        "models": ["custom"],
        "default_model": "custom",
        "base_url": "",
        "features": "支持任意兼容 OpenAI API 的服务商",
        "pricing": "取决于提供商",
    },
}


def select_ai_provider(console: Console) -> tuple[str, str, str, str]:
    """交互式选择 AI 模型提供商"""
    console.print("\n[bold cyan]🤖 AI 模型提供商选择[/bold cyan]")
    console.print("-" * 60)

    # 显示所有提供商选项
    provider_list = list(AI_PROVIDERS.keys())
    for i, provider_key in enumerate(provider_list, 1):
        provider = AI_PROVIDERS[provider_key]
        console.print(f"[{i}] [bold]{provider['name']}[/bold]")
        console.print(f"    特点: {provider['features']}")
        console.print(f"    参考价: {provider['pricing']}")
        console.print()

    # 让用户选择
    choices = list(map(str, range(1, len(provider_list) + 1)))
    default = "1"  # 默认 DeepSeek

    selected = Prompt.ask(
        f"选择 AI 提供商 (1-{len(provider_list)})",
        choices=choices,
        default=default,
        show_choices=False
    )

    provider_key = provider_list[int(selected) - 1]
    provider = AI_PROVIDERS[provider_key]

    if provider_key == "custom":
        base_url = Prompt.ask("请输入 API Base URL", default="https://api.example.com/v1")
        model = Prompt.ask("请输入模型名称", default="custom-model")
    else:
        # 选择具体模型
        console.print(f"\n[bold]可用模型 ({provider['name']}):[/bold]")
        for i, model_name in enumerate(provider['models'], 1):
            marker = " (推荐)" if model_name == provider['default_model'] else ""
            console.print(f"  {i}. {model_name}{marker}")

        model_choices = list(map(str, range(1, len(provider['models']) + 1)))
        model_default = str(provider['models'].index(provider['default_model']) + 1) if provider['default_model'] in provider['models'] else "1"

        model_selected = Prompt.ask(
            f"选择模型 (1-{len(provider['models'])})",
            choices=model_choices,
            default=model_default,
            show_choices=False
        )
        model = provider['models'][int(model_selected) - 1]
        base_url = provider['base_url']

    # 提示是否已有 API Key
    has_api_key = Prompt.ask(
        "\n是否已有 API Key?",
        choices=["y", "n"],
        default="n"
    ) == "y"

    api_key = ""
    if has_api_key:
        api_key = Prompt.ask("请输入 API Key", password=True)

    return provider_key, model, base_url, api_key


def select_exchange(console: Console) -> tuple[str, str, str]:
    """交互式选择交易所"""
    console.print("\n[bold cyan]🏦 交易所选择[/bold cyan]")
    console.print("-" * 60)

    exchanges = [
        ("hyperliquid", "Hyperliquid", "高杠杆，低手续费，支持 API 交易"),
        ("binance", "Binance", "全球最大，币种最全"),
        ("bybit", "Bybit", "衍生品专业平台"),
        ("okx", "OKX", "功能全面，API 友好"),
        ("kucoin", "KuCoin", "新兴交易所，DeFi 丰富"),
    ]

    for i, (key, name, desc) in enumerate(exchanges, 1):
        console.print(f"[{i}] [bold]{name}[/bold] - {desc}")

    choices = list(map(str, range(1, len(exchanges) + 1)))
    selected = Prompt.ask(
        f"选择交易所 (1-{len(exchanges)})",
        choices=choices,
        default="1",
        show_choices=False
    )

    exchange_key, exchange_name, _ = exchanges[int(selected) - 1]

    # API Key
    has_api_key = Prompt.ask(
        f"\n是否已有 {exchange_name} API Key?",
        choices=["y", "n"],
        default="n"
    ) == "y"

    api_key = ""
    api_secret = ""

    if has_api_key:
        api_key = Prompt.ask(f"{exchange_name} API Key")
        if exchange_key != "hyperliquid":
            api_secret = Prompt.ask(f"{exchange_name} API Secret", password=True)
    else:
        console.print(f"[yellow]⚠️  请稍后手动配置 {exchange_name} API Key[/yellow]")

    return exchange_key, api_key, api_secret


def select_risk_level(console: Console) -> dict:
    """交互式选择风险等级"""
    console.print("\n[bold cyan]⚠️  风险偏好设置[/bold cyan]")
    console.print("-" * 60)

    levels = [
        ("low", "保守型", "杠杆 ≤1.5x，单仓 ≤5%，严格止损"),
        ("medium", "平衡型", "杠杆 ≤3x，单仓 ≤10%，适中止损"),
        ("high", "激进型", "杠杆 ≤5x，单仓 ≤20%，宽松止损"),
    ]

    for i, (key, name, desc) in enumerate(levels, 1):
        console.print(f"[{i}] [bold]{name}[/bold] - {desc}")

    choices = list(map(str, range(1, len(levels) + 1)))
    selected = Prompt.ask(
        f"选择风险偏好 (1-{len(levels)})",
        choices=choices,
        default="2",
        show_choices=False
    )

    level_key, level_name, _ = levels[int(selected) - 1]

    return {
        "low": {
            "max_leverage": 1.5,
            "max_position_pct": 0.05,
            "stop_loss_pct": 0.025,
            "max_daily_loss_pct": 0.03,
        },
        "medium": {
            "max_leverage": 3.0,
            "max_position_pct": 0.10,
            "stop_loss_pct": 0.05,
            "max_daily_loss_pct": 0.05,
        },
        "high": {
            "max_leverage": 5.0,
            "max_position_pct": 0.20,
            "stop_loss_pct": 0.08,
            "max_daily_loss_pct": 0.10,
        },
    }[level_key]


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
    interactive: bool = typer.Option(True, "-i/--no-interactive", help="Interactive mode"),
):
    """
    Initialize OpenTrade configuration

    Creates:
    - config.yaml (main configuration)
    - .env (environment variables)
    - data/ directory
    """
    from opentrade.core.config import OpenTradeConfig, ExchangeConfig, AIConfig, RiskConfig

    console = Console()
    console.print("[bold]🚀 OpenTrade 初始化向导[/bold]")
    console.print("=" * 60)

    # 检查是否已初始化
    config_path = Path.home() / ".opentrade" / "config.yaml"
    if config_path.exists() and not force:
        console.print("[yellow]⚠️  OpenTrade 已初始化 (使用 --force 重新初始化)[/yellow]")
        raise typer.Exit(0)

    if interactive:
        # 1. AI 模型选择
        provider_key, model, base_url, api_key = select_ai_provider(console)

        # 2. 交易所选择
        exchange_key, exchange_api_key, exchange_api_secret = select_exchange(console)

        # 3. 风险偏好
        risk_params = select_risk_level(console)

        # 4. 是否启用 Telegram 通知
        tg_enabled = Prompt.ask(
            "\n是否启用 Telegram 通知?",
            choices=["y", "n"],
            default="n"
        ) == "y"

        telegram_config = {}
        if tg_enabled:
            telegram_config = {
                "telegram_bot_token": Prompt.ask("Telegram Bot Token", password=True),
                "telegram_chat_id": Prompt.ask("Telegram Chat ID"),
            }

        # 生成配置
        config = OpenTradeConfig(
            exchange=ExchangeConfig(
                name=exchange_key,
                api_key=exchange_api_key or None,
                api_secret=exchange_api_secret or None,
            ),
            ai=AIConfig(
                model=model,
                base_url=base_url if base_url else None,
                api_key=api_key or None,
            ),
            risk=RiskConfig(
                max_leverage=risk_params["max_leverage"],
                max_position_pct=risk_params["max_position_pct"],
                stop_loss_pct=risk_params["stop_loss_pct"],
                max_daily_loss_pct=risk_params["max_daily_loss_pct"],
            ),
            notification={
                "telegram_enabled": tg_enabled,
                **telegram_config,
            } if telegram_config else None,
        )
    else:
        # 非交互模式：使用默认值
        config = OpenTradeConfig()

    # 保存配置
    config.to_file(config_path)

    # 创建 .env 示例
    env_path = Path.home() / ".opentrade" / ".env.example"
    env_content = f'''# OpenTrade 环境变量示例
# 复制到 .env 并填入你的 API Keys

# ==================== AI 模型 ====================
DEEPSEEK_API_KEY={api_key if provider_key == 'deepseek' else ''}
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# ==================== 交易所 ====================
HYPERLIQUID_API_KEY={exchange_api_key if exchange_key == 'hyperliquid' else ''}
HYPERLIQUID_API_SECRET=
BINANCE_API_KEY=
BINANCE_API_SECRET=
BYBIT_API_KEY=
BYBIT_API_SECRET=
OKX_API_KEY=
OKX_API_SECRET=

# ==================== 数据库 ====================
DATABASE_URL=postgresql+asyncpg://opentrade:password@localhost:5432/opentrade
REDIS_URL=redis://localhost:6379/0

# ==================== Telegram ====================
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
'''
    env_path.write_text(env_content)

    # 创建数据目录
    data_dir = Path.home() / ".opentrade" / "data"
    (data_dir / "strategies").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    (data_dir / "backups").mkdir(parents=True, exist_ok=True)

    console.print("\n" + "=" * 60)
    console.print("[green]✅ 初始化完成![/green]")
    console.print("=" * 60)
    console.print(f"\n配置文件: {config_path}")
    console.print(f"环境示例: {env_path}")
    console.print("\n下一步:")
    console.print("  1. 编辑配置文件填入 API Keys")
    console.print("  2. 启动网关: opentrade gateway")
    console.print("  3. 访问: http://localhost:8000/docs")


if __name__ == "__main__":
    app()
