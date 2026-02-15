"""
OpenTrade Risk Agent - 风险管理
"""

from typing import Optional

from opentrade.agents.base import BaseAgent, MarketState
from opentrade.core.config import get_config


class RiskAgent(BaseAgent):
    """风险控制 Agent
    
    负责评估交易风险，执行风控规则，
    确保交易在可接受的风险范围内。
    """
    
    @property
    def name(self) -> str:
        return "risk_agent"
    
    @property
    def description(self) -> str:
        return "风险控制专家，确保每笔交易在安全范围内"
    
    def __init__(self):
        self.config = get_config()
    
    async def analyze(
        self,
        state: MarketState,
        current_positions: list = None,
        recent_pnl: float = None,
        daily_loss: float = None,
    ) -> dict:
        """风险分析
        
        Args:
            state: 市场状态
            current_positions: 当前持仓
            recent_pnl: 最近交易盈亏
            daily_loss: 当日亏损
        """
        risk_factors = []
        risk_score = 0.3  # 基础风险
        reasons = []
        can_trade = True
        
        # 1. 市场风险评估
        market_risk = self._assess_market_risk(state)
        risk_score += market_risk["score"]
        reasons.extend(market_risk["reasons"])
        
        # 2. 持仓风险评估
        position_risk = self._assess_position_risk(current_positions)
        risk_score += position_risk["score"]
        reasons.extend(position_risk["reasons"])
        
        # 3. 亏损风险评估
        loss_risk = self._assess_loss_risk(daily_loss)
        risk_score += loss_risk["score"]
        reasons.extend(loss_risk["reasons"])
        
        # 4. 综合评估
        risk_level, max_loss = self._calculate_risk_level(risk_score)
        
        # 5. 检查是否允许交易
        can_trade = risk_level in ["low", "medium"]
        if daily_loss and daily_loss < -self.config.risk.max_daily_loss_pct:
            can_trade = False
            reasons.append("达到每日止损限额，暂停交易")
        
        return {
            "signal_score": -risk_score,  # 风险越高，信号越负
            "confidence": 0.8,
            "risk_level": risk_score,
            "risk_level_category": risk_level,
            "max_loss_pct": max_loss,
            "can_trade": can_trade,
            "reasons": reasons,
            "risk_factors": risk_factors,
        }
    
    def _assess_market_risk(self, state: MarketState) -> dict:
        """评估市场风险"""
        score = 0.0
        reasons = []
        
        # 波动率风险
        volatility = state.atr / state.price if state.price > 0 else 0.02
        if volatility > 0.05:
            score += 0.2
            reasons.append(f"高波动: {volatility:.2%}")
        elif volatility > 0.03:
            score += 0.1
            reasons.append(f"中等波动: {volatility:.2%}")
        
        # 价格位置风险 (接近强平或支撑)
        if state.liquidation_price and state.price:
            distance_to_liq = abs(state.price - state.liquidation_price) / state.price
            if distance_to_liq < 0.1:
                score += 0.3
                reasons.append("接近强平价格")
            elif distance_to_liq < 0.2:
                score += 0.15
        
        # 资金费率极端
        if abs(state.funding_rate) > 0.1:
            score += 0.1
            reasons.append(f"资金费率极端: {state.funding_rate:.4f}")
        
        # 市场情绪极端
        if state.fear_greed_index < 20 or state.fear_greed_index > 80:
            score += 0.1
            reasons.append(f"情绪极端: {state.fear_greed_index}")
        
        return {"score": score, "reasons": reasons}
    
    def _assess_position_risk(self, positions: list) -> dict:
        """评估持仓风险"""
        if not positions:
            return {"score": 0.0, "reasons": []}
        
        score = 0.0
        reasons = []
        
        # 持仓数量
        if len(positions) >= self.config.risk.max_open_positions:
            score += 0.3
            reasons.append(f"持仓已达上限: {len(positions)}")
        
        # 总杠杆
        total_exposure = sum(
            p.get("size", 0) * p.get("leverage", 1)
            for p in positions
        )
        if total_exposure > 0.5:
            score += 0.2
            reasons.append(f"总敞口过高: {total_exposure:.1%}")
        
        # 未实现亏损
        total_unrealized_pnl = sum(
            p.get("unrealized_pnl", 0) for p in positions
        )
        if total_unrealized_pnl < 0:
            loss_ratio = abs(total_unrealized_pnl)
            if loss_ratio > 0.03:
                score += 0.2
                reasons.append(f"未实现亏损: {loss_ratio:.2%}")
        
        return {"score": score, "reasons": reasons}
    
    def _assess_loss_risk(self, daily_loss: float) -> dict:
        """评估日内亏损风险"""
        if not daily_loss:
            return {"score": 0.0, "reasons": []}
        
        score = 0.0
        reasons = []
        
        daily_loss_pct = daily_loss  # 假设是比例
        
        if daily_loss_pct < -0.02:
            score += 0.1
            reasons.append(f"日内亏损: {daily_loss_pct:.2%}")
        if daily_loss_pct < -0.05:
            score += 0.3
            reasons.append("接近每日止损")
        
        return {"score": score, "reasons": reasons}
    
    def _calculate_risk_level(self, risk_score: float) -> tuple[str, float]:
        """计算风险等级和最大亏损"""
        if risk_score < 0.3:
            return "low", 1.0
        elif risk_score < 0.5:
            return "medium", 2.0
        elif risk_score < 0.7:
            return "high", 3.0
        else:
            return "extreme", 5.0


