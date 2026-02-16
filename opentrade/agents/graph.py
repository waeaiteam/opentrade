"""
OpenTrade LangGraph StateGraph 定义

定义完整的交易决策工作流图。
"""

from typing import Any, TypedDict, TYPE_CHECKING

from opentrade.agents.coordinator import AgentType, MarketDirection, AgentCoordinator, AgentInput, FinalDecision

# 条件导入 langgraph (仅在需要时)
if TYPE_CHECKING:
    from langgraph.graph import StateGraph, END
else:
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        StateGraph = None
        END = None


# ============ Graph State ============

class GraphState(TypedDict):
    """图状态 - 所有节点共享"""
    # 输入
    symbol: str
    price: float
    ohlcv: dict
    risk_level: str
    max_leverage: float
    trace_id: str

    # 中间状态
    agent_outputs: dict[str, dict]
    consensus: dict
    decision: dict

    # 输出
    final_decision: dict | None


# ============ Node Functions ============

async def market_analysis_node(state: GraphState) -> GraphState:
    """Market Agent 分析节点"""
    from opentrade.agents.market import MarketAgent

    agent = MarketAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.MARKET.value: output.model_dump(),
        }
    }


async def strategy_analysis_node(state: GraphState) -> GraphState:
    """Strategy Agent 分析节点"""
    from opentrade.agents.strategy import StrategyAgent

    agent = StrategyAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.STRATEGY.value: output.model_dump(),
        }
    }


async def risk_analysis_node(state: GraphState) -> GraphState:
    """Risk Agent 分析节点"""
    from opentrade.agents.risk import RiskAgent

    agent = RiskAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.RISK.value: output.model_dump(),
        }
    }


async def onchain_analysis_node(state: GraphState) -> GraphState:
    """Onchain Agent 分析节点"""
    from opentrade.agents.onchain import OnchainAgent

    agent = OnchainAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.ONCHAIN.value: output.model_dump(),
        }
    }


async def sentiment_analysis_node(state: GraphState) -> GraphState:
    """Sentiment Agent 分析节点"""
    from opentrade.agents.sentiment import SentimentAgent

    agent = SentimentAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.SENTIMENT.value: output.model_dump(),
        }
    }


async def macro_analysis_node(state: GraphState) -> GraphState:
    """Macro Agent 分析节点"""
    from opentrade.agents.macro import MacroAgent

    agent = MacroAgent()
    input_data = _create_agent_input(state)

    output = await agent.analyze(input_data)

    return {
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            AgentType.MACRO.value: output.model_dump(),
        }
    }


def consensus_node(state: GraphState) -> GraphState:
    """辩论共识节点"""
    from opentrade.agents.coordinator import DebateEngine

    debate = DebateEngine()
    agent_outputs = [
        output for output in state.get("agent_outputs", {}).values()
    ]

    consensus = debate.calculate_consensus(agent_outputs)

    return {
        "consensus": consensus.model_dump() if hasattr(consensus, 'model_dump') else consensus,
    }


def synthesize_decision_node(state: GraphState) -> GraphState:
    """决策合成节点"""
    from opentrade.agents.coordinator import FinalDecision

    consensus = state.get("consensus", {})
    agent_outputs = state.get("agent_outputs", {})

    # 简单决策合成
    direction = consensus.get("direction", "neutral")
    confidence = consensus.get("overall_confidence", 0.5)
    score = consensus.get("weighted_score", 0.0)

    decision = {
        "action": "hold",
        "direction": direction,
        "confidence": confidence,
        "score": score,
        "symbol": state.get("symbol"),
        "price": state.get("price"),
        "reasons": consensus.get("key_reasons", []),
        "agent_votes": consensus.get("votes", []),
    }

    # 根据方向决定行动
    if direction == "bullish" and confidence > 0.6:
        decision["action"] = "buy"
    elif direction == "bearish" and confidence > 0.6:
        decision["action"] = "sell"

    return {
        "decision": decision,
        "final_decision": decision,
    }


