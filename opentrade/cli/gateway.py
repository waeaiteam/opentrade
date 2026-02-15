"""
OpenTrade Gateway Service CLI

Usage:
    opentrade gateway [OPTIONS]

Options:
    --host TEXT     绑定地址 (默认: 0.0.0.0)
    --port INT      HTTP 端口 (默认: 8000)
    --ws-port INT   WebSocket 端口 (默认: 18790)
    --daemon        后台运行
    --workers INT   工作进程数 (默认: 1)
    --reload       热重载 (开发模式)
    --tls          启用 TLS
    --cert FILE    SSL 证书路径
    --key FILE     SSL 密钥路径
    --help         显示帮助
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="gateway", help="启动 OpenTrade 网关服务")


def check_dependencies() -> dict:
    """检查依赖服务可用性"""
    from opentrade.core.config import get_config

    config = get_config()
    status = {}

    # 检查数据库
    try:
        from opentrade.core.database import get_engine
        engine = get_engine()
        asyncio.run(engine.connect())
        status["database"] = "✅ 连接成功"
    except Exception as e:
        status["database"] = f"❌ {e}"

    # 检查 Redis
    try:
        import redis
        r = redis.from_url(config.storage.redis_url)
        r.ping()
        status["redis"] = "✅ 连接成功"
    except Exception as e:
        status["redis"] = f"❌ {e}"

    # 检查交易所
    if config.exchange.api_key and config.exchange.api_secret:
        try:
            import ccxt
            exchange_class = getattr(ccxt, config.exchange.name)
            exchange = exchange_class({
                "apiKey": config.exchange.api_key,
                "secret": config.exchange.api_secret,
            })
            asyncio.run(exchange.fetch_balance())
            status["exchange"] = f"✅ {config.exchange.name}"
        except Exception as e:
            status["exchange"] = f"❌ {e}"
    else:
        status["exchange"] = "⚠️ 未配置 API Key"

    return status


async def start_gateway(
    host: str,
    port: int,
    ws_port: int,
    reload: bool = False,
):
    """启动网关服务"""
    import uvicorn
    from opentrade.web.api import app as fastapi_app

    config = {
        "app": "opentrade.web.api:app",
        "host": host,
        "port": port,
        "reload": reload,
        "log_level": "info",
    }

    print(f"[green]🚀 启动网关服务...[/green]")
    print(f"   HTTP: http://{host}:{port}")
    print(f"   WS:   ws://{host}:{ws_port}")

    # 启动 uvicorn
    uvicorn.run(**config)


@app.command()
def main(
    host: str = typer.Option("0.0.0.0", "-h", "--host", help="绑定地址"),
    port: int = typer.Option(8000, "-p", "--port", help="HTTP 端口"),
    ws_port: int = typer.Option(18790, "-w", "--ws-port", help="WebSocket 端口"),
    daemon: bool = typer.Option(False, "-d", "--daemon", help="后台运行"),
    workers: int = typer.Option(1, "-w", "--workers", help="工作进程数"),
    reload: bool = typer.Option(False, "-r", "--reload", help="热重载"),
    tls: bool = typer.Option(False, "--tls", help="启用 TLS"),
    cert: Optional[str] = typer.Option(None, "--cert", help="SSL 证书"),
    key: Optional[str] = typer.Option(None, "--key", help="SSL 密钥"),
    check: bool = typer.Option(False, "--check", help="仅检查依赖"),
):
    """启动 OpenTrade 网关服务 (REST API + WebSocket)"""
    console = Console()

    # 欢迎信息
    print(Panel(
        "[bold]OpenTrade 网关服务[/bold]\n\n"
        "提供 REST API 和 WebSocket 接口\n"
        "支持策略管理、交易执行、行情查询",
        title="OpenTrade Gateway",
        subtitle="启动中..."
    ))

    # 检查依赖
    if check:
        print("\n[bold]📋 依赖检查:[/bold]")
        status = check_dependencies()
        table = Table(show_header=False)
        for k, v in status.items():
            table.add_row(f"[cyan]{k}[/cyan]", v)
        console.print(table)
        raise typer.Exit(0)

    # 检查配置
    from opentrade.core.config import get_config
    config = get_config()

    print(f"\n[bold]📊 配置信息:[/bold]")
    print(f"   交易所: {config.exchange.name}")
    print(f"   AI模型: {config.ai.model}")
    print(f"   风控: {config.risk.risk_level}")

    if not config.exchange.api_key:
        print("\n[yellow]⚠️  警告: 未配置交易所 API Key，仅支持 paper 模式[/yellow]")

    if not config.ai.api_key:
        print("[yellow]⚠️  警告: 未配置 AI API Key，策略功能受限[/yellow]")

    # 后台运行
    if daemon:
        import daemon
        from daemon.pidfile import PIDFile

        pidfile = Path("/tmp/opentrade-gateway.pid")

        with daemon.DaemonContext(pidfile=pidfile):
            asyncio.run(start_gateway(host, port, ws_port, reload))

        print(f"[green]✅ 后台启动，PID: {pidfile.read_text()}[/green]")
        raise typer.Exit(0)

    # 前台运行
    try:
        asyncio.run(start_gateway(host, port, ws_port, reload))
    except KeyboardInterrupt:
        print("\n[yellow]👋 网关已停止[/yellow]")


@app.command()
def status():
    """查看网关运行状态"""
    from opentrade.core.config import get_config
    from opentrade.core.database import get_engine
    import redis

    config = get_config()

    table = Table(title="网关状态")
    table.add_row("组件", "状态")

    # 检查进程
    import os
    pidfile = Path("/tmp/opentrade-gateway.pid")
    if pidfile.exists():
        pid = pidfile.read_text().strip()
        try:
            os.kill(int(pid), 0)
            table.add_row("进程", f"✅ 运行中 (PID: {pid})")
        except ProcessLookupError:
            table.add_row("进程", "❌ 进程不存在")
    else:
        table.add_row("进程", "⚠️ 未运行")

    # 检查数据库
    try:
        engine = get_engine()
        asyncio.run(engine.connect())
        table.add_row("数据库", "✅ 已连接")
    except Exception as e:
        table.add_row("数据库", f"❌ {e}")

    # 检查 Redis
    try:
        r = redis.from_url(config.storage.redis_url)
        r.ping()
        table.add_row("Redis", "✅ 已连接")
    except Exception as e:
        table.add_row("Redis", f"❌ {e}")

    print(table)


@app.command()
def stop():
    """停止网关服务"""
    pidfile = Path("/tmp/opentrade-gateway.pid")
    if not pidfile.exists():
        print("[yellow]网关未运行[/yellow]")
        raise typer.Exit(1)

    import os
    pid = int(pidfile.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
        pidfile.unlink()
        print("[green]✅ 网关已停止[/green]")
    except ProcessLookupError:
        print("[yellow]进程不存在，已清理 PID 文件[/yellow]")


if __name__ == "__main__":
    app()