class RiskController:
    """风险控制器 - 执行风控规则"""
    
    def __init__(self):
        self.config = get_config()
    
    def check_trade(self, decision: dict, positions: list, account_balance: float) -> dict:
        """检查交易是否符合风控规则"""
        errors = []
        warnings = []
        approved = True
        
        # 1. 检查仓位限制
        position_value = decision.get("size", 0) * decision.get("leverage", 1)
        max_position = self.config.risk.max_position_pct * account_balance
        
        if position_value > max_position:
            errors.append(f"仓位超限: {position_value:.2%} > {max_position:.2%}")
            approved = False
        
        # 2. 检查杠杆限制
        if decision.get("leverage", 1) > self.config.risk.max_leverage:
            errors.append(f"杠杆超限: {decision['leverage']}x > {self.config.risk.max_leverage}x")
            decision["leverage"] = self.config.risk.max_leverage
        
        # 3. 检查持仓数量
        if len(positions) >= self.config.risk.max_open_positions:
            errors.append(f"持仓数量超限: {len(positions)} >= {self.config.risk.max_open_positions}")
            approved = False
        
        # 4. 检查止损设置
        if not decision.get("stop_loss_pct"):
            errors.append("未设置止损")
            approved = False
        elif decision["stop_loss_pct"] > self.config.risk.stop_loss_pct * 1.5:
            warnings.append(f"止损过大: {decision['stop_loss_pct']:.2%}")
        
        # 5. 检查每日亏损
        # TODO: 检查当日累计亏损
        
        # 6. 检查资金限制
        if decision.get("size", 0) > 0.25:
            warnings.append("单笔仓位过大，建议不超过25%")
        
        return {
            "approved": approved,
            "errors": errors,
            "warnings": warnings,
            "modified_decision": decision,
        }
    
    def calculate_position_size(
        self,
        confidence: float,
        risk_score: float,
        account_balance: float,
    ) -> float:
        """计算安全仓位大小"""
        # Kelly Criterion 简化版
        kelly = confidence - (1 - confidence) / (1 / (risk_score + 0.1) - 1)
        
        # 使用半凯利公式
        position_pct = max(0.01, kelly * 0.5)
        
        # 限制最大仓位
        max_pct = self.config.risk.max_position_pct
        position_pct = min(position_pct, max_pct)
        
        return position_pct
