"""OpenTrade CLI 应用

Usage:
    opentrade [OPTIONS] COMMAND [ARGS]...

Options:
    --config FILE     配置文件路径
    --verbose         详细输出
    --version         显示版本
    --help            显示帮助

Commands:
    init              初始化配置
    gateway           启动网关服务
    trade             开始交易
    backtest          回测策略
    strategy          策略管理
    plugin            插件管理
    config            配置管理
    doctor            系统诊断
    update            更新检查
"""

from pathlib import Path

import typer
from rich import print
from rich.panel import Panel
from typer import Argument, Option

from opentrade import __version__
from opentrade.cli.utils import (
    get_config_path,
    handle_exceptions,
    setup_logging,
)

app = typer.Typer(
    name="opentrade",
    help=__doc__,
    add_completion=False,
    no_args_is_help=True,
)


def version_callback(value: bool):
    """显示版本信息"""
    if value:
        print(f"[bold green]OpenTrade[/bold green] v{__version__}")
        print("开源 AI 交易系统")
        print()
        print("📚 文档: https://docs.opentrade.ai")
        print("🐛 问题: https://github.com/opentrade-ai/opentrade/issues")
        print("💬 Discord: https://discord.gg/opentrade")
        raise typer.Exit(0)


@app.callback()
@handle_exceptions
def main(
    ctx: typer.Context,
    config: Path | None = Option(
        None, "-c", "--config", help="配置文件路径"
    ),
    verbose: bool = Option(
        False, "-v", "--verbose", help="详细输出"
    ),
    version: bool = Option(
        False, "--version", callback=version_callback, is_eager=True
    ),
):
    """OpenTrade - 开源 AI 交易系统"""
    # 设置日志
    setup_logging(verbose=verbose)

    # 加载配置
    if config:
        # TODO: 加载指定配置文件
        pass


@app.command()
def init(
    force: bool = Option(False, "-f", "--force", help="强制重新初始化"),
):
    """初始化 OpenTrade 配置"""
    from opentrade.core.config import ConfigManager

    config_dir = Path.home() / ".opentrade"
    config_file = config_dir / "config.yaml"

    if config_file.exists() and not force:
        print(f"[yellow]配置文件已存在: {config_file}[/yellow]")
        print("使用 [bold]opentrade init --force[/bold] 重新初始化")
        raise typer.Exit(1)

    # 创建配置目录
    config_dir.mkdir(parents=True, exist_ok=True)

    # 生成默认配置
    config = ConfigManager.generate_default()
    config.to_file(config_file)

    print(Panel(
        f"[green]✅ OpenTrade 初始化完成！[/green]\n\n"
        f"📁 配置文件: {config_file}\n\n"
        "下一步:\n"
        "  1. 编辑配置文件: opentrade config edit\n"
        "  2. 设置交易所 API Key\n"
        "  3. 启动网关: opentrade gateway\n"
        "  4. 开始交易: opentrade trade --mode paper",
        title="OpenTrade",
        subtitle="初始化成功"
    ))


@app.command()
def gateway(
    daemon: bool = Option(False, "-d", "--daemon", help="后台运行"),
    port: int = Option(18790, "-p", "--port", help="端口号"),
    host: str = Option("127.0.0.1", "-h", "--host", help="绑定地址"),
):
    """启动 OpenTrade 网关服务"""
    from opentrade.cli.gateway import run_gateway

    if daemon:
        import subprocess
        import sys

        # 后台启动
        cmd = [sys.executable, "-m", "opentrade.cli.gateway", str(port), host]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[green]✅ 网关已在后台启动: ws://{host}:{port}[/green]")
        raise typer.Exit(0)

    # 前台运行
    print("[bold]🚀 启动 OpenTrade 网关...[/bold]")
    print(f"   地址: ws://{host}:{port}")
    print(f"   Web:  http://{host}:3000")
    print()
    print("[dim]按 Ctrl+C 停止[/dim]")
    print()

    run_gateway(port=port, host=host)


