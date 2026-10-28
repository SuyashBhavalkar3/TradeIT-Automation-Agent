from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config.settings import Settings
from src.core.logging import get_logger
from src.strategy.base_strategy import TradeProposal

logger = get_logger("risk_manager")


@dataclass(frozen=True)
class RiskApproval:
    is_approved: bool
    proposal: TradeProposal
    approved_quantity: int
    lots: int
    total_risk_amount: float
    total_capital_required: float
    rejection_reasons: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class RiskManager:
    """
    Independent Hard Risk Management Engine.
    Enforces deterministic capital limits, daily circuit breakers, and position sizing.
    No strategy or AI can override these rules.
    """

    def __init__(
        self,
        settings: Settings,
        max_daily_loss: Optional[float] = None,
        max_per_trade_risk: Optional[float] = None,
        max_open_positions: Optional[int] = None,
        max_capital_per_trade: Optional[float] = None
    ):
        self.settings = settings
        self.max_daily_loss = max_daily_loss or settings.MAX_DAILY_LOSS
        self.max_per_trade_risk = max_per_trade_risk or settings.MAX_PER_TRADE_RISK
        self.max_open_positions = max_open_positions or settings.MAX_OPEN_POSITIONS
        self.max_capital_per_trade = max_capital_per_trade or settings.MAX_CAPITAL_PER_TRADE

        # State tracking (persists during daily session)
        self._cumulative_daily_pnl: float = 0.0
        self._open_positions_count: int = 0
        self._is_emergency_halt: bool = False
        self._recent_proposals: List[dict] = []  # Deduplication cache
        self._dedup_window_seconds: float = 60.0

    @property
    def cumulative_daily_pnl(self) -> float:
        return self._cumulative_daily_pnl

    @property
    def is_emergency_halt(self) -> bool:
        return self._is_emergency_halt

    def trigger_emergency_halt(self, reason: str):
        self._is_emergency_halt = True
        logger.critical("EMERGENCY TRADING HALT TRIGGERED", reason=reason, daily_pnl=self._cumulative_daily_pnl)

    def record_closed_trade_pnl(self, pnl: float):
        """Updates cumulative daily P&L. If daily loss breached, triggers emergency shutdown."""
        self._cumulative_daily_pnl += pnl
        logger.info("Daily P&L updated", pnl_delta=pnl, cumulative_daily_pnl=self._cumulative_daily_pnl)

        if self._cumulative_daily_pnl <= -abs(self.max_daily_loss):
            self.trigger_emergency_halt(
                f"Daily loss limit breached: {self._cumulative_daily_pnl:.2f} <= -{abs(self.max_daily_loss):.2f}"
            )

    def set_open_positions_count(self, count: int):
        self._open_positions_count = max(0, count)

    def validate_and_size(
        self,
        proposal: TradeProposal,
        lot_size: int = 25,
        available_cash: float = 50000.0
    ) -> RiskApproval:
        reasons = []

        # Check 1: Emergency halt active
        if self._is_emergency_halt:
            reasons.append("Emergency trading halt is active: No new trades permitted")
            return self._reject(proposal, reasons)

        # Check 2: Daily loss circuit breaker
        if self._cumulative_daily_pnl <= -abs(self.max_daily_loss):
            self.trigger_emergency_halt("Daily loss limit exceeded")
            reasons.append(f"Daily loss limit breached ({self._cumulative_daily_pnl:.2f} <= -{self.max_daily_loss})")
            return self._reject(proposal, reasons)

        # Check 3: Max concurrent open positions
        if self._open_positions_count >= self.max_open_positions:
            reasons.append(f"Max open positions reached ({self._open_positions_count} >= {self.max_open_positions})")
            return self._reject(proposal, reasons)

        # Check 4: Duplicate order prevention (cooldown window)
        now = datetime.now()
        for prev in self._recent_proposals:
            if prev["symbol"] == proposal.symbol and prev["direction"] == proposal.direction:
                age = (now - prev["timestamp"]).total_seconds()
                if age < self._dedup_window_seconds:
                    reasons.append(f"Duplicate order rejected: identical setup triggered {age:.1f}s ago (cooldown: {self._dedup_window_seconds}s)")
                    return self._reject(proposal, reasons)

        # Check 5: Dynamic Position Sizing based on Stop Loss Distance
        risk_per_share = proposal.risk_points
        if risk_per_share <= 0:
            reasons.append("Invalid risk points on proposal (risk points <= 0)")
            return self._reject(proposal, reasons)

        # Sizing formula: lots = floor(max_risk / (risk_per_share * lot_size))
        risk_per_lot = risk_per_share * lot_size
        max_lots_by_risk = int(self.max_per_trade_risk // risk_per_lot)

        if max_lots_by_risk < 1:
            reasons.append(
                f"Risk per lot (₹{risk_per_lot:.2f}) exceeds max per-trade risk budget (₹{self.max_per_trade_risk:.2f}). Trade rejected."
            )
            return self._reject(proposal, reasons)

        # Sizing ceiling: Capital Commitment Limit
        premium_per_lot = proposal.expected_entry_price * lot_size
        max_lots_by_capital = int(min(available_cash, self.max_capital_per_trade) // premium_per_lot)

        final_lots = min(max_lots_by_risk, max_lots_by_capital)
        if final_lots < 1:
            reasons.append(
                f"Capital required per lot (₹{premium_per_lot:.2f}) exceeds available margin or capital budget (₹{self.max_capital_per_trade:.2f})"
            )
            return self._reject(proposal, reasons)

        final_quantity = final_lots * lot_size
        total_risk = round(final_quantity * risk_per_share, 2)
        total_capital = round(final_quantity * proposal.expected_entry_price, 2)

        # Record proposal to deduplication cache
        self._recent_proposals.append({
            "symbol": proposal.symbol,
            "direction": proposal.direction,
            "timestamp": now
        })
        # Clean expired cache entries
        self._recent_proposals = [
            p for p in self._recent_proposals
            if (now - p["timestamp"]).total_seconds() < self._dedup_window_seconds
        ]

        logger.info(
            "Trade proposal APPROVED by Risk Manager",
            symbol=proposal.symbol,
            lots=final_lots,
            quantity=final_quantity,
            risk=total_risk,
            capital=total_capital
        )

        return RiskApproval(
            is_approved=True,
            proposal=proposal,
            approved_quantity=final_quantity,
            lots=final_lots,
            total_risk_amount=total_risk,
            total_capital_required=total_capital,
            rejection_reasons=[]
        )

    def _reject(self, proposal: TradeProposal, reasons: List[str]) -> RiskApproval:
        logger.warning(
            "Trade proposal REJECTED by Risk Manager",
            symbol=proposal.symbol,
            reasons=reasons
        )
        return RiskApproval(
            is_approved=False,
            proposal=proposal,
            approved_quantity=0,
            lots=0,
            total_risk_amount=0.0,
            total_capital_required=0.0,
            rejection_reasons=reasons
        )
