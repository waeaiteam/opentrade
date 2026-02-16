"""
OpenTrade CLI 工具函数
"""

import sys
import traceback
from functools import wraps
from pathlib import Path
from typing import Any, Callable

import structlog
from rich.console import Console
from rich.theme import Theme

# 自定义主题
theme = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green bold",
    "title": "bold blue",
})

console = Console(theme=theme)

logger = structlog.get_logger(__name__)


def setup_logging(verbose: bool = False):
    """配置日志"""
    log_level = "DEBUG" if verbose else "INFO"

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(
                colors=sys.stdout.isatty(),
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    import logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(message)s",
    )


def handle_exceptions(func: Callable) -> Callable:
    """异常处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            raise SystemExit(0)
        except Exception as e:
            console.print(f"\n[error]❌ 错误: {e}[/error]")
            if "--verbose" in sys.argv or "-v" in sys.argv:
                console.print(traceback.format_exc())
            sys.exit(1)
    return wrapper


def get_config_path() -> Path:
    """获取配置文件路径"""
    return Path.home() / ".opentrade" / "config.yaml"


def save_token(token: str):
    """保存 API Token"""
    config_dir = Path.home() / ".opentrade"
    config_dir.mkdir(parents=True, exist_ok=True)

    token_file = config_dir / ".token"
    token_file.write_text(token)
    token_file.chmod(0o600)


def load_token() -> str | None:
    """加载 API Token"""
    token_file = Path.home() / ".opentrade" / ".token"
    if token_file.exists():
        return token_file.read_text().strip()
    return None


def confirm_action(message: str, default: bool = False) -> bool:
    """确认操作"""
    from typer.style import Styling

    suffix = " [Y/n]" if default else " [y/N]"
    response = input(f"{message}{suffix} ")

    if default:
        return response.lower() not in ("n", "no")
    return response.lower() in ("y", "yes")


def print_table(headers: list[str], rows: list[list[Any]]):
    """打印表格"""
    from rich.table import Table

    table = Table()
    for h in headers:
        table.add_column(h, style="cyan")

    for row in rows:
        table.add_row(*[str(c) for c in row])

    console.print(table)


def print_status(services: list[dict]):
    """打印服务状态"""
    from rich.panel import Panel

    status_map = {
        "running": ("✅", "green"),
        "stopped": ("❌", "red"),
        "unknown": ("❓", "yellow"),
    }

    lines = []
    for s in services:
        icon, color = status_map.get(s["status"], status_map["unknown"])
        lines.append(f"{icon} {s['name']}: {s.get('message', 'OK')}")

    console.print(Panel("\n".join(lines), title="服务状态"))


class ProgressSpinner:
    """进度 spinner"""

    def __init__(self, message: str = "处理中..."):
        self.message = message
        self.spinner = None

    def __enter__(self):
        from rich.spinner import Spinner
        from rich.live import Live

        self.spinner = Spinner("dots", self.message)
        self.live = Live(self.spinner, refresh_per_second=10)
        self.live.start()
        return self

    def __exit__(self, *args):
        if self.live:
            self.live.stop()

    def update(self, message: str):
        if self.spinner:
            self.spinner.update(message)
