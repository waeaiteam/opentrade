"""
OpenTrade Market Agent - 市场分析
"""


from opentrade.agents.base import BaseAgent, MarketState


class MarketAgent(BaseAgent):
    """市场分析 Agent
    
    负责技术分析和市场状态判断，
    提供交易信号和技术面置信度。
    """

    @property
    def name(self) -> str:
        return "market_agent"

    @property
    def description(self) -> str:
        return "技术分析专家，专注K线形态和技术指标"

    async def analyze(self, state: MarketState) -> dict:
        """技术分析"""
        score = 0.0
        reasons = []
        confidence = 0.5

        # 趋势分析
        trend = self._analyze_trend(state)
        score += trend["score"]
        reasons.extend(trend["reasons"])

        # 动量分析
        momentum = self._analyze_momentum(state)
        score += momentum["score"]
        reasons.extend(momentum["reasons"])

        # 波动率分析
        volatility = self._analyze_volatility(state)

        # 成交量分析
        volume = self._analyze_volume(state)
        score += volume["score"]
        reasons.extend(volume["reasons"])

        # 标准化分数
        score = max(-1, min(1, score / 4))
        confidence = self._calculate_confidence(state)

        return {
            "signal_score": score,
            "confidence": confidence,
            "trend": trend["direction"],
            "momentum": momentum["direction"],
            "reasons": reasons,
            "indicators": {
                "ema_trend": trend["direction"],
                "rsi_level": self._rsi_level(state.rsi),
                "macd_signal": momentum["direction"],
                "volatility": volatility["level"],
            },
        }

    def _analyze_trend(self, state: MarketState) -> dict:
        """趋势分析"""
        score = 0.0
        reasons = []
        direction = "neutral"

        # EMA 交叉
        if state.ema_fast > state.ema_slow:
            score += 0.2
            direction = "bullish"
            reasons.append(f"EMA金叉: 快速{state.ema_fast:.2f} > 慢速{state.ema_slow:.2f}")
        elif state.ema_fast < state.ema_slow:
            score -= 0.2
            direction = "bearish"
            reasons.append(f"EMA死叉: 快速{state.ema_fast:.2f} < 慢速{state.ema_slow:.2f}")

        # 价格位置
        if state.price > state.bollinger_middle:
            score += 0.1
        else:
            score -= 0.1

        # 价格相对EMA
        if state.price > state.ema_slow:
            score += 0.1
            reasons.append("价格在EMA21上方")
        else:
            score -= 0.1
            reasons.append("价格在EMA21下方")

        return {"score": score, "reasons": reasons, "direction": direction}

    def _analyze_momentum(self, state: MarketState) -> dict:
        """动量分析"""
        score = 0.0
        reasons = []
        direction = "neutral"

        # RSI
        if state.rsi > 70:
            score -= 0.15
            reasons.append(f"RSI超买: {state.rsi:.1f}")
        elif state.rsi < 30:
            score += 0.15
            reasons.append(f"RSI超卖: {state.rsi:.1f}")
        elif state.rsi > 55:
            score += 0.1
        elif state.rsi < 45:
            score -= 0.1

        # MACD
        if state.macd_histogram > 0:
            if state.macd_histogram > state.macd_histogram * 0.1:  # 加速上升
                score += 0.15
                reasons.append("MACD柱状图加速上升")
            else:
                score += 0.1
            direction = "bullish"
        elif state.macd_histogram < 0:
            if state.macd_histogram < state.macd_histogram * 0.1:  # 加速下降
                score -= 0.15
                reasons.append("MACD柱状图加速下降")
            else:
                score -= 0.1
            direction = "bearish"

        return {"score": score, "reasons": reasons, "direction": direction}

    def _analyze_volatility(self, state: MarketState) -> dict:
        """波动率分析"""
        volatility = state.atr / state.price if state.price > 0 else 0.02

        if volatility > 0.05:
            level = "high"
        elif volatility < 0.02:
            level = "low"
        else:
            level = "normal"

        return {"level": level, "value": volatility}

    def _analyze_volume(self, state: MarketState) -> dict:
        """成交量分析"""
        score = 0.0
        reasons = []

        if state.volume_ratio > 1.5:
            score += 0.2
            reasons.append(f"放量: 成交量比率 {state.volume_ratio:.2f}")
        elif state.volume_ratio > 1.2:
            score += 0.1
        elif state.volume_ratio < 0.7:
            score -= 0.1
            reasons.append(f"缩量: 成交量比率 {state.volume_ratio:.2f}")

        return {"score": score, "reasons": reasons}

    def _rsi_level(self, rsi: float) -> str:
        """RSI 区间"""
        if rsi > 70:
            return "overbought"
        elif rsi > 60:
            return "bullish"
        elif rsi < 30:
            return "oversold"
        elif rsi < 40:
            return "bearish"
        return "neutral"

    def _calculate_confidence(self, state: MarketState) -> float:
        """计算置信度"""
        factors = []

        # 信号一致性
        consistency = 1.0

        # EMA 方向
        if (state.ema_fast - state.ema_slow) / state.ema_slow > 0.02:
            consistency += 0.1
        elif (state.ema_slow - state.ema_fast) / state.ema_slow > 0.02:
            consistency -= 0.1

        # RSI 强度
        if abs(state.rsi - 50) > 20:
            factors.append(0.1)

        # MACD 强度
        if abs(state.macd_histogram) > state.price * 0.001:
            factors.append(0.1)

        return min(sum(factors) * 0.5 + 0.5, 0.95)
