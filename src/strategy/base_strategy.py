from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from src.analytics.market_state import MarketState
from src.core.events import Event
from src.regime.permission_engine import TradePermissionDecision


class SignalDirection(str, Enum):
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class TradeProposal(Event):
    """Structured proposal generated dynamically by a strategy."""

    strategy_name: str = ""
    symbol: str = ""
    underlying_symbol: str = ""
    direction: SignalDirection = SignalDirection.NO_SIGNAL
    option_type: str = ""                # "CE" or "PE"
    strike: float = 0.0
    expiry_date: str = ""

    # Dynamic Pricing & Levels (computed from ATR and structure, zero static points)
    underlying_spot: float = 0.0
    expected_entry_price: float = 0.0
    stop_loss_price: float = 0.0
    target_price: float = 0.0
    risk_points: float = 0.0
    reward_points: float = 0.0
    risk_reward_ratio: float = 0.0

    # Rationale and Invalidation
    market_regime: str = ""
    reasons: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate(
        self,
        state: MarketState,
        permission: TradePermissionDecision,
        current_option_price: float,
        india_vix: float = 16.0
    ) -> Optional[TradeProposal]:
        """Evaluates market state and returns a structured trade proposal if conditions align."""
        pass
