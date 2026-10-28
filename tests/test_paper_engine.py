from datetime import datetime
import pytest
from config.settings import Settings
from src.core.events import EventBus, TickEvent
from src.execution.cost_model import IndianFOCostModel
from src.execution.order_model import OrderSide, OrderStatus
from src.execution.paper_engine import PaperExecutionEngine
from src.risk.risk_manager import RiskApproval, RiskManager
from src.strategy.base_strategy import SignalDirection, TradeProposal


@pytest.fixture
def paper_setup():
    settings = Settings()
    bus = EventBus()
    risk_manager = RiskManager(settings)
    paper_engine = PaperExecutionEngine(bus, risk_manager, initial_capital=100000.0)
    return bus, risk_manager, paper_engine


def test_indian_fo_cost_model():
    # Buy at 100, Sell at 120, Qty 50 (2 lots)
    costs = IndianFOCostModel.calculate_option_trade_costs(buy_price=100.0, sell_price=120.0, quantity=50)

    assert costs.brokerage == 40.0  # 20 buy + 20 sell
    assert costs.stt > 0
    assert costs.exchange_charges > 0
    assert costs.gst > 0
    assert costs.total_costs > 40.0


@pytest.mark.asyncio
async def test_paper_execution_order_flow(paper_setup):
    bus, risk_manager, engine = paper_setup

    proposal = TradeProposal(
        strategy_name="DYNAMIC_OPTIONS_MOMENTUM",
        symbol="NIFTY_22700_CE",
        underlying_symbol="NIFTY",
        direction=SignalDirection.BUY_CALL,
        option_type="CE",
        expected_entry_price=100.0,
        stop_loss_price=85.0,
        target_price=130.0,
        risk_points=15.0
    )

    approval = RiskApproval(
        is_approved=True,
        proposal=proposal,
        approved_quantity=50,
        lots=2,
        total_risk_amount=750.0,
        total_capital_required=5000.0
    )

    # 1. Execute virtual buy order
    order = await engine.execute_approved_proposal(approval)

    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert order.filled_price >= 100.0  # Includes realistic slippage
    assert len(engine.open_positions) == 1
    assert "NIFTY_22700_CE" in engine.open_positions

    # 2. Simulate tick reaching Target (135 >= 130)
    target_tick = TickEvent(symbol="NIFTY_22700_CE", ltp=135.0, bid_price=134.9, ask_price=135.1)
    await engine.on_tick(target_tick)

    # Position should be closed
    assert len(engine.open_positions) == 0
    assert len(engine.closed_trades) == 1

    closed = engine.closed_trades[0]
    assert closed.exit_reason == "TARGET_ACHIEVED"
    assert closed.gross_pnl > 0
    assert closed.net_pnl > 0
    assert closed.statutory_costs > 0


@pytest.mark.asyncio
async def test_paper_stop_loss_trigger(paper_setup):
    bus, risk_manager, engine = paper_setup

    proposal = TradeProposal(
        symbol="NIFTY_22700_PE",
        expected_entry_price=100.0,
        stop_loss_price=85.0,
        target_price=130.0
    )

    approval = RiskApproval(
        is_approved=True,
        proposal=proposal,
        approved_quantity=25,
        lots=1,
        total_risk_amount=375.0,
        total_capital_required=2500.0
    )

    await engine.execute_approved_proposal(approval)
    assert len(engine.open_positions) == 1

    # Simulate price crashing below stop-loss (80 <= 85)
    sl_tick = TickEvent(symbol="NIFTY_22700_PE", ltp=80.0, bid_price=79.9, ask_price=80.1)
    await engine.on_tick(sl_tick)

    assert len(engine.open_positions) == 0
    assert len(engine.closed_trades) == 1
    assert engine.closed_trades[0].exit_reason == "STOP_LOSS_TRIGGERED"
    assert engine.closed_trades[0].net_pnl < 0