def risk_check_node(state: GraphState) -> GraphState:
    """风控检查节点"""
    from opentrade.agents.risk import RiskLevel, RiskAssessment

    consensus = state.get("consensus", {})
    risk_level = state.get("risk_level", "medium")

    # 检查风险
    if consensus.get("direction") == "bullish":
        if risk_level == "high":
            action = "buy_reduced"
        else:
            action = "buy"
    elif consensus.get("direction") == "bearish":
        if risk_level == "high":
            action = "sell_reduced"
        else:
            action = "sell"
    else:
        action = "hold"

    return {
        "decision": {
            **state.get("decision", {}),
            "action": action,
        },
    }


# ============ Helper Functions ============

def _create_agent_input(state: GraphState) -> AgentInput:
    """创建 Agent 输入"""
    return AgentInput(
        symbol=state.get("symbol", "BTC/USDT"),
        trace_id=state.get("trace_id", ""),
        price=state.get("price", 0.0),
        ohlcv=state.get("ohlcv", {}),
        risk_level=state.get("risk_level", "medium"),
        max_leverage=state.get("max_leverage", 2.0),
    )


# ============ Graph Builder ============

def create_trading_graph() -> StateGraph:
    """
    创建交易决策图

    工作流:
    1. 并行执行 6 个 Agent
    2. 辩论共识
    3. 决策合成
    4. 风控检查
    5. 输出决策

    Returns:
        StateGraph: 编译后的图
    """
    # 创建图
    graph = StateGraph(GraphState)

    # 添加节点
    graph.add_node("market_analysis", market_analysis_node)
    graph.add_node("strategy_analysis", strategy_analysis_node)
    graph.add_node("risk_analysis", risk_analysis_node)
    graph.add_node("onchain_analysis", onchain_analysis_node)
    graph.add_node("sentiment_analysis", sentiment_analysis_node)
    graph.add_node("macro_analysis", macro_analysis_node)
    graph.add_node("consensus", consensus_node)
    graph.add_node("synthesize", synthesize_decision_node)
    graph.add_node("risk_check", risk_check_node)

    # 设置入口
    graph.set_entry_point("market_analysis")

    # 第一层并行执行
    graph.add_edge("market_analysis", "consensus")
    graph.add_edge("strategy_analysis", "consensus")
    graph.add_edge("risk_analysis", "consensus")
    graph.add_edge("onchain_analysis", "consensus")
    graph.add_edge("sentiment_analysis", "consensus")
    graph.add_edge("macro_analysis", "consensus")

    # 共识 -> 决策合成 -> 风控 -> 结束
    graph.add_edge("consensus", "synthesize")
    graph.add_edge("synthesize", "risk_check")
    graph.add_edge("risk_check", END)

    return graph


# ============ 图单例 ============

_trading_graph = None


def get_trading_graph() -> StateGraph:
    """获取交易图（单例）"""
    global _trading_graph
    if _trading_graph is None:
        _trading_graph = create_trading_graph()
    return _trading_graph


async def run_graph(
    symbol: str,
    price: float,
    ohlcv: dict,
    risk_level: str = "medium",
    max_leverage: float = 2.0,
) -> dict:
    """
    运行交易决策图

    Args:
        symbol: 交易对
        price: 当前价格
        ohlcv: K线数据
        risk_level: 风险等级
        max_leverage: 最大杠杆

    Returns:
        dict: 最终决策
    """
    import time
    import uuid
    from datetime import datetime

    start_time = time.time()

    # 创建初始状态
    initial_state = {
        "symbol": symbol,
        "price": price,
        "ohlcv": ohlcv,
        "risk_level": risk_level,
        "max_leverage": max_leverage,
        "trace_id": f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "agent_outputs": {},
        "consensus": {},
        "decision": {},
        "final_decision": None,
    }

    # 获取并运行图
    graph = get_trading_graph()
    app = graph.compile()

    # 运行图
    result = await app.ainvoke(initial_state)

    # 计算处理时间
    result["processing_time_ms"] = (time.time() - start_time) * 1000

    return result
