"""
OpenTrade 协调 Agent - 多 Agent 协作
"""

import json
from typing import Optional

from opentrade.agents.base import (
    BaseAgent,
    MarketState,
    SignalType,
    SignalConfidence,
    TradeDecision,
)
from opentrade.core.config import get_config


class CoordinatorAgent(BaseAgent):
    """协调 Agent - 多 Agent 协作中枢
    
    负责协调各个专业 Agent 的分析结果，
    综合决策生成最终的交易信号。
    """
    
    @property
    def name(self) -> str:
        return "coordinator"
    
    @property
    def description(self) -> str:
        return "综合协调各专业 Agent，生成最终交易决策"
    
    def __init__(self):
        self.config = get_config()
        # 延迟初始化各专业 Agent
        self._market_agent = None
        self._strategy_agent = None
        self._risk_agent = None
        self._onchain_agent = None
        self._sentiment_agent = None
        self._macro_agent = None
    
    async def _get_market_agent(self):
        """获取市场 Agent"""
        if self._market_agent is None:
            from opentrade.agents.market import MarketAgent
            self._market_agent = MarketAgent()
        return self._market_agent
    
    async def _get_strategy_agent(self):
        """获取策略 Agent"""
        if self._strategy_agent is None:
            from opentrade.agents.strategy import StrategyAgent
            self._strategy_agent = StrategyAgent()
        return self._strategy_agent
    
    async def _get_risk_agent(self):
        """获取风控 Agent"""
        if self._risk_agent is None:
            from opentrade.agents.risk import RiskAgent
            self._risk_agent = RiskAgent()
        return self._risk_agent
    
    async def _get_onchain_agent(self):
        """获取链上 Agent"""
        if self._onchain_agent is None:
            from opentrade.agents.onchain import OnChainAgent
            self._onchain_agent = OnChainAgent()
        return self._onchain_agent
    
    async def _get_sentiment_agent(self):
        """获取情绪 Agent"""
        if self._sentiment_agent is None:
            from opentrade.agents.sentiment import SentimentAgent
            self._sentiment_agent = SentimentAgent()
        return self._sentiment_agent
    
    async def _get_macro_agent(self):
        """获取宏观 Agent"""
        if self._macro_agent is None:
            from opentrade.agents.macro import MacroAgent
            self._macro_agent = MacroAgent()
        return self._macro_agent
    
    async def analyze(
        self,
        market_state: MarketState,
        positions: list = None,
        recent_trades: list = None,
    ) -> TradeDecision:
        """综合分析并生成决策
        
        Args:
            market_state: 市场状态
            positions: 当前持仓
            recent_trades: 最近交易
        """
        # 1. 并行收集各 Agent 分析结果
        import asyncio
        
        agents = [
            self._get_market_agent(),
            self._get_strategy_agent(),
            self._get_risk_agent(),
            self._get_onchain_agent(),
            self._get_sentiment_agent(),
            self._get_macro_agent(),
        ]
        
        # 并发执行
        results = await asyncio.gather(
            *(agent.analyze(market_state) for agent in agents),
            return_exceptions=True
        ]
        
        # 解析结果
        market_result = results[0]
        strategy_result = results[1]
        risk_result = results[2]
        onchain_result = results[3]
        sentiment_result = results[4]
        macro_result = results[5]
        
        # 2. 综合分析
        decision = await self._synthesize_decision(
            market_state,
            market_result,
            strategy_result,
            risk_result,
            onchain_result,
            sentiment_result,
            macro_result,
            positions,
            recent_trades,
        )
        
        return decision
    
    async def _synthesize_decision(
        self,
        market_state: MarketState,
        market_result: dict,
        strategy_result: dict,
        risk_result: dict,
        onchain_result: dict,
        sentiment_result: dict,
        macro_result: dict,
        positions: list,
        recent_trades: list,
    ) -> TradeDecision:
        """综合各 Agent 结果生成决策"""
        
        # 计算综合置信度
        weights = {
            "market": 0.25,
            "strategy": 0.20,
            "risk": 0.25,
            "onchain": 0.10,
            "sentiment": 0.10,
            "macro": 0.10,
        }
        
        # 各 Agent 的信号方向 (1=Bullish, -1=Bearish, 0=Neutral)
        market_signal = market_result.get("signal_score", 0) * weights["market"]
        strategy_signal = strategy_result.get("signal_score", 0) * weights["strategy"]
        risk_signal = risk_result.get("signal_score", 0) * weights["risk"]  # 风控越低越好
        onchain_signal = onchain_result.get("signal_score", 0) * weights["onchain"]
        sentiment_signal = sentiment_result.get("signal_score", 0) * weights["sentiment"]
        macro_signal = macro_result.get("signal_score", 0) * weights["macro"]
        
        # 综合信号
        total_signal = (
            market_signal +
            strategy_signal +
            risk_signal +
            onchain_signal +
            sentiment_signal +
            macro_signal
        )
        
        # 计算综合置信度
        technical_conf = market_result.get("confidence", 0.5)
        fundamental_conf = (strategy_result.get("confidence", 0.5) + macro_result.get("confidence", 0.5)) / 2
        sentiment_conf = (sentiment_result.get("confidence", 0.5) + onchain_result.get("confidence", 0.5)) / 2
        
        overall_confidence = (
            technical_conf * 0.4 +
            fundamental_conf * 0.35 +
            sentiment_conf * 0.25
        )
        
        # 确定动作
        if abs(total_signal) < 0.1:
            action = SignalType.HOLD
        elif total_signal > 0:
            action = SignalType.BUY if market_state.price < market_state.ohlcv_1h.get("close", 0) else SignalType.SHORT
        else:
            action = SignalType.SELL if market_state.price < market_state.ohlcv_1h.get("close", 0) else SignalType.COVER
        
        # 收集理由
        reasons = []
        reasons.extend(market_result.get("reasons", []))
        reasons.extend(strategy_result.get("reasons", []))
        reasons.extend(risk_result.get("reasons", []))
        if sentiment_result.get("is_extreme"):
            reasons.append(f"情绪极端: 恐惧贪婪指数 {market_state.fear_greed_index}")
        if macro_result.get("risk_events"):
            reasons.append(f"宏观风险: {', '.join(macro_result['risk_events'])}")
        
        # 风险评估
        risk_score = risk_result.get("risk_level", 0.5)
        max_loss = risk_result.get("max_loss_pct", 1.0)
        
        # 计算仓位大小
        size = self._calculate_position_size(
            confidence=overall_confidence,
            risk_score=risk_score,
            current_positions=positions,
        )
        
        # 计算杠杆
        leverage = self._calculate_leverage(
            risk_score=risk_score,
            confidence=overall_confidence,
            market_volatility=market_state.atr / market_state.price if market_state.price > 0 else 0.02,
        )
        
        # 计算止盈止损
        stop_loss_pct, take_profit_pct = self._calculate_sl_tp(
            action=action,
            risk_score=risk_score,
            atr=market_state.atr,
            price=market_state.price,
        )
        
        return TradeDecision(
            action=action,
            symbol=market_state.symbol,
            size=size,
            leverage=leverage,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            confidence=SignalConfidence(
                overall=overall_confidence,
                technical=technical_conf,
                fundamental=fundamental_conf,
                sentiment=sentiment_conf,
            ),
            reasons=reasons,
            strategy_name="Multi-Agent Coordinator",
            risk_score=risk_score,
            max_loss_pct=max_loss,
            risk_check_passed=risk_score < 0.7,
        )
    
    def _calculate_position_size(
        self,
        confidence: float,
        risk_score: float,
        current_positions: list = None,
    ) -> float:
        """计算仓位大小 (0-1)"""
        base_size = confidence * (1 - risk_score * 0.5)
        
        # 减少已有持仓的仓位
        if current_positions:
            current_exposure = sum(p.get("size", 0) * p.get("leverage", 1) for p in current_positions)
            base_size *= (1 - min(current_exposure, 0.5))
        
        return min(max(base_size, 0.01), 0.25)  # 限制在 1%-25%
    
    def _calculate_leverage(
        self,
        risk_score: float,
        confidence: float,
        market_volatility: float,
    ) -> float:
        """计算杠杆"""
        base_leverage = 1.0
        
        # 高置信度 + 低风险 = 高杠杆
        if confidence > 0.7 and risk_score < 0.3:
            base_leverage = 3.0
        elif confidence > 0.6 and risk_score < 0.4:
            base_leverage = 2.0
        elif confidence > 0.5 and risk_score < 0.5:
            base_leverage = 1.5
        
        # 根据波动率调整
        if market_volatility > 0.05:  # 高波动
            base_leverage *= 0.5
        elif market_volatility < 0.02:  # 低波动
            base_leverage *= 1.2
        
        return min(base_leverage, self.config.risk.max_leverage)
    
    def _calculate_sl_tp(
        self,
        action: SignalType,
        risk_score: float,
        atr: float,
        price: float,
    ) -> tuple[Optional[float], Optional[float]]:
        """计算止盈止损"""
        if action in [SignalType.HOLD, SignalType.CLOSE]:
            return None, None
        
        # 止损
        base_stop = self.config.risk.stop_loss_pct
        if risk_score > 0.5:
            base_stop *= 0.8  # 高风险时缩小止损
        stop_loss_pct = base_stop
        
        # 止盈 (风险回报比)
        risk_reward_ratio = 2.0
        if risk_score > 0.5:
            risk_reward_ratio = 1.5
        take_profit_pct = stop_loss_pct * risk_reward_ratio
        
        return stop_loss_pct, take_profit_pct
