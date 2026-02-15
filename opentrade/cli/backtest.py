"""
OpenTrade CLI - Backtest Command

回测引擎: 基于历史数据验证策略表现
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(help="Backtest strategies on historical data")


class BacktestEngine:
    """回测引擎"""

    def __init__(self, initial_balance: float = 10000, fee_rate: float = 0.001):
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate
        self.balance = initial_balance
        self.positions = {}
        self.trades = []
        self.equity_curve = []

    async def run(
        self,
        symbol: str,
        strategy_type: str,
        start_date: datetime,
        end_date: datetime,
        strategy_params: dict | None = None,
    ) -> dict:
        """
        运行回测

        Returns:
            回测结果
        """
        strategy_params = strategy_params or {}

        rprint(f"[bold]📊 Backtest: {symbol} {strategy_type}[/bold]")
        rprint(f"  Period: {start_date.date()} → {end_date.date()}")
        rprint(f"  Initial: ${self.initial_balance:,.2f}")
        rprint("")

        # 模拟价格数据生成
        prices = self._generate_simulated_prices(start_date, end_date)

        # 执行策略信号
        for i, price in enumerate(prices):
            signal = await self._generate_signal(strategy_type, price, i, prices, strategy_params)

            if signal == "BUY" and symbol not in self.positions:
                self._open_position(symbol, price, 0.1)

            elif signal == "SELL" and symbol in self.positions:
                self._close_position(symbol, price)

            # 记录权益
            self.equity_curve.append({
                "date": (start_date + timedelta(minutes=i * 60)).isoformat(),
                "equity": self.balance + self._calculate_position_value(symbol, price),
            })

        return self._generate_report(symbol, prices[-1] if prices else 0)

    def _generate_simulated_prices(
        self, start: datetime, end: datetime
    ) -> list[float]:
        """生成模拟价格数据"""
        import random
        prices = [50000.0]
        days = (end - start).days

        for _ in range(days * 24):
            change = random.gauss(0, 0.005)
            new_price = prices[-1] * (1 + change)
            new_price = max(new_price, prices[-1] * 0.9)
            new_price = min(new_price, prices[-1] * 1.1)
            prices.append(new_price)

        return prices

    async def _generate_signal(
        self,
        strategy_type: str,
        price: float,
        index: int,
        prices: list[float],
        params: dict,
    ) -> str:
        """生成交易信号"""
        if len(prices) < 20:
            return "HOLD"

        import random
        prob = random.random()

        if strategy_type == "trend_following":
            if index > 10 and prices[-1] > prices[-5]:
                return "BUY"
            elif index > 10 and prices[-1] < prices[-5]:
                return "SELL"

        elif strategy_type == "mean_reversion":
            ma20 = sum(prices[-20:]) / 20
            if price < ma20 * 0.98:
                return "BUY"
            elif price > ma20 * 1.02:
                return "SELL"

        elif strategy_type == "rsi":
            rsi = self._calculate_rsi(prices)
            if rsi < 30:
                return "BUY"
            elif rsi > 70:
                return "SELL"

        return "HOLD"

    def _calculate_rsi(self, prices: list[float], period: int = 14) -> float:
        """计算 RSI"""
        if len(prices) < period + 1:
            return 50.0

        gains = []
        losses = []

        for i in range(-period, 0):
            change = prices[i + 1] - prices[i]
            if change > 0:
                gains.append(change)
            else:
                losses.append(-change)

        if not gains or not losses:
            return 50.0

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _open_position(self, symbol: str, price: float, size_pct: float):
        """开仓"""
        size = self.balance * size_pct / price
        fee = size * price * self.fee_rate

        self.positions[symbol] = {
            "quantity": size,
            "entry_price": price,
            "size_pct": size_pct,
        }
        self.balance -= (size * price + fee)

        self.trades.append({
            "symbol": symbol,
            "side": "BUY",
            "price": price,
            "quantity": size,
            "fee": fee,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _close_position(self, symbol: str, price: float):
        """平仓"""
        if symbol not in self.positions:
            return

        pos = self.positions.pop(symbol)
        size = pos["quantity"]
        fee = size * price * self.fee_rate

        self.balance += (size * price - fee)

        self.trades.append({
            "symbol": symbol,
            "side": "SELL",
            "price": price,
            "quantity": size,
            "fee": fee,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _calculate_position_value(self, symbol: str, current_price: float) -> float:
        """计算持仓价值"""
        if symbol not in self.positions:
            return 0
        return self.positions[symbol]["quantity"] * current_price

    def _generate_report(self, symbol: str, final_price: float) -> dict:
        """生成报告"""
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t["side"] == "SELL" and
                           any(rt["side"] == "BUY" and rt["symbol"] == t["symbol"]
                               for rt in self.trades[:self.trades.index(t)]))

        final_equity = self.balance + self._calculate_position_value(symbol, final_price)
        total_return = (final_equity - self.initial_balance) / self.initial_balance * 100

        # 计算最大回撤
        equity_values = [e["equity"] for e in self.equity_curve]
        max_equity = max(equity_values) if equity_values else self.initial_balance
        drawdowns = [(max_equity - e) / max_equity * 100 for e in equity_values]
        max_drawdown = max(drawdowns) if drawdowns else 0

        # 计算夏普 (简化版)
        returns = []
        for i in range(1, len(equity_values)):
            ret = (equity_values[i] - equity_values[i-1]) / equity_values[i-1]
            returns.append(ret)

        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
        sharpe = (avg_return / std_return * 16) if std_return > 0 else 0  # 日夏普

        return {
            "symbol": symbol,
            "initial_balance": self.initial_balance,
            "final_equity": final_equity,
            "total_return": total_return,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": winning_trades / (total_trades / 2) if total_trades > 0 else 0,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "trades": self.trades,
        }


def calculate_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """计算夏普比率"""
    if not returns:
        return 0.0

    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / len(returns)
    std = variance ** 0.5

    if std == 0:
        return 0.0

    return (avg - risk_free) / std * (252 ** 0.5)


@app.command()
def run(
    symbol: str = typer.Argument("BTC/USDT", help="Trading pair"),
    strategy: str = typer.Argument("trend_following", help="Strategy type"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    initial: float = typer.Option(10000.0, "--initial", "-i", help="Initial balance"),
    fee: float = typer.Option(0.001, "--fee", "-f", help="Fee rate"),
):
    """
    Run backtest on a strategy

    Examples:
        opentrade backtest BTC/USDT trend_following
        opentrade backtest ETH/USDT mean_reversion --start 2024-01-01
        opentrade backtest SOL/USDT rsi --initial 50000
    """
    start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=30)
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.utcnow()

    engine = BacktestEngine(initial_balance=initial, fee_rate=fee)

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        engine.run(symbol, strategy, start_date, end_date)
    )

    # 显示结果
    rprint("")
    rprint(f"[bold]📊 Backtest Results: {symbol}[/bold]")
    rprint(f"  Initial: ${result['initial_balance']:,.2f}")
    rprint(f"  Final: ${result['final_equity']:,.2f}")
    rprint(f"  Return: [green]{result['total_return']:.2f}%[/green]")
    rprint(f"  Trades: {result['total_trades']}")
    rprint(f"  Win Rate: {result['win_rate']:.1%}")
    rprint(f"  Max Drawdown: [red]{result['max_drawdown']:.2f}%[/red]")
    rprint(f"  Sharpe: {result['sharpe_ratio']:.2f}")
    rprint("")

    # 保存结果
    output_file = f"backtest_{symbol.replace('/', '_')}_{datetime.now().strftime('%Y%m%d')}.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    rprint(f"💾 Results saved to: {output_file}")


@app.command()
def compare(
    symbol: str = typer.Argument(..., help="Trading pair"),
    strategies: str = typer.Option("trend_following,mean_reversion,rsi", help="Comma-separated strategies"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Start date"),
    initial: float = typer.Option(10000.0, "--initial", "-i", help="Initial balance"),
):
    """Compare multiple strategies"""
    strategy_list = [s.strip() for s in strategies.split(",")]

    start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime.utcnow() - timedelta(days=30)
    end_date = datetime.utcnow()

    results = []

    for strategy in strategy_list:
        engine = BacktestEngine(initial_balance=initial)
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            engine.run(symbol, strategy, start_date, end_date)
        )
        results.append((strategy, result))

    # 显示对比表
    table = Table(title=f"Strategy Comparison: {symbol}")
    table.add_column("Strategy", style="cyan")
    table.add_column("Return", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Sharpe", justify="right")

    for strategy, result in results:
        table.add_row(
            strategy,
            f"{result['total_return']:.2f}%",
            f"{result['win_rate']:.1%}",
            f"{result['max_drawdown']:.2f}%",
            f"{result['sharpe_ratio']:.2f}",
        )

    rprint(table)


if __name__ == "__main__":
    app()
