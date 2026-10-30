import pytest
from datetime import datetime
from config.settings import Settings, TradingMode
from src.core.events import EventBus
from src.execution.execution_router import ExecutionRouter
from src.execution.order_model import OrderStatus
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.dhan_gateway import DhanOrderGateway
from src.execution.safe_mode_manager import SafeModeManager, SetupState
from src.risk.risk_manager import RiskManager
from src.strategy.base_strategy import SignalDirection, TradeProposal


@pytest.mark.asyncio
async def test_autonomous_mode_execution_flow():
    # Setup test environment with SAFE_MODE = False (Autonomous)
    settings = Settings(TRADING_MODE=TradingMode.PAPER, SAFE_MODE=False)
    event_bus = EventBus()
    risk_manager = RiskManager(settings=settings)
    paper_engine = PaperExecutionEngine(event_bus=event_bus, risk_manager=risk_manager)
    dhan_gateway = DhanOrderGateway(settings=settings)
    router = ExecutionRouter(settings=settings, paper_engine=paper_engine, dhan_gateway=dhan_gateway)
    safe_mode = SafeModeManager(settings=settings)

    assert safe_mode.is_safe_mode() is False

    proposal = TradeProposal(
        strategy_name="TEST_STRATEGY",
        symbol="NIFTY_22950_CE",
        underlying_symbol="NIFTY",
        direction=SignalDirection.BUY_CALL,
        option_type="CE",
        expected_entry_price=100.0,
        stop_loss_price=80.0,
        target_price=132.0,
        risk_points=20.0,
        reward_points=32.0,
        risk_reward_ratio=1.6
    )

    setup = safe_mode.register_proposal(proposal)
    assert setup.state == SetupState.ARMED  # Auto-armed because safe_mode is False!

    # Sizing approval
    approval = risk_manager.validate_and_size(proposal, lot_size=25, available_cash=paper_engine.available_cash, record_order=True)
    assert approval.is_approved is True
    assert approval.lots > 0

    # Anti-chasing validation
    valid, reason = safe_mode.validate_anti_chasing(setup.setup_id, current_market_price=100.5)
    assert valid is True

    # Execute order via router
    order = await router.execute_approved_proposal(approval)
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert len(paper_engine.open_positions) == 1

    # Verify panic square-off closes all positions immediately
    closed = await paper_engine.close_all_positions(exit_reason="USER_PANIC_SQUARE_OFF")
    assert len(closed) == 1
    assert len(paper_engine.open_positions) == 0
    assert len(paper_engine.closed_trades) == 1
