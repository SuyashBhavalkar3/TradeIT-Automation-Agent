from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import List, Optional
from config.settings import Settings
from src.core.events import Event
from src.core.logging import get_logger
from src.regime.classifier import MarketRegime, RegimeClassification

logger = get_logger("permission_engine")


class TradePermissionState(str, Enum):
    PERMITTED = "PERMITTED"                      # Strategy is allowed to evaluate new setups
    BLOCKED = "BLOCKED"                          # New trade entries strictly prohibited
    RESTRICTED_MANAGE_ONLY = "MANAGE_ONLY"       # No new entries; existing open positions still managed


@dataclass(frozen=True)
class TradePermissionDecision(Event):
    symbol: str = ""
    is_permitted: bool = False
    state: TradePermissionState = TradePermissionState.BLOCKED
    regime: MarketRegime = MarketRegime.UNKNOWN
    reasons: List[str] = field(default_factory=list)
    allowed_directions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class TradePermissionEngine:
    """Evaluates whether trading is permitted for intraday options buying under current conditions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # Parse operating timings
        self.entry_start_time = time(9, 20, 0)   # Wait 5 mins after 09:15 open to settle opening whips
        self.entry_end_time = time(15, 0, 0)     # No new entries after 15:00

    def evaluate(
        self,
        classification: RegimeClassification,
        current_time: Optional[datetime] = None
    ) -> TradePermissionDecision:
        now = current_time or datetime.now()
        current_t = now.time()

        reasons = []
        allowed_directions = []

        # Rule 1: Operating Hours Restriction
        if current_t < self.entry_start_time:
            reasons.append(f"Market opening cool-off: No entries allowed before {self.entry_start_time.strftime('%H:%M')} IST")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.RESTRICTED_MANAGE_ONLY,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        if current_t > self.entry_end_time:
            reasons.append(f"Cutoff passed: No new entries permitted after {self.entry_end_time.strftime('%H:%M')} IST")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.RESTRICTED_MANAGE_ONLY,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        # Rule 2: Data Hazard Hard Block
        if classification.regime == MarketRegime.ABNORMAL_DATA:
            reasons.append("Data feed compromised: Stale ticks, abnormal spread, or connection lost")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.BLOCKED,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        # Rule 3: High Volatility Hazard Block
        if classification.regime == MarketRegime.HIGH_VOLATILITY:
            reasons.append(f"High volatility hazard: {classification.primary_reason}")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.RESTRICTED_MANAGE_ONLY,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        # Rule 4: Choppy Market Block (Theta Protection)
        if classification.regime == MarketRegime.CHOPPY:
            reasons.append("Choppy market: Options buying prohibited to prevent rapid theta erosion and false breakouts")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.RESTRICTED_MANAGE_ONLY,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        # Rule 5: Sideways / Ranging Block
        if classification.regime == MarketRegime.RANGING:
            reasons.append("Ranging market: Insufficient directional momentum for trend options buying")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=False,
                state=TradePermissionState.RESTRICTED_MANAGE_ONLY,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=[]
            )

        # Rule 6: Trending Bullish -> Permit CE Buying
        if classification.regime == MarketRegime.TRENDING_BULLISH:
            reasons.append(f"Bullish trend confirmed (Confidence: {int(classification.confidence * 100)}%): Strategy permitted to search for CALL setups")
            allowed_directions.append("CE")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=True,
                state=TradePermissionState.PERMITTED,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=allowed_directions
            )

        # Rule 7: Trending Bearish -> Permit PE Buying
        if classification.regime == MarketRegime.TRENDING_BEARISH:
            reasons.append(f"Bearish trend confirmed (Confidence: {int(classification.confidence * 100)}%): Strategy permitted to search for PUT setups")
            allowed_directions.append("PE")
            return TradePermissionDecision(
                symbol=classification.symbol,
                is_permitted=True,
                state=TradePermissionState.PERMITTED,
                regime=classification.regime,
                reasons=reasons,
                allowed_directions=allowed_directions
            )

        # Rule 8: Fail-safe Default Block
        reasons.append("Unclassified regime: Defaulting to fail-safe block")
        return TradePermissionDecision(
            symbol=classification.symbol,
            is_permitted=False,
            state=TradePermissionState.BLOCKED,
            regime=classification.regime,
            reasons=reasons,
            allowed_directions=[]
        )
