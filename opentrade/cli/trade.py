"""
OpenTrade Trade CLI - 交易命令

Usage:
    opentrade trade [OPTIONS]

Options:
    --mode TEXT     模式: paper/live (默认: paper)
    --strategy TEXT 策略 ID (默认: 当前启用策略)
    --symbol TEXT   交易标的 (默认: BTC/USDT)
    --max-cycles INT  最大循环次数 (0=无限)
    --interval INT  执行间隔秒数 (默认: 60)
    --dry-run      dry-run 模式 (不执行交易)
    --help         显示帮助
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="trade", help="执行交易策略")


def show_status(mode: str, strategy: str, symbol: str):
    """显示当前状态"""
    from opentrade.core.config import get_config
    config = get_config()

    table = Table(title="交易状态")
    table.add_row("项目", "值")
    table.add_row("模式", mode.upper())
    table.add_row("策略", strategy)
    table.add_row("交易对", symbol)
    table.add_row("交易所", config.exchange.name)
    table.add_row("风控等级", config.risk.risk_level)
    table.add_row("最大杠杆", str(config.risk.max_leverage))
    table.add_row("最大仓位", f"{config.risk.max_position_pct * 100}%")

    print(Panel(
        table,
        title="OpenTrade 交易",
        subtitle=f"启动时间: {datetime.now().isoformat()}"
    ))


def show_positions(exchange, symbol: str):
    """显示当前持仓"""
    try:
        balance = asyncio.run(exchange.fetch_balance())
        positions = asyncio.run(exchange.fetch_positions([symbol])) if "fetch_positions" in dir(exchange) else []

        table = Table(title=f"持仓 - {symbol}")
        table.add_row("资产", "可用", "冻结", "净值")

        for asset, info in balance.get("total", {}).items():
            if info and float(info) > 0.0001:
                free = balance.get("free", {}).get(asset, 0)
                used = balance.get("used", {}).get(asset, 0)
                table.add_row(asset, str(free), str(used), str(info))

        if positions:
            for pos in positions:
                table.add_row(
                    f"[cyan]{pos['symbol']}[/cyan]",
                    f"L: {pos['side']}",
                    f"S: {pos['size']}",
                    f"P: {pos['entryPrice']}"
                )

        print(table)
    except Exception as e:
        print(f"[yellow]⚠️  获取持仓失败: {e}[/yellow]")


async def run_trading_loop(
    exchange,
    strategy_id: str,
    symbol: str,
    mode: str,
    max_cycles: int,
    interval: int,
):
    """运行交易循环"""
    from opentrade.core.gateway import OrderGateway
    from opentrade.core.config import get_config
    from opentrade.services.lifecycle_manager import LifecycleManager
    from opentrade.agents.coordinator import AgentCoordinator

    config = get_config()
    gateway = OrderGateway(exchange)
    lifecycle = LifecycleManager()
    coordinator = AgentCoordinator()

    cycle = 0
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        print("\n[yellow]⏹️  收到停止信号，正在优雅退出...[/yellow]")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"\n[green]🚀 开始交易循环 (模式: {mode})[/green]")
    print(f"   策略: {strategy_id}")
    print(f"   交易对: {symbol}")
    print(f"   间隔: {interval}秒")
    print("-" * 50)

    while running:
        cycle += 1

        if max_cycles > 0 and cycle > max_cycles:
            print(f"\n[green]✅ 完成 {max_cycles} 个循环，退出[/green]")
            break

        print(f"\n[bold]--- 循环 {cycle} ---[/bold]")

        try:
            # 1. 获取市场状态
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe="1h", limit=100)
            ticker = await exchange.fetch_ticker(symbol)

            market_state = {
                "symbol": symbol,
                "price": ticker["last"],
                "ohlcv": ohlcv,
                "timestamp": datetime.now().isoformat(),
            }

            # 2. Agent 分析
            decision = await coordinator.analyze(market_state)

            if decision["action"] == "hold":
                print("🤔 保持观望")
            else:
                print(f"📊 Agent 决策: {decision['action']} {decision.get('confidence', 0)*100:.0f}%")
                print(f"   原因: {', '.join(decision.get('reasons', []))}")

                # 3. 风控 + 执行
                if mode != "dry-run":
                    order = await gateway.submit(
                        symbol=symbol,
                        action=decision["action"],
                        size=decision.get("size", 0.1),
                        leverage=config.risk.max_leverage,
                    )
                    if order:
                        print(f"✅ 订单已提交: {order['id']}")
                    else:
                        print("❌ 订单被风控拒绝")
                else:
                    print(f"   [yellow]DRY-RUN: 不会实际下单[/yellow]")

            # 4. 显示持仓
            show_positions(exchange, symbol)

        except Exception as e:
            print(f"[red]❌ 循环错误: {e}[/red]")

        # 等待下一个循环
        if running:
            await asyncio.sleep(interval)

    print("\n[green]👋 交易循环已停止[/green]")


@app.command()
def main(
    mode: str = typer.Option("paper", "-m", "--mode", help="交易模式: paper/live"),
    strategy: Optional[str] = typer.Option(None, "-s", "--strategy", help="策略 ID"),
    symbol: str = typer.Option("BTC/USDT", "-S", "--symbol", help="交易对"),
    max_cycles: int = typer.Option(0, "-c", "--max-cycles", help="最大循环次数 (0=无限)"),
    interval: int = typer.Option(60, "-i", "--interval", help="循环间隔秒数"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="仅模拟，不执行交易"),
):
    """执行 AI 交易策略"""
    console = Console()

    # 欢迎信息
    print(Panel(
        f"[bold]OpenTrade 交易执行[/bold]\n\n"
        f"模式: {mode.upper()}\n"
        f"交易对: {symbol}\n"
        f"策略: {strategy or '默认策略'}",
        title="OpenTrade Trade",
        subtitle="启动中..."
    ))

    # 检查配置
    from opentrade.core.config import get_config
    config = get_config()

    if not config.exchange.api_key and mode != "paper":
        print("[red]❌ 实盘模式需要配置交易所 API Key[/red]")
        print("   使用 opentrade init 配置，或设置 OPENTRADE_EXCHANGE_API_KEY 环境变量")
        raise typer.Exit(1)

    if not config.ai.api_key and not dry_run:
        print("[yellow]⚠️  警告: 未配置 AI API Key，将使用规则引擎[/yellow]")

    # 显示状态
    show_status(mode, strategy or "默认", symbol)

    # 创建交易所连接
    import ccxt

    try:
        if mode == "paper":
            # 模拟交易所
            print("\n[cyan]📝 使用 Paper 模式 (模拟交易)[/cyan]")
            exchange = ccxt.binance({
                "apiKey": "paper",
                "secret": "paper",
                "enableRateLimit": True,
                "sandbox": True,  # 使用测试网络
            })
        else:
            print(f"\n[red]🔴 连接实盘: {config.exchange.name}[/red]")
            exchange_config = {
                "apiKey": config.exchange.api_key,
                "secret": config.exchange.api_secret,
                "enableRateLimit": True,
            }
            if config.exchange.passphrase:
                exchange_config["password"] = config.exchange.passphrase

            exchange_class = getattr(ccxt, config.exchange.name)
            exchange = exchange_class(exchange_config)

        # 测试连接
        balance = asyncio.run(exchange.fetch_balance())
        print(f"\n[green]✅ 交易所连接成功[/green]")
        print(f"   余额: {sum(float(v) for v in balance.get('total', {}).values()):.4f} USDT")

    except Exception as e:
        print(f"[red]❌ 交易所连接失败: {e}[/red]")
        raise typer.Exit(1)

    # 启动交易循环
    try:
        asyncio.run(run_trading_loop(
            exchange=exchange,
            strategy_id=strategy or "default",
            symbol=symbol,
            mode=mode,
            max_cycles=max_cycles,
            interval=interval,
        ))
    except KeyboardInterrupt:
        print("\n[yellow]👋 用户中断[/yellow]")


@app.command()
def status():
    """查看当前交易状态"""
    from opentrade.core.database import get_engine
    from sqlalchemy import text

    console = Console()

    table = Table(title="交易状态")

    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 检查是否有运行中的交易
            result = conn.execute(text("SELECT count(*) FROM trades WHERE status='open'"))
            open_trades = result.scalar() or 0

            result = conn.execute(text("SELECT count(*) FROM trades WHERE created_at > NOW() - INTERVAL '24 hours'"))
            today_trades = result.scalar() or 0

            table.add_row("项目", "值")
            table.add_row("开启仓位", str(open_trades))
            table.add_row("今日交易", str(today_trades))
            table.add_row("状态", "🟢 运行中")

        console.print(table)
    except Exception as e:
        print(f"[yellow]⚠️  无法获取状态: {e}[/yellow]")


@app.command()
def stop():
    """停止当前运行的交易"""
    import os
    import signal

    pidfile = Path("/tmp/opentrade-trade.pid")
    if not pidfile.exists():
        print("[yellow]未检测到运行中的交易[/yellow]")
        raise typer.Exit(1)

    pid = int(pidfile.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
        pidfile.unlink()
        print("[green]✅ 交易已停止[/green]")
    except ProcessLookupError:
        print("[yellow]进程不存在[/yellow]")


if __name__ == "__main__":
    app()
