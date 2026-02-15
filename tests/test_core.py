"""
OpenTrade 测试包
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def config_data():
    """测试配置数据"""
    return {
        "exchange": {"name": "binance", "testnet": True},
        "ai": {"model": "deepseek/deepseek-chat"},
        "risk": {"max_leverage": 3.0, "stop_loss_pct": 0.05},
    }


@pytest.fixture
def sample_market_state():
    """测试市场状态"""
    from opentrade.agents.base import MarketState
    from datetime import datetime
    
    return MarketState(
        symbol="BTC/USDT",
        price=50000.0,
        timestamp=datetime.utcnow(),
        ohlcv_1h={"close": 50000, "open": 49500, "high": 50200, "low": 49300, "volume": 1000000},
        ema_fast=50100.0,
        ema_slow=49800.0,
        rsi=55.0,
        macd=150.0,
        macd_signal=100.0,
        macd_histogram=50.0,
        bollinger_upper=51000.0,
        bollinger_middle=50000.0,
        bollinger_lower=49000.0,
        atr=500.0,
        volume=1000000.0,
        volume_ratio=1.2,
    )


class TestMarketAgent:
    """市场分析 Agent 测试"""
    
    def test_trend_detection(self, sample_market_state):
        """测试趋势检测"""
        from opentrade.agents.market import MarketAgent
        import asyncio
        
        agent = MarketAgent()
        
        # 价格在EMA上方，应该看涨
        sample_market_state.price = 51000
        
        result = asyncio.get_event_loop().run_until_complete(
            agent.analyze(sample_market_state)
        )
        
        assert "signal_score" in result
        assert "reasons" in result


class TestRiskAgent:
    """风险 Agent 测试"""
    
    def test_risk_calculation(self, config_data):
        """测试风险计算"""
        from opentrade.agents.risk import RiskAgent
        import asyncio
        
        # 模拟配置
        agent = RiskAgent()
        
        # 低波动市场
        from opentrade.agents.base import MarketState
        from datetime import datetime
        
        state = MarketState(
            symbol="BTC/USDT",
            price=50000.0,
            timestamp=datetime.utcnow(),
            atr=500.0,  # 1% 波动率
        )
        
        result = asyncio.get_event_loop().run_until_complete(
            agent.analyze(state)
        )
        
        assert "risk_level" in result


class TestDataService:
    """数据服务测试"""
    
    def test_indicator_calculation(self):
        """测试技术指标计算"""
        from opentrade.services.data_service import DataService
        
        service = DataService()
        
        # 模拟价格数据
        closes = [50000 + i * 100 for i in range(50)]
        
        # 测试 EMA 计算
        ema = service._ema(closes, 9)
        assert ema > 0
        
        # 测试 RSI 计算
        rsi = service._rsi(closes, 14)
        assert 0 <= rsi <= 100


class TestBacktestService:
    """回测服务测试"""
    
    def test_sharpe_calculation(self):
        """夏普比率计算"""
        from opentrade.services.backtest_service import BacktestService
        
        service = BacktestService()
        
        trades = [
            {"pnl": 0.02},
            {"pnl": -0.01},
            {"pnl": 0.03},
            {"pnl": -0.015},
            {"pnl": 0.025},
        ]
        
        sharpe = service._calculate_sharpe_ratio(trades)
        assert sharpe != 0  # 应该能计算出数值


class TestTradeExecutor:
    """交易执行器测试"""
    
    def test_risk_check(self):
        """测试风控检查"""
        from opentrade.services.trade_executor import TradeExecutor
        from opentrade.agents.base import TradeDecision, SignalType, SignalConfidence
        
        executor = TradeExecutor(mode="paper")
        
        decision = TradeDecision(
            action=SignalType.BUY,
            symbol="BTC/USDT",
            size=0.5,  # 50% 仓位 - 超过默认限制
            leverage=5.0,  # 5x 杠杆 - 超过默认限制
            confidence=SignalConfidence(overall=0.3, technical=0.3, fundamental=0.3, sentiment=0.3),
            reasons=["test"],
        )
        
        result = executor._check_risk(decision)
        
        assert "errors" in result
        assert not result["passed"]  # 应该被拦截
