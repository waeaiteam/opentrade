"""
OpenTrade Agents Package
"""

from opentrade.agents.base import (
    BaseAgent,
    MarketState,
    SignalType,
    SignalConfidence,
    TradeDecision,
)
from opentrade.agents.coordinator import CoordinatorAgent
from opentrade.agents.market import MarketAgent
from opentrade.agents.risk import RiskAgent, RiskController
from opentrade.agents.strategy import StrategyAgent
from opentrade.agents.onchain import OnChainAgent
from opentrade.agents.sentiment import SentimentAgent
from opentrade.agents.macro import MacroAgent

__all__ = [
    # Base
    "BaseAgent",
    "MarketState",
    "SignalType",
    "SignalConfidence",
    "TradeDecision",
    # Agents
    "CoordinatorAgent",
    "MarketAgent",
    "StrategyAgent",
    "RiskAgent",
    "OnChainAgent",
    "SentimentAgent",
    "MacroAgent",
    # Controllers
    "RiskController",
]
