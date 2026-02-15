"""
OpenTrade AI Agent 模块
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class SignalType(str, Enum):
    """交易信号类型"""
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class SignalConfidence(BaseModel):
    """信号置信度"""
    overall: float  # 0-1
    technical: float  # 0-1
    fundamental: float  # 0-1
    sentiment: float  # 0-1


@dataclass
class MarketState:
    """市场状态"""
    symbol: str
    price: float
    timestamp: datetime
    
    # OHLCV
    ohlcv_5m: dict = field(default_factory=dict)
    ohlcv_15m: dict = field(default_factory=dict)
    ohlcv_1h: dict = field(default_factory=dict)
    ohlcv_4h: dict = field(default_factory=dict)
    
    # 订单簿
    orderbook: dict = field(default_factory=dict)
    
    # 资金费率
    funding_rate: float = 0.0
    funding_time: Optional[datetime] = None
    
    # 持仓量
    open_interest: float = 0.0
    open_interest_change: float = 0.0
    
    # 技术指标
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 50.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    bollinger_upper: float = 0.0
    bollinger_middle: float = 0.0
    bollinger_lower: float = 0.0
    atr: float = 0.0
    volume: float = 0.0
    volume_ratio: float = 1.0
    
    # 链上数据
    exchange_net_flow: float = 0.0
    whale_transactions: int = 0
    stablecoin_mint: float = 0.0
    
    # 情绪数据
    fear_greed_index: int = 50
    social_sentiment: float = 0.0
    twitter_volume: int = 0
    
    # 宏观数据
    dxy_index: float = 0.0
    sp500_change: float = 0.0
    gold_price: float = 0.0
    bond_yield_10y: float = 0.0
    vix_index: float = 0.0
    
    def to_prompt_format(self) -> str:
        """转换为 AI prompt 格式"""
        return f"""
=== {self.symbol} 市场状态 ===

📊 当前价格: ${self.price:,.2f}

📈 技术指标:
- EMA(9): {self.ema_fast:.2f}
- EMA(21): {self.ema_slow:.2f}
- RSI(14): {self.rsi:.1f}
- MACD: {self.macd:.2f} (signal: {self.macd_signal:.2f})
- Bollinger Bands: {self.bollinger_lower:.2f} - {self.bollinger_middle:.2f} - {self.bollinger_upper:.2f}
- ATR: {self.atr:.2f}
- 成交量: {self.volume:,.0f} (Ratio: {self.volume_ratio:.2f})

💰 合约数据:
- 资金费率: {self.funding_rate:.4f}%
- 持仓量: {self.open_interest:,.0f}
- OI变化: {self.open_interest_change:+.2f}%

🔗 链上数据:
- 交易所净流入: {self.exchange_net_flow:+,.2f} {self.symbol}
- 巨鲸交易: {self.whale_transactions}
- 稳定币铸造: {self.stablecoin_mint:+,.0f}

😨 情绪指标:
- 恐惧贪婪指数: {self.fear_greed_index}/100
- 社交情绪: {self.social_sentiment:.2f}

🌍 宏观数据:
- 美元指数: {self.dxy_index:.2f}
- S&P 500: {self.sp500_change:+.2f}%
- 黄金: ${self.gold_price:,.2f}
- 10年美债收益率: {self.bond_yield_10y:.2f}%
- VIX: {self.vix_index:.2f}
"""


@dataclass
class TradeDecision:
    """交易决策"""
    action: SignalType
    symbol: str
    size: float  # 仓位大小 (0-1 代表资金比例)
    leverage: float = 1.0
    
    # 止盈止损
    stop_loss: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit: Optional[float] = None
    take_profit_pct: Optional[float] = None
    
    # 置信度
    confidence: SignalConfidence = field(default_factory=lambda: SignalConfidence(
        overall=0.5, technical=0.5, fundamental=0.5, sentiment=0.5
    ))
    
    # 理由
    reasons: list[str] = field(default_factory=list)
    
    # 元数据
    strategy_id: Optional[str] = None
    strategy_name: Optional[str] = None
    strategy_version: str = "1.0.0"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # 风险评估
    risk_score: float = 0.5  # 0-1, 越高风险越大
    max_loss_pct: float = 1.0
    
    # 验证状态
    risk_check_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "action": self.action.value,
            "symbol": self.symbol,
            "size": self.size,
            "leverage": self.leverage,
            "stop_loss": self.stop_loss,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit": self.take_profit,
            "take_profit_pct": self.take_profit_pct,
            "confidence": self.confidence.model_dump(),
            "reasons": self.reasons,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "timestamp": self.timestamp.isoformat(),
            "risk_score": self.risk_score,
            "max_loss_pct": self.max_loss_pct,
            "risk_check_passed": self.risk_check_passed,
        }


class BaseAgent(ABC):
    """AI Agent 基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Agent 描述"""
        pass
    
    @abstractmethod
    async def analyze(self, market_state: MarketState) -> dict:
        """分析方法"""
        pass
    
    async def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return f"""
你是一个专业的加密货币交易分析师，专注于{self.description}。

你将接收市场数据并进行分析，输出结构化的分析结果。
请保持客观、理性，避免情绪化决策。
"""
