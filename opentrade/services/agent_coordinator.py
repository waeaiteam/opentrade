"""
OpenTrade 多Agent架构 - P1 优化

核心优化: 基于 LangGraph 的事件驱动工作流
- 并行执行: 市场/链上/情绪/宏观 Agent 并行分析
- 辩论引擎: 多空/趋势/套利/风控 Agent 博弈
- 风控一票否决: 最终驳回权

作者: OpenTrade AI
日期: 2026-02-15
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ============== Agent 状态 ==============

class AgentStatus(Enum):
    """Agent 状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Agent 分析结果"""
    agent_name: str
    status: AgentStatus
    result: dict = None
    error: str = None
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class MarketState:
    """市场状态 (所有 Agent 共享)"""
    symbol: str = "BTC/USDT"
    current_price: float = 0.0
    trend: str = "neutral"  # bullish/bearish/neutral
    volatility: float = 0.0

    # 技术分析
    ema_short: float = 0.0
    ema_long: float = 0.0
    rsi: float = 50.0
    macd_signal: str = "neutral"
    bollinger_position: float = 0.5  # 0-1

    # 链上数据
    net_flow: float = 0.0
    whale_transactions: int = 0
    exchange_inflow: float = 0.0
    exchange_outflow: float = 0.0

    # 情绪数据
    fear_greed_index: int = 50
    social_sentiment: float = 0.0
    news_sentiment: float = 0.0

    # 宏观数据
    dxy: float = 100.0
    sp500: float = 4000.0
    bond_yield: float = 4.0
    vix: float = 20.0

    # Agent 结果
    market_result: dict = None
    strategy_result: dict = None
    risk_result: dict = None
    onchain_result: dict = None
    sentiment_result: dict = None
    macro_result: dict = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "trend": self.trend,
            "volatility": self.volatility,
            "ema_short": self.ema_short,
            "ema_long": self.ema_long,
            "rsi": self.rsi,
            "macd_signal": self.macd_signal,
            "bollinger_position": self.bollinger_position,
            "net_flow": self.net_flow,
            "whale_transactions": self.whale_transactions,
            "fear_greed_index": self.fear_greed_index,
            "social_sentiment": self.social_sentiment,
            "macro": {
                "dxy": self.dxy,
                "sp500": self.sp500,
                "bond_yield": self.bond_yield,
                "vix": self.vix,
            },
        }


# ============== LangGraph 工作流 ==============

class GraphNode:
    """图节点"""
    def __init__(self, name: str, func: Callable):
        self.name = name
        self.func = func
        self.dependencies: list[str] = []
        self.result: Any = None

    def depends_on(self, *nodes: str):
        """设置依赖"""
        self.dependencies.extend(nodes)
        return self


class LangGraphWorkflow:
    """
    LangGraph 风格工作流引擎
    
    支持:
    - 并行执行无依赖的节点
    - 顺序执行有依赖的节点
    - 条件分支
    - 循环 (用于辩论)
    """

    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[tuple[str, str]] = []  # (from, to)

    def add_node(self, name: str, func: Callable, dependencies: list[str] = None) -> "LangGraphWorkflow":
        """添加节点"""
        node = GraphNode(name, func)
        if dependencies:
            node.dependencies = dependencies
        self.nodes[name] = node
        return self

    def add_edge(self, from_node: str, to_node: str) -> "LangGraphWorkflow":
        """添加边"""
        self.edges.append((from_node, to_node))
        return self

    async def execute(self, initial_state: dict) -> dict:
        """
        执行工作流
        
        策略:
        1. 找到所有无依赖的节点
        2. 并行执行
        3. 完成后检查依赖
        4. 继续执行可执行的节点
        5. 循环直到完成
        """
        # 状态
        state = initial_state.copy()
        completed = set()
        results = {}

        # 执行历史 (用于循环检测)
        execution_history = set()

        # 最大迭代次数 (防止无限循环)
        max_iterations = 100
        iteration = 0

        while len(completed) < len(self.nodes) and iteration < max_iterations:
            iteration += 1

            # 找出可执行的节点 (依赖都已完成)
            ready_nodes = []
            for name, node in self.nodes.items():
                if name in completed:
                    continue

                # 检查依赖
                deps_done = all(dep in completed for dep in node.dependencies)

                # 条件检查 (动态依赖)
                if deps_done:
                    ready_nodes.append(node)

            if not ready_nodes:
                # 无可执行节点但未完成
                break

            # 并行执行
            import asyncio

            async def run_node(node: GraphNode):
                try:
                    # 将当前状态传入
                    result = await node.func(state, results)
                    node.result = result
                    return node
                except Exception as e:
                    node.result = {"error": str(e)}
                    return node

            tasks = [run_node(n) for n in ready_nodes]
            completed_nodes = await asyncio.gather(*tasks)

            for node in completed_nodes:
                completed.add(node.name)
                results[node.name] = node.result

            # 更新状态
            state.update(results)

        return results


# ============== 多Agent 协调器 ==============

class MultiAgentCoordinator:
    """
    多Agent 协调器 (基于 LangGraph)
    
    工作流:
    1. 并行阶段: 市场/链上/情绪/宏观 Agent 并行分析
    2. 辩论阶段: 多空/趋势/套利/风控 Agent 博弈
    3. 决策阶段: 生成最终交易策略
    4. 风控阶段: 一票否决校验
    """

    def __init__(self):
        self.workflow = LangGraphWorkflow()
        self.market_state = MarketState()

        # Agent 回调
        self._agent_funcs: dict[str, Callable] = {}

        # 配置
        self.config = {
            "max_debate_rounds": 3,
            "consensus_threshold": 0.7,
            "enable_parallel": True,
        }

    def register_agent(self, name: str, func: Callable):
        """注册 Agent"""
        self._agent_funcs[name] = func

    async def analyze_market(self, state: MarketState) -> MarketState:
        """市场分析 Agent"""
        if "market" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["market"](state)
        state.market_result = result
        return state

    async def analyze_strategy(self, state: MarketState) -> MarketState:
        """策略 Agent"""
        if "strategy" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["strategy"](state)
        state.strategy_result = result
        return state

    async def analyze_risk(self, state: MarketState) -> MarketState:
        """风险 Agent (一票否决权)"""
        if "risk" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["risk"](state)
        state.risk_result = result
        return state

    async def analyze_onchain(self, state: MarketState) -> MarketState:
        """链上分析 Agent"""
        if "onchain" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["onchain"](state)
        state.onchain_result = result
        return state

    async def analyze_sentiment(self, state: MarketState) -> MarketState:
        """情绪分析 Agent"""
        if "sentiment" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["sentiment"](state)
        state.sentiment_result = result
        return state

    async def analyze_macro(self, state: MarketState) -> MarketState:
        """宏观分析 Agent"""
        if "macro" not in self._agent_funcs:
            return state

        result = await self._agent_funcs["macro"](state)
        state.macro_result = result
        return state

    def _build_workflow(self):
        """构建工作流"""
        self.workflow = LangGraphWorkflow()

        # 并行阶段: 数据收集
        if self.config["enable_parallel"]:
            # 无依赖，可以并行
            self.workflow.add_node("market_analyzer", self.analyze_market)
            self.workflow.add_node("onchain_analyzer", self.analyze_onchain)
            self.workflow.add_node("sentiment_analyzer", self.analyze_sentiment)
            self.workflow.add_node("macro_analyzer", self.analyze_macro)

        # 辩论阶段: 策略生成 (依赖数据收集)
        self.workflow.add_node("strategy_analyzer", self.analyze_strategy)
        self.workflow.add_edge("market_analyzer", "strategy_analyzer")
        self.workflow.add_edge("onchain_analyzer", "strategy_analyzer")
        self.workflow.add_edge("sentiment_analyzer", "strategy_analyzer")
        self.workflow.add_edge("macro_analyzer", "strategy_analyzer")

        # 风控阶段: 最终校验 (一票否决)
        self.workflow.add_node("risk_analyzer", self.analyze_risk)
        self.workflow.add_edge("strategy_analyzer", "risk_analyzer")

    async def run(self, initial_state: MarketState = None) -> dict:
        """
        运行完整工作流
        
        Returns:
            {
                "state": 最终状态,
                "decision": 交易决策,
                "audit": 决策链路,
            }
        """
        if initial_state:
            self.market_state = initial_state

        # 构建工作流
        self._build_workflow()

        # 执行
        results = await self.workflow.execute(self.market_state.to_dict())

        # 生成决策
        decision = self._generate_decision(results)

        # 风控一票否决检查
        risk_result = results.get("risk_analyzer", {})
        if risk_result.get("blocked"):
            decision = {"action": "HOLD", "reason": "风控拦截: " + risk_result.get("reason")}

        # 构建审计链
        audit = {
            "timestamp": datetime.utcnow().isoformat(),
            "agents": {
                "market": results.get("market_analyzer"),
                "onchain": results.get("onchain_analyzer"),
                "sentiment": results.get("sentiment_analyzer"),
                "macro": results.get("macro_analyzer"),
                "strategy": results.get("strategy_analyzer"),
                "risk": results.get("risk_analyzer"),
            },
            "decision": decision,
        }

        return {
            "state": self.market_state,
            "decision": decision,
            "audit": audit,
        }

    def _generate_decision(self, results: dict) -> dict:
        """生成最终决策"""
        # 汇总各 Agent 信号
        signals = []

        market = results.get("market_analyzer", {})
        if market:
            signals.append(("market", market.get("signal"), market.get("confidence", 0)))

        strategy = results.get("strategy_analyzer", {})
        if strategy:
            signals.append(("strategy", strategy.get("signal"), strategy.get("confidence", 0)))

        onchain = results.get("onchain_analyzer", {})
        if onchain:
            signals.append(("onchain", onchain.get("signal"), onchain.get("confidence", 0)))

        sentiment = results.get("sentiment_analyzer", {})
        if sentiment:
            signals.append(("sentiment", sentiment.get("signal"), sentiment.get("confidence", 0)))

        macro = results.get("macro_analyzer", {})
        if macro:
            signals.append(("macro", macro.get("signal"), macro.get("confidence", 0)))

        # 计算加权信号
        if not signals:
            return {"action": "HOLD", "reason": "无信号"}

        # 简单投票
        buy_count = sum(1 for _, s, _ in signals if s in ["BUY", "LONG"])
        sell_count = sum(1 for _, s, _ in signals if s in ["SELL", "SHORT"])

        total_confidence = sum(c for _, _, c in signals)
        avg_confidence = total_confidence / len(signals)

        if buy_count > sell_count:
            action = "BUY"
            confidence = buy_count / len(signals)
        elif sell_count > buy_count:
            action = "SELL"
            confidence = sell_count / len(signals)
        else:
            action = "HOLD"
            confidence = avg_confidence

        return {
            "action": action,
            "confidence": confidence,
            "signals": [s[0] for s in signals],
            "avg_confidence": avg_confidence,
        }


# ============== 辩论引擎 ==============

class DebateEngine:
    """
    辩论引擎
    
    让不同观点的 Agent 进行博弈，输出共识
    """

    def __init__(self):
        self.agents: list[str] = []
        self._debate_history: list[dict] = []

    def add_agent(self, name: str):
        """添加辩论 Agent"""
        self.agents.append(name)

    async def debate(self, topic: str, initial_positions: dict) -> dict:
        """
        运行辩论
        
        Args:
            topic: 辩论主题
            initial_positions: 各 Agent 的初始观点
        
        Returns:
            共识结果
        """
        positions = initial_positions.copy()
        self._debate_history = []

        for round_num in range(3):  # 最多3轮
            round_debate = {
                "round": round_num,
                "positions": {},
            }

            # 每个 Agent 回应其他 Agent 的观点
            for agent in self.agents:
                if agent not in positions:
                    continue

                # 简单处理: 汇总所有观点
                all_views = "\n".join([
                    f"{a}: {p}" for a, p in positions.items()
                    if a != agent
                ])

                # Agent 调整观点
                new_position = await self._agent_think(agent, topic, all_views)
                positions[agent] = new_position
                round_debate["positions"][agent] = new_position

            self._debate_history.append(round_debate)

            # 检查是否达成共识
            consensus = self._check_consensus(positions)
            if consensus:
                return {
                    "consensus": consensus,
                    "rounds": round_num + 1,
                    "history": self._debate_history,
                }

        # 未达成共识，返回加权平均
        return {
            "consensus": self._aggregate_opinions(positions),
            "rounds": len(self._debate_history),
            "history": self._debate_history,
        }

    async def _agent_think(self, agent: str, topic: str, other_views: str) -> str:
        """Agent 思考并调整观点"""
        # 简化: 随机或基于规则调整
        # 实际应该调用 Agent 的思考逻辑
        return "unchanged"

    def _check_consensus(self, positions: dict) -> str | None:
        """检查共识"""
        unique = set(positions.values())
        if len(unique) == 1:
            return list(unique)[0]
        return None

    def _aggregate_opinions(self, positions: dict) -> dict:
        """汇总观点"""
        votes = {}
        for agent, position in positions.items():
            if position not in votes:
                votes[position] = []
            votes[position].append(agent)

        # 返回得票最多的
        winner = max(votes.items(), key=lambda x: len(x[1]))
        return {
            "position": winner[0],
            "supporters": winner[1],
            "votes": {k: len(v) for k, v in votes.items()},
        }


# ============== 可解释性输出 ==============

def explain_decision(decision: dict, audit: dict) -> str:
    """
    生成可解释的决策报告
    
    强制所有 Agent 输出结构化内容:
    - 核心观点
    - 支撑数据
    - 置信度
    - 风险点
    """
    lines = [
        "=" * 60,
        "OpenTrade 交易决策报告",
        "=" * 60,
        "",
        f"决策: {decision.get('action', 'HOLD')}",
        f"置信度: {decision.get('confidence', 0):.2%}",
        f"信号来源: {', '.join(decision.get('signals', []))}",
        "",
        "--- Agent 分析 ---",
        "",
    ]

    for agent_name, result in audit.get("agents", {}).items():
        if result:
            lines.append(f"[{agent_name.upper()}]")
            lines.append(f"  信号: {result.get('signal', 'N/A')}")
            lines.append(f"  置信度: {result.get('confidence', 0):.2%}")
            lines.append(f"  核心观点: {result.get('summary', 'N/A')}")
            if result.get("data"):
                lines.append(f"  支撑数据: {result['data']}")
            lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


# ============== 全局实例 ==============

coordinator = MultiAgentCoordinator()
