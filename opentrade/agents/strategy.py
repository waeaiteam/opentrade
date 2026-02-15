"""
OpenTrade Strategy Agent - 策略分析
"""


from opentrade.agents.base import BaseAgent, MarketState


class StrategyAgent(BaseAgent):
    """策略分析 Agent
    
    负责策略绩效评估、信号生成，
    提供基于策略规则的交易信号。
    """

    @property
    def name(self) -> str:
        return "strategy_agent"

    @property
    def description(self) -> str:
        return "量化策略专家，基于历史策略模式生成信号"

    async def analyze(
        self,
        state: MarketState,
        strategy_stats: dict = None,
        signal_history: list = None,
    ) -> dict:
        """策略分析"""
        score = 0.0
        reasons = []
        confidence = 0.6

        # 趋势策略信号
        trend_signal = self._analyze_trend_strategy(state)
        score += trend_signal["score"]
        reasons.extend(trend_signal["reasons"])

        # 均线策略信号
        ma_signal = self._analyze_ma_strategy(state)
        score += ma_signal["score"]
        reasons.extend(ma_signal["reasons"])

        # 突破策略信号
        breakout_signal = self._analyze_breakout_strategy(state)
        score += breakout_signal["score"]
        reasons.extend(breakout_signal["reasons"])

        # 策略历史表现
        if strategy_stats:
            perf_signal = self._analyze_performance(strategy_stats)
            score += perf_signal["score"]
            reasons.extend(perf_signal["reasons"])
            confidence = perf_signal["confidence"]

        # 标准化
        score = max(-1, min(1, score / 3))

        return {
            "signal_score": score,
            "confidence": confidence,
            "reasons": reasons,
            "strategies": {
                "trend": trend_signal["direction"],
                "ma": ma_signal["direction"],
                "breakout": breakout_signal["direction"],
            },
        }

    def _analyze_trend_strategy(self, state: MarketState) -> dict:
        """趋势策略分析"""
        score = 0.0
        reasons = []
        direction = "neutral"

        # 价格 vs EMA
        if state.price > state.ema_slow and state.price > state.ema_fast:
            score += 0.2
            direction = "bullish"
        elif state.price < state.ema_slow and state.price < state.ema_fast:
            score -= 0.2
            direction = "bearish"

        # EMA 斜率 (简化为差值)
        ema_slope = (state.ema_fast - state.ema_slow) / state.ema_slow
        if ema_slope > 0.01:
            score += 0.1
            direction = "bullish"
        elif ema_slope < -0.01:
            score -= 0.1
            direction = "bearish"

        return {"score": score, "reasons": reasons, "direction": direction}

    def _analyze_ma_strategy(self, state: MarketState) -> dict:
        """均线策略分析"""
        score = 0.0
        reasons = []
        direction = "neutral"

        # 价格突破均线
        ohlcv = state.ohlcv_1h
        if ohlcv:
            close = ohlcv.get("close", state.price)
            sma_20 = (ohlcv.get("close", 0) * 19 + state.price) / 20  # 简化的 SMA

            if state.price > sma_20:
                score += 0.15
                reasons.append("价格站上SMA20")
            else:
                score -= 0.15
                reasons.append("价格跌破SMA20")

        return {"score": score, "reasons": reasons, "direction": direction}

    def _analyze_breakout_strategy(self, state: MarketState) -> dict:
        """突破策略分析"""
        score = 0.0
        reasons = []
        direction = "neutral"

        # Bollinger Band 突破
        if state.price > state.bollinger_upper:
            score += 0.2
            direction = "bullish_strong"
            reasons.append("突破上轨")
        elif state.price > state.bollinger_middle:
            score += 0.1
            direction = "bullish"
        elif state.price < state.bollinger_lower:
            score -= 0.2
            direction = "bearish_strong"
            reasons.append("跌破下轨")
        elif state.price < state.bollinger_middle:
            score -= 0.1
            direction = "bearish"

        return {"score": score, "reasons": reasons, "direction": direction}

    def _analyze_performance(self, stats: dict) -> dict:
        """策略表现分析"""
        score = 0.0
        reasons = []
        confidence = 0.6

        win_rate = stats.get("win_rate", 0.5)
        if win_rate > 0.6:
            score += 0.15
            reasons.append(f"高胜率: {win_rate:.1%}")
            confidence += 0.1
        elif win_rate < 0.4:
            score -= 0.15
            reasons.append(f"低胜率: {win_rate:.1%}")

        profit_factor = stats.get("profit_factor", 1.0)
        if profit_factor > 1.5:
            score += 0.1
            reasons.append(f"高盈亏比: {profit_factor:.2f}")

        sharpe = stats.get("sharpe_ratio", 0)
        if sharpe > 1.5:
            score += 0.1
            reasons.append(f"高夏普: {sharpe:.2f}")

        return {
            "score": score,
            "reasons": reasons,
            "confidence": min(confidence, 0.95),
        }
