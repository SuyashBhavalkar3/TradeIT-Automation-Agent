from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from config.settings import Settings
from src.core.logging import get_logger
from src.strategy.base_strategy import TradeProposal

logger = get_logger("safe_mode_manager")


class SetupState(str, Enum):
    PROPOSED = "PROPOSED"            # Waiting for human pre-approval
    ARMED = "ARMED"                  # Pre-approved; ready to trigger on price condition
    TRIGGERED = "TRIGGERED"          # Condition met, sent to execution
    DISARMED = "DISARMED"            # Manually disarmed or market invalidated
    EXPIRED = "EXPIRED"              # Timed out before price condition was reached
    REJECTED_CHASING = "REJECTED_CHASING"  # Price spiked beyond anti-chasing tolerance


@dataclass
class ArmedSetup:
    setup_id: str
    proposal: TradeProposal
    state: SetupState = SetupState.PROPOSED
    armed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    trigger_price: float = 0.0
    price_ceiling: float = 0.0       # Max allowed entry price (no chasing)
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


class SafeModeManager:
    """
    Operationally critical Safe Mode Manager.
    Enforces advance Pre-Approval (Arming) and Anti-Chasing Ceiling protection.
    Prevents entering bad trades when prices spike during human deliberation.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.safe_mode_enabled = settings.SAFE_MODE
        self.max_slippage_pct = settings.MAX_ENTRY_SLIPPAGE_PCT
        self._setups: Dict[str, ArmedSetup] = {}

    def is_safe_mode(self) -> bool:
        return self.safe_mode_enabled

    def toggle_safe_mode(self, enabled: bool):
        self.safe_mode_enabled = enabled
        if not enabled:
            # Safe Mode turned OFF -> auto-arm pending proposals for autonomous execution
            now = datetime.now()
            for s in self._setups.values():
                if s.state == SetupState.PROPOSED:
                    s.state = SetupState.ARMED
                    s.armed_at = now
        logger.info("Safe Mode toggled", enabled=enabled)

    def get_pending_or_armed_setup(self, symbol: str) -> Optional[ArmedSetup]:
        now = datetime.now()
        for s in self._setups.values():
            if s.proposal.symbol == symbol and s.state in [SetupState.PROPOSED, SetupState.ARMED]:
                if s.expires_at and now > s.expires_at:
                    s.state = SetupState.EXPIRED
                    continue
                return s
        return None

    def register_proposal(self, proposal: TradeProposal, timeout_minutes: int = 10) -> ArmedSetup:
        setup_id = f"SETUP_{proposal.symbol}_{int(datetime.now().timestamp())}"
        expected = proposal.expected_entry_price
        ceiling = round(expected * (1.0 + self.max_slippage_pct), 2)

        setup = ArmedSetup(
            setup_id=setup_id,
            proposal=proposal,
            state=SetupState.PROPOSED if self.safe_mode_enabled else SetupState.ARMED,
            trigger_price=expected,
            price_ceiling=ceiling,
            expires_at=datetime.now() + timedelta(minutes=timeout_minutes)
        )
        self._setups[setup_id] = setup

        logger.info(
            "Registered setup in Safe Mode Manager",
            setup_id=setup_id,
            symbol=proposal.symbol,
            trigger=expected,
            ceiling=ceiling,
            mode="SAFE_MODE_REQUIRES_ARM" if self.safe_mode_enabled else "AUTO_ARMED"
        )
        return setup

    def get_setup(self, setup_id: str) -> Optional[ArmedSetup]:
        return self._setups.get(setup_id)

    def arm_setup(self, setup_id: str) -> Tuple[bool, str]:
        setup = self._setups.get(setup_id)
        if not setup:
            return False, "Setup not found"

        if setup.state not in [SetupState.PROPOSED, SetupState.DISARMED]:
            return False, f"Cannot arm setup in state: {setup.state.value}"

        if setup.expires_at and datetime.now() > setup.expires_at:
            setup.state = SetupState.EXPIRED
            return False, "Setup has already expired"

        setup.state = SetupState.ARMED
        setup.armed_at = datetime.now()
        logger.info("Setup ARMED by user consent", setup_id=setup_id, symbol=setup.proposal.symbol)
        return True, "Setup successfully armed. Bot will execute automatically the instant condition is met."

    def disarm_setup(self, setup_id: str, reason: str = "User cancelled") -> Tuple[bool, str]:
        setup = self._setups.get(setup_id)
        if not setup:
            return False, "Setup not found"

        setup.state = SetupState.DISARMED
        setup.rejection_reason = reason
        logger.info("Setup DISARMED", setup_id=setup_id, reason=reason)
        return True, f"Setup disarmed: {reason}"

    def validate_anti_chasing(self, setup_id: str, current_market_price: float) -> Tuple[bool, str]:
        """
        Hard safety check: validates current market price against pre-calculated price ceiling.
        If price jumped higher than tolerance, strictly rejects entry to protect capital.
        """
        setup = self._setups.get(setup_id)
        if not setup:
            return False, "Setup not found"

        # Check expiration
        if setup.expires_at and datetime.now() > setup.expires_at:
            setup.state = SetupState.EXPIRED
            return False, "Setup expired before entry condition was met"

        # Check Price Ceiling (Anti-Chasing Protection)
        if current_market_price > setup.price_ceiling:
            deviation_pct = round(((current_market_price - setup.trigger_price) / setup.trigger_price) * 100.0, 2)
            reason = (
                f"ANTI-CHASING PROTECTION TRIGGERED: Market price (₹{current_market_price:.2f}) spiked above "
                f"maximum ceiling (₹{setup.price_ceiling:.2f}, +{deviation_pct}% deviation). "
                f"Order REJECTED to prevent chasing and capital loss."
            )
            setup.state = SetupState.REJECTED_CHASING
            setup.rejection_reason = reason
            logger.warning("Anti-chasing ceiling breached", setup_id=setup_id, current=current_market_price, ceiling=setup.price_ceiling)
            return False, reason

        return True, "Price within acceptable execution tolerance"

    def mark_triggered(self, setup_id: str):
        setup = self._setups.get(setup_id)
        if setup:
            setup.state = SetupState.TRIGGERED

    def get_active_setups(self) -> List[dict]:
        now = datetime.now()
        results = []
        for s in self._setups.values():
            if s.expires_at and now > s.expires_at and s.state in [SetupState.PROPOSED, SetupState.ARMED]:
                s.state = SetupState.EXPIRED

            results.append({
                "setup_id": s.setup_id,
                "symbol": s.proposal.symbol,
                "direction": s.proposal.direction.value,
                "state": s.state.value,
                "trigger_price": s.trigger_price,
                "price_ceiling": s.price_ceiling,
                "stop_loss": s.proposal.stop_loss_price,
                "target": s.proposal.target_price,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "rejection_reason": s.rejection_reason
            })
        return results