@app.command()
def trade(
    mode: str = Argument(
        default="paper", help="交易模式: paper(模拟) / live(实盘)"
    ),
    strategy: str | None = Option(
        None, "-s", "--strategy", help="指定策略"
    ),
    symbol: str | None = Option(
        None, "-S", "--symbol", help="交易标的"
    ),
    leverage: float = Option(1.0, "-l", "--leverage", help="杠杆倍数"),
):
    """启动交易机器人"""
    from opentrade.services.strategy_service import StrategyService
    from opentrade.services.trade_executor import TradeExecutor

    if mode not in ["paper", "live"]:
        print(f"[red]无效模式: {mode}[/red]")
        print("有效模式: paper, live")
        raise typer.Exit(1)

    print(f"[bold]🚀 启动交易模式: {mode}[/bold]")

    if mode == "paper":
        print("[yellow]⚠️  模拟交易模式 - 不涉及真实资金[/yellow]")
    else:
        print("[red]⚠️  实盘交易模式 - 涉及真实资金！[/red]")
        if not typer.confirm("确认启动实盘交易？"):
            raise typer.Exit(0)

    # 初始化
    executor = TradeExecutor(mode=mode)

    if strategy:
        service = StrategyService()
        strat = service.load_strategy(strategy)
        print(f"[green]加载策略: {strat.name}[/green]")

    # 启动交易循环
    executor.start(symbol=symbol, leverage=leverage)


@app.command()
def backtest(
    start: str = Argument(..., help="开始日期 YYYY-MM-DD"),
    end: str = Argument(default=None, help="结束日期 YYYY-MM-DD"),
    strategy: str = Option("trend_following", "-s", "--strategy", help="策略名称"),
    capital: float = Option(10000.0, "-c", "--capital", help="初始资金"),
    symbols: str = Option("BTC/USDT,ETH/USDT", "-S", "--symbols", help="交易标的"),
    report: bool = Option(False, "-r", "--report", help="生成报告"),
):
    """回测策略"""
    from datetime import datetime

    from opentrade.services.backtest_service import BacktestService

    print("[bold]📊 开始回测[/bold]")
    print(f"   策略: {strategy}")
    print(f"   资金: ${capital:,.2f}")
    print(f"   标的: {symbols}")
    print(f"   时间: {start} ~ {end or '至今'}")
    print()

    service = BacktestService()

    symbol_list = [s.strip() for s in symbols.split(",")]

    results = service.run_backtest(
        strategy_name=strategy,
        start_date=datetime.fromisoformat(start),
        end_date=datetime.fromisoformat(end) if end else None,
        symbol=symbol_list,
        initial_capital=capital,
    )

    # 显示结果
    print(Panel(
        f"[green]回测完成！[/green]\n\n"
        f"总交易次数: {results['total_trades']}\n"
        f"胜率: {results['win_rate']:.2%}\n"
        f"总收益: {results['total_return']:.2%}\n"
        f"最大回撤: {results['max_drawdown']:.2%}\n"
        f"夏普比率: {results['sharpe_ratio']:.2f}",
        title="回测结果"
    ))

    if report:
        service.generate_report(results, output_file=f"backtest_{strategy}_{start}.html")


@app.command()
def strategy(
    ctx: typer.Context,
    command: str = Argument(default=None, help="子命令: list, use, export, import, new"),
):
    """策略管理"""
    if command is None:
        print(ctx.get_help())
        raise typer.Exit(1)

    if command == "list":
        _strategy_list()
    elif command == "new":
        _strategy_new(ctx.params.get("name"))
    elif command == "export":
        _strategy_export()
    elif command == "import":
        _strategy_import()
    else:
        print(f"未知命令: {command}")
        raise typer.Exit(1)


def _strategy_list():
    """列出策略"""
    from opentrade.services.strategy_service import StrategyService

    service = StrategyService()
    strategies = service.list_strategies()

    print("\n[bold]📋 已安装策略:[/bold]\n")
    for s in strategies:
        print(f"  • [cyan]{s.name}[/cyan] v{s.version} - {s.description}")


def _strategy_new(name: str):
    """创建新策略"""

    if not name:
        name = typer.prompt("策略名称")

    # TODO: 从模板生成策略文件
    print(f"[green]创建策略: {name}[/green]")


def _strategy_export():
    """导出策略"""
    print("导出策略...")


def _strategy_import():
    """导入策略"""
    print("导入策略...")


