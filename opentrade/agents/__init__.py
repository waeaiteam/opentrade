"""
OpenTrade Agents Package
"""

from opentrade.agents.base import (
    BaseAgent,
    MarketState,
    SignalConfidence,
    SignalType,
    TradeDecision,
)
from opentrade.agents.coordinator import AgentCoordinator
from opentrade.agents.macro import MacroAgent
from opentrade.agents.market import MarketAgent
from opentrade.agents.onchain import OnchainAgent
from opentrade.agents.risk import RiskAgent
from opentrade.agents.sentiment import SentimentAgent
from opentrade.agents.strategy import StrategyAgent

__all__ = [
    # Base
    "BaseAgent",
    "MarketState",
    "SignalType",
    "SignalConfidence",
    "TradeDecision",
    # Agents
    "AgentCoordinator",
    "MarketAgent",
    "StrategyAgent",
    "RiskAgent",
    "OnchainAgent",
    "SentimentAgent",
    "MacroAgent",
]
