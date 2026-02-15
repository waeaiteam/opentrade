"""
OpenTrade 回测服务
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from statistics import mean, stdev

from opentrade.core.config import get_config
from opentrade.core.database import db
from opentrade.models.trade import Trade, TradeSide, TradeAction, TradeStatus


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "total_pnl_percent": self.total_pnl_percent,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "profit_factor": self.profit_factor,
        }


class BacktestService:
    """回测服务
    
    负责策略回测、历史数据模拟、
    性能评估和报告生成。
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def run_backtest(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime = None,
        symbol: str = "BTC/USDT",
        initial_capital: float = 10000.0,
        leverage: float = 1.0,
    ) -> BacktestResult:
        """运行回测"""
        end_date = end_date or datetime.utcnow()
        
        # 获取历史数据
        from opentrade.services.data_service import data_service
        
        ohlcv = await data_service.fetch_ohlcv(
            symbol,
            timeframe="1h",
            limit=24 * (end_date - start_date).days + 100,
        )
        
        # 过滤日期范围
        ohlcv = [
            d for d in ohlcv
            if start_date.timestamp() * 1000 <= d["timestamp"] <= end_date.timestamp() * 1000
        ]
        
        # 模拟交易
        result = self._simulate_trades(
            ohlcv=ohlcv,
            strategy_name=strategy_name,
            initial_capital=initial_capital,
            leverage=leverage,
        )
        
        return result
    
    def _simulate_trades(
        self,
        ohlcv: list[dict],
        strategy_name: str,
        initial_capital: float,
        leverage: float,
    ) -> BacktestResult:
        """模拟交易"""
        result = BacktestResult()
        
        capital = initial_capital
        position = None  # (side, entry_price, size)
        equity_curve = [(ohlcv[0]["timestamp"], capital)]
        
        for i, candle in enumerate(ohlcv[1:], 1):
            price = candle["close"]
            timestamp = candle["timestamp"]
            
            # 更新持仓价值
            if position:
                if position[0] == "long":
                    unrealized = (price - position[1]) / position[1]
                else:
                    unrealized = (position[1] - price) / position[1]
                
                equity = position[2] * (1 + unrealized * leverage)
                equity_curve.append((timestamp, capital * equity))
            
            # 生成交易信号 (基于简单规则)
            signal = self._generate_signal(ohlcv[:i+1], strategy_name)
            
            if signal == "buy" and not position:
                # 开多
                size = capital * 0.1  # 10% 仓位
                quantity = size / price
                position = ("long", price, size)
                
                result.trades.append({
                    "action": "open_long",
                    "entry_price": price,
                    "quantity": quantity,
                    "timestamp": timestamp,
                })
            
            elif signal == "sell" and position and position[0] == "long":
                # 平多
                pnl = (price - position[1]) / position[1] * leverage
                capital = capital * (1 + pnl)
                
                result.trades.append({
                    "action": "close_long",
                    "exit_price": price,
                    "pnl": pnl,
                    "timestamp": timestamp,
                })
                
                if pnl > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                
                position = None
            
            elif signal == "short" and not position:
                # 开空
                size = capital * 0.1
                quantity = size / price
                position = ("short", price, size)
                
                result.trades.append({
                    "action": "open_short",
                    "entry_price": price,
                    "quantity": quantity,
                    "timestamp": timestamp,
                })
            
            elif signal == "cover" and position and position[0] == "short":
                # 平空
                pnl = (position[1] - price) / position[1] * leverage
                capital = capital * (1 + pnl)
                
                result.trades.append({
                    "action": "close_short",
                    "exit_price": price,
                    "pnl": pnl,
                    "timestamp": timestamp,
                })
                
                if pnl > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                
                position = None
        
        # 平仓剩余持仓
        if position:
            price = ohlcv[-1]["close"]
            if position[0] == "long":
                pnl = (price - position[1]) / position[1] * leverage
            else:
                pnl = (position[1] - price) / position[1] * leverage
            
            capital = capital * (1 + pnl)
            result.trades.append({
                "action": "force_close",
                "exit_price": price,
                "pnl": pnl,
                "timestamp": ohlcv[-1]["timestamp"],
            })
        
        # 计算结果
        result.total_trades = len(result.trades)
        result.total_pnl = capital - initial_capital
        result.total_pnl_percent = (capital - initial_capital) / initial_capital
        
        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades
        
        # 计算最大回撤
        result.max_drawdown = self._calculate_max_drawdown(equity_curve)
        result.equity_curve = equity_curve
        
        # 计算夏普比率
        result.sharpe_ratio = self._calculate_sharpe_ratio(result.trades)
        
        # 计算盈亏比
        if result.losing_trades > 0:
            avg_win = sum(t["pnl"] for t in result.trades if t["pnl"] > 0) / result.winning_trades
            avg_loss = abs(sum(t["pnl"] for t in result.trades if t["pnl"] < 0) / result.losing_trades)
            result.profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")
        
        return result
    
    def _generate_signal(self, ohlcv: list[dict], strategy_name: str) -> str:
        """生成交易信号"""
        if len(ohlcv) < 30:
            return "hold"
        
        closes = [d["close"] for d in ohlcv]
        
        if strategy_name == "trend_following":
            # 简单趋势策略
            sma_fast = sum(closes[-9:]) / 9
            sma_slow = sum(closes[-21:]) / 21
            
            prev_fast = sum(closes[-10:-1]) / 9
            prev_slow = sum(closes[-22:-1]) / 21
            
            if sma_fast > sma_slow and prev_fast <= prev_slow:
                return "buy"
            elif sma_fast < sma_slow and prev_fast >= prev_slow:
                return "short"
        
        elif strategy_name == "mean_reversion":
            # 均值回归策略
            bb_upper = sum(closes[-20:]) / 20 + 2 * stdev(closes[-20:])
            bb_lower = sum(closes[-20:]) / 20 - 2 * stdev(closes[-20:])
            
            price = closes[-1]
            
            if price > bb_upper:
                return "sell"
            elif price < bb_lower:
                return "buy"
        
        elif strategy_name == "rsi_strategy":
            # RSI 策略
            gains = []
            losses = []
            for i in range(1, len(closes)):
                change = closes[i] - closes[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))
            
            if rsi < 30:
                return "buy"
            elif rsi > 70:
                return "sell"
        
        return "hold"
    
    def _calculate_max_drawdown(self, equity_curve: list) -> float:
        """计算最大回撤"""
        if not equity_curve:
            return 0
        
        max_equity = equity_curve[0][1]
        max_drawdown = 0
        
        for timestamp, equity in equity_curve:
            if equity > max_equity:
                max_equity = equity
            
            drawdown = (max_equity - equity) / max_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _calculate_sharpe_ratio(self, trades: list) -> float:
        """计算夏普比率"""
        if len(trades) < 2:
            return 0
        
        pnls = [t["pnl"] for t in trades]
        returns = [p / 100 for p in pnls]  # 假设以百分比计算
        
        if mean(returns) == 0:
            return 0
        
        avg_return = mean(returns)
        std_return = stdev(returns) if len(returns) > 1 else 0
        
        if std_return == 0:
            return 0
        
        # 年化夏普 (假设1小时周期，约8760小时/年)
        annualized_return = avg_return * 8760
        annualized_std = std_return * (8760 ** 0.5)
        
        return annualized_return / annualized_std if annualized_std > 0 else 0
    
    def generate_report(self, result: BacktestResult, output_file: str = None) -> str:
        """生成回测报告"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>OpenTrade 回测报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
        .metric {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
        .metric h3 {{ margin: 0 0 10px 0; color: #666; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .positive {{ color: green; }}
        .negative {{ color: red; }}
    </style>
</head>
<body>
    <h1>📊 OpenTrade 回测报告</h1>
    
    <h2>核心指标</h2>
    <div class="metrics">
        <div class="metric">
            <h3>总交易次数</h3>
            <div class="value">{result.total_trades}</div>
        </div>
        <div class="metric">
            <h3>胜率</h3>
            <div class="value">{result.win_rate:.2%}</div>
        </div>
        <div class="metric">
            <h3>总收益</h3>
            <div class="value {'positive' if result.total_pnl > 0 else 'negative'}">
                {result.total_pnl:+.2%}
            </div>
        </div>
        <div class="metric">
            <h3>最大回撤</h3>
            <div class="value negative">{result.max_drawdown:.2%}</div>
        </div>
        <div class="metric">
            <h3>夏普比率</h3>
            <div class="value">{result.sharpe_ratio:.2f}</div>
        </div>
        <div class="metric">
            <h3>盈亏比</h3>
            <div class="value">{result.profit_factor:.2f}</div>
        </div>
    </div>
    
    <h2>交易记录</h2>
    <table>
        <tr><th>时间</th><th>操作</th><th>价格</th><th>盈亏</th></tr>
        {''.join(f'<tr><td>{t["timestamp"]}</td><td>{t["action"]}</td><td>{t.get("entry_price", t.get("exit_price", 0)):.2f}</td><td class="{"positive" if t.get("pnl", 0) > 0 else "negative"}">{t.get("pnl", 0):.2%}</td></tr>' for t in result.trades)}
    </table>
</body>
</html>
        """
        
        if output_file:
            with open(output_file, "w") as f:
                f.write(html)
        
        return html
