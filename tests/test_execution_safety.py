from datetime import datetime, timedelta
import pytest
from config.settings import Settings, TradingMode
from src.core.events import EventBus
from src.execution.dhan_gateway import DhanOrderGateway
from src.execution.execution_router import ExecutionRouter
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.safe_mode_manager import SafeModeManager, SetupState
from src.risk.risk_manager import RiskApproval, RiskManager
from src.strategy.base_strategy import SignalDirection, TradeProposal


@pytest.fixture
def safety_setup():
    settings = Settings(TRADING_MODE=TradingMode.PAPER, SAFE_MODE=True, MAX_ENTRY_SLIPPAGE_PCT=0.01)
    bus = EventBus()
    risk_manager = RiskManager(settings)
    paper_engine = PaperExecutionEngine(bus, risk_manager)
    dhan_gateway = DhanOrderGateway(settings)
    router = ExecutionRouter(settings, paper_engine, dhan_gateway)
    safe_mode_mgr = SafeModeManager(settings)
    return settings, safe_mode_mgr, router, dhan_gateway, paper_engine


def test_safe_mode_pre_approval_arming(safety_setup):
    _, safe_mode_mgr, _, _, _ = safety_setup

    proposal = TradeProposal(
        strategy_name="DYNAMIC_OPTIONS_MOMENTUM",
        symbol="NIFTY_22700_CE",
        direction=SignalDirection.BUY_CALL,
        expected_entry_price=135.0,
        stop_loss_price=120.0,
        target_price=165.0
    )

    # 1. Register setup in Safe Mode -> should be in PROPOSED state
    setup = safe_mode_mgr.register_proposal(proposal, timeout_minutes=5)
    assert setup.state == SetupState.PROPOSED
    assert setup.trigger_price == 135.0
    assert setup.price_ceiling == 136.35  # 135 * 1.01

    # 2. Arm setup (User pre-approval consent)
    success, msg = safe_mode_mgr.arm_setup(setup.setup_id)
    assert success is True
    assert setup.state == SetupState.ARMED
    assert "successfully armed" in msg


def test_anti_chasing_ceiling_blocks_spikes(safety_setup):
    _, safe_mode_mgr, _, _, _ = safety_setup

    proposal = TradeProposal(
        symbol="NIFTY_22700_CE",
        expected_entry_price=135.0,
        stop_loss_price=120.0,
        target_price=165.0
    )

    setup = safe_mode_mgr.register_proposal(proposal)
    safe_mode_mgr.arm_setup(setup.setup_id)

    # Scenario: User approved, but price jumped to 142.0 (> 136.35 ceiling)
    valid, reason = safe_mode_mgr.validate_anti_chasing(setup.setup_id, current_market_price=142.0)

    assert valid is False
    assert setup.state == SetupState.REJECTED_CHASING
    assert "ANTI-CHASING PROTECTION TRIGGERED" in reason


def test_anti_chasing_permits_within_tolerance(safety_setup):
    _, safe_mode_mgr, _, _, _ = safety_setup

    proposal = TradeProposal(
        symbol="NIFTY_22700_CE",
        expected_entry_price=135.0
    )

    setup = safe_mode_mgr.register_proposal(proposal)
    safe_mode_mgr.arm_setup(setup.setup_id)

    # Price at 135.50 (within 136.35 ceiling)
    valid, _ = safe_mode_mgr.validate_anti_chasing(setup.setup_id, current_market_price=135.50)
    assert valid is True


def test_dhan_gateway_strictly_refuses_orders_in_paper_mode(safety_setup):
    settings, _, _, dhan_gateway, _ = safety_setup

    assert settings.TRADING_MODE == TradingMode.PAPER

    proposal = TradeProposal(symbol="NIFTY_22700_CE", expected_entry_price=135.0)
    approval = RiskApproval(
        is_approved=True,
        proposal=proposal,
        approved_quantity=25,
        lots=1,
        total_risk_amount=375.0,
        total_capital_required=3375.0
    )

    # Calling Dhan live gateway when mode is PAPER must raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        dhan_gateway.execute_live_order(approval, security_id="35008")

    assert "SAFETY REFUSAL" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_routes_to_paper_when_in_paper_mode(safety_setup):
    _, _, router, _, paper_engine = safety_setup

    assert router.is_live is False

    proposal = TradeProposal(symbol="NIFTY_22700_CE", expected_entry_price=100.0)
    approval = RiskApproval(
        is_approved=True,
        proposal=proposal,
        approved_quantity=25,
        lots=1,
        total_risk_amount=250.0,
        total_capital_required=2500.0
    )

    order = await router.execute_approved_proposal(approval)
    assert order is not None
    assert "NIFTY_22700_CE" in paper_engine.open_positions