@app.command()
def plugin(
    ctx: typer.Context,
    command: str = Argument(default=None, help="子命令: list, install, update, search"),
    name: str = Argument(default=None, help="插件名称"),
):
    """插件管理"""
    if command is None:
        print(ctx.get_help())
        raise typer.Exit(1)

    if command == "list":
        _plugin_list()
    elif command == "install":
        _plugin_install(name)
    elif command == "search":
        _plugin_search(name)
    elif command == "update":
        _plugin_update(name or "all")
    else:
        print(f"未知命令: {command}")
        raise typer.Exit(1)


def _plugin_list():
    """列出插件"""
    print("\n[bold]📦 已安装插件:[/bold]\n")
    print("  🔌 策略插件:")
    print("    • trend_following - 趋势跟踪策略")
    print("    • mean_reversion - 均值回归策略")
    print()
    print("  📡 数据源插件:")
    print("    • ccxt - 交易所数据")
    print("    • glassnode - 链上数据")
    print()
    print("  🔔 通知插件:")
    print("    • telegram - Telegram 通知")
    print("    • log - 日志通知")


def _plugin_install(name: str):
    """安装插件"""
    if not name:
        print("[red]请指定插件名称[/red]")
        raise typer.Exit(1)
    print(f"安装插件: {name}")


def _plugin_search(query: str):
    """搜索插件"""
    if not query:
        print("[red]请指定搜索关键词[/red]")
        raise typer.Exit(1)
    print(f"搜索插件: {query}")


def _plugin_update(name: str):
    """更新插件"""
    print(f"更新插件: {name}")


@app.command()
def config(
    ctx: typer.Context,
    command: str = Argument(default=None, help="子命令: show, set, edit, reset"),
):
    """配置管理"""
    if command is None:
        print(ctx.get_help())
        raise typer.Exit(1)

    if command == "show":
        _config_show()
    elif command == "set":
        _config_set()
    elif command == "edit":
        _config_edit()
    elif command == "reset":
        _config_reset()
    else:
        print(f"未知命令: {command}")
        raise typer.Exit(1)


def _config_show():
    """显示配置"""
    from opentrade.core.config import load_config

    config = load_config()

    print("\n[bold]⚙️  OpenTrade 配置[/bold]\n")
    print(f"配置文件: {get_config_path()}")
    print(f"交易所: {config.exchange.name}")
    print(f"API Key: {'✅ 已配置' if config.exchange.api_key else '❌ 未配置'}")
    print(f"API Secret: {'✅ 已配置' if config.exchange.api_secret else '❌ 未配置'}")
    print(f"AI 模型: {config.ai.model}")
    print(f"风险等级: {config.trading.risk_level}")


def _config_set():
    """设置配置"""
    print("设置配置...")


def _config_edit():
    """编辑配置"""
    import os
    import subprocess

    editor = os.environ.get("EDITOR", "nano")
    config = get_config_path()

    subprocess.run([editor, str(config)])


def _config_reset():
    """重置配置"""
    if typer.confirm("确认重置所有配置？"):
        config = get_config_path()
        if config.exists():
            config.unlink()
        print("[green]配置已重置[/green]")


@app.command()
def doctor(
    fix: bool = Option(False, "-f", "--fix", help="自动修复"),
    migrate: bool = Option(False, "-m", "--migrate", help="数据库迁移"),
):
    """系统诊断"""
    from opentrade.cli.doctor import run_diagnosis

    issues = run_diagnosis(fix=fix)

    if not issues:
        print("\n[green]✅ 系统健康！[/green]")
    else:
        print(f"\n[yellow]发现 {len(issues)} 个问题[/yellow]")


@app.command()
def update(
    check: bool = Option(True, "-c", "--check", help="检查更新"),
    latest: bool = Option(False, "-l", "--latest", help="更新到最新版本"),
):
    """检查/更新 OpenTrade"""
    from opentrade.cli.updater import check_update, perform_update

    if check:
        update_info = check_update()

        if update_info["has_update"]:
            print(f"\n[yellow]新版本可用: {update_info['latest']}[/yellow]")
            print(f"当前版本: {update_info['current']}")
            print(f"更新大小: {update_info['size']}")

            if latest:
                perform_update()
        else:
            print("\n[green]✅ 已经是最新版本[/green]")
    else:
        print("使用 --check 检查更新")


# 入口点
def run():
    """运行 CLI"""
    main()


if __name__ == "__main__":
    run()
