"""
OpenTrade Macro Agent - 宏观分析
"""

from typing import Optional

from opentrade.agents.base import BaseAgent, MarketState


class MacroAgent(BaseAgent):
    """宏观分析 Agent
    
    负责宏观市场分析，包括美元指数、
    股票市场、国债收益率等。
    """
    
    @property
    def name(self) -> str:
        return "macro_agent"
    
    @property
    def description(self) -> str:
        return "宏观分析专家，解读宏观经济对加密市场的影响"
    
    async def analyze(self, state: MarketState) -> dict:
        """宏观分析"""
        score = 0.0
        reasons = []
        confidence = 0.5
        risk_events = []
        
        # 美元指数 (DXY)
        dxy = state.dxy_index
        if dxy > 107:
            score -= 0.2
            reasons.append(f"美元强势 DXY: {dxy:.1f}")
            risk_events.append("美元超涨")
        elif dxy > 105:
            score -= 0.1
            reasons.append(f"美元偏强 DXY: {dxy:.1f}")
        elif dxy < 100:
            score += 0.15
            reasons.append(f"美元弱势 DXY: {dxy:.1f}")
        
        # S&P 500
        sp500 = state.sp500_change
        if sp500 > 0.02:
            score += 0.1
            reasons.append(f"风险情绪回暖 S&P: {sp500:+.2%}")
        elif sp500 < -0.02:
            score -= 0.15
            reasons.append(f"风险情绪恶化 S&P: {sp500:+.2%}")
            risk_events.append("股市下跌")
        
        # 黄金
        gold = state.gold_price
        gold_change = (gold - 2000) / 2000  # 简化的变化率
        if gold_change > 0.1:
            score += 0.1
            reasons.append(f"黄金上涨避险")
        
        # 美债收益率
        bond_yield = state.bond_yield_10y
        if bond_yield > 4.5:
            score -= 0.15
            reasons.append(f"高收益率 {bond_yield:.2f}% 压力")
            risk_events.append("收益率飙升")
        elif bond_yield < 3.5:
            score += 0.05
        
        # VIX
        vix = state.vix_index
        if vix > 25:
            score -= 0.15
            reasons.append(f"市场恐慌 VIX: {vix:.1f}")
            risk_events.append("波动率飙升")
        elif vix < 15:
            score += 0.05
        
        # 宏观风险评估
        macro_risk_score = len(risk_events) * 0.2
        if macro_risk_score > 0.5:
            score -= 0.2
            reasons.append(f"宏观风险累积: {len(risk_events)}个事件")
        
        # 标准化
        score = max(-1, min(1, score / 4))
        
        return {
            "signal_score": score,
            "confidence": confidence,
            "reasons": reasons,
            "risk_events": risk_events,
            "indicators": {
                "dxy": dxy,
                "sp500": sp500,
                "gold": gold,
                "bond_yield": bond_yield,
                "vix": vix,
            },
        }
