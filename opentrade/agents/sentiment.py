"""
OpenTrade Sentiment Agent - 情绪分析
"""

from typing import Optional

from opentrade.agents.base import BaseAgent, MarketState


class SentimentAgent(BaseAgent):
    """情绪分析 Agent
    
    负责市场情绪分析，包括恐惧贪婪指数、
    社交媒体情绪、新闻情绪等。
    """
    
    @property
    def name(self) -> str:
        return "sentiment_agent"
    
    @property
    def description(self) -> str:
        return "情绪分析专家，解读市场恐惧与贪婪"
    
    async def analyze(self, state: MarketState) -> dict:
        """情绪分析"""
        score = 0.0
        reasons = []
        confidence = 0.55
        is_extreme = False
        
        # 恐惧贪婪指数
        fg = state.fear_greed_index
        if fg <= 25:
            score += 0.3
            reasons.append(f"极度恐惧: {fg}/100")
            is_extreme = True
        elif fg <= 40:
            score += 0.15
            reasons.append(f"恐惧: {fg}/100")
        elif fg >= 75:
            score -= 0.3
            reasons.append(f"极度贪婪: {fg}/100")
            is_extreme = True
        elif fg >= 60:
            score -= 0.15
            reasons.append(f"贪婪: {fg}/100")
        else:
            score += 0.05  # 中性偏多
        
        # 社交情绪
        sentiment = state.social_sentiment
        if sentiment > 0.3:
            score -= 0.1
            reasons.append("社交情绪偏多")
        elif sentiment < -0.3:
            score += 0.1
            reasons.append("社交情绪偏空")
        
        # Twitter 讨论量
        twitter_vol = state.twitter_volume
        if twitter_vol > 50000:
            if sentiment > 0.2:
                score -= 0.1
                reasons.append("高讨论 + 乐观情绪")
            else:
                score += 0.05
        
        # VIX 指数 (市场恐慌指标)
        vix = state.vix_index
        if vix > 30:
            score += 0.1
            reasons.append(f"VIX升高: {vix:.1f} (恐慌)")
        elif vix < 15:
            score -= 0.1
            reasons.append(f"VIX低位: {vix:.1f} (自满)")
        
        # 标准化
        score = max(-1, min(1, score / 4))
        
        return {
            "signal_score": score,
            "confidence": confidence,
            "reasons": reasons,
            "is_extreme": is_extreme,
            "indicators": {
                "fear_greed": fg,
                "social_sentiment": sentiment,
                "twitter_volume": twitter_vol,
                "vix": vix,
            },
        }
