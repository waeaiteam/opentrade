"""
OpenTrade OnChain Agent - 链上数据分析
"""


from opentrade.agents.base import BaseAgent, MarketState


class OnChainAgent(BaseAgent):
    """链上数据 Agent
    
    负责链上数据分析，包括资金流向、
    巨鲸行为、稳定币数据等。
    """

    @property
    def name(self) -> str:
        return "onchain_agent"

    @property
    def description(self) -> str:
        return "链上数据专家，分析交易所净流入、巨鲸行为"

    async def analyze(self, state: MarketState) -> dict:
        """链上分析"""
        score = 0.0
        reasons = []
        confidence = 0.6

        # 交易所净流入分析
        net_flow = state.exchange_net_flow
        if net_flow > 0:
            score += 0.2
            reasons.append(f"资金净流入: {net_flow:+,.0f}")
        elif net_flow < 0:
            score -= 0.2
            reasons.append(f"资金净流出: {net_flow:+,.0f}")

        # 巨鲸交易
        if state.whale_transactions > 10:
            score += 0.15
            reasons.append(f"巨鲸活跃: {state.whale_transactions}笔")
        elif state.whale_transactions > 5:
            score += 0.05

        # 稳定币数据
        stablecoin = state.stablecoin_mint
        if stablecoin > 1e8:  # > 100M
            score += 0.1
            reasons.append(f"稳定币大量铸造: ${stablecoin/1e6:.0f}M")
        elif stablecoin < -1e8:
            score -= 0.1
            reasons.append(f"稳定币大量赎回: ${abs(stablecoin)/1e6:.0f}M")

        # OI 变化
        oi_change = state.open_interest_change
        if oi_change > 0.05:
            score += 0.1
            reasons.append(f"持仓增加: {oi_change:.1%}")
        elif oi_change > 0.02:
            score += 0.05
        elif oi_change < -0.05:
            score -= 0.1
            reasons.append(f"持仓减少: {oi_change:.1%}")

        # 资金费率
        funding = state.funding_rate
        if funding > 0.05:
            score -= 0.1  # 高资金费可能是顶部信号
            reasons.append("高资金费率: 多头拥挤")
        elif funding < -0.05:
            score += 0.1  # 负资金费可能是底部信号
            reasons.append("负资金费率: 空头拥挤")

        # 标准化
        score = max(-1, min(1, score / 4))

        return {
            "signal_score": score,
            "confidence": confidence,
            "reasons": reasons,
            "indicators": {
                "net_flow": net_flow,
                "whale_tx": state.whale_transactions,
                "stablecoin": stablecoin,
                "oi_change": oi_change,
                "funding": funding,
            },
        }
