from datetime import datetime
import pytest
from config.settings import Settings
from src.analytics.market_state import MarketState
from src.regime.classifier import MarketRegime
from src.regime.permission_engine import TradePermissionDecision, TradePermissionState
from src.risk.risk_manager import RiskManager
from src.strategy.base_strategy import SignalDirection, TradeProposal
from src.strategy.options_momentum_strategy import OptionsMomentumStrategy


@pytest.fixture
def risk_manager():
    settings = Settings()
    return RiskManager(
        settings=settings,
        max_daily_loss=5000.0,
        max_per_trade_risk=1500.0,
        max_open_positions=2,
        max_capital_per_trade=25000.0
    )


def test_strategy_bullish_pullback_proposal():
    strategy = OptionsMomentumStrategy()

    # Bullish state with pullback near EMA 21
    state = MarketState(
        symbol="NIFTY",
        close=22700.0,
        atr=20.0,
        adx=28.0,
        plus_di=25.0,
        minus_di=12.0,
        vwap=22680.0,
        price_vs_vwap="ABOVE",
        ema_9=22705.0,
        ema_21=22702.0,
        rsi=55.0
    )

    permission = TradePermissionDecision(
        symbol="NIFTY",
        is_permitted=True,
        state=TradePermissionState.PERMITTED,
        regime=MarketRegime.TRENDING_BULLISH,
        allowed_directions=["CE"]
    )

    proposal = strategy.evaluate(
        state=state,
        permission=permission,
        current_option_price=135.0,
        india_vix=16.0
    )

    assert proposal is not None
    assert proposal.direction == SignalDirection.BUY_CALL
    assert proposal.strike == 22700.0
    assert proposal.expected_entry_price == 135.0
    assert proposal.stop_loss_price < proposal.expected_entry_price
    assert proposal.target_price > proposal.expected_entry_price
    assert proposal.risk_reward_ratio >= 1.6
    assert len(proposal.reasons) > 0
    assert len(proposal.invalidation_conditions) > 0


def test_strategy_returns_none_when_blocked():
    strategy = OptionsMomentumStrategy()

    state = MarketState(symbol="NIFTY", close=22700.0, atr=20.0, adx=15.0)

    # Permission is BLOCKED
    permission = TradePermissionDecision(
        symbol="NIFTY",
        is_permitted=False,
        state=TradePermissionState.BLOCKED,
        regime=MarketRegime.CHOPPY,
        allowed_directions=[]
    )

    proposal = strategy.evaluate(state, permission, current_option_price=135.0)
    assert proposal is None


def test_risk_manager_approval_and_sizing(risk_manager):
    proposal = TradeProposal(
        strategy_name="DYNAMIC_OPTIONS_MOMENTUM",
        symbol="NIFTY_22700_CE",
        underlying_symbol="NIFTY",
        direction=SignalDirection.BUY_CALL,
        expected_entry_price=135.0,
        stop_loss_price=120.0,
        target_price=165.0,
        risk_points=15.0,
        reward_points=30.0,
        risk_reward_ratio=2.0
    )

    # Lot size 25: Risk per lot = 15 * 25 = 375 INR
    # Max risk 1500 INR -> 1500 // 375 = 4 lots = 100 qty
    approval = risk_manager.validate_and_size(proposal, lot_size=25, available_cash=50000.0)

    assert approval.is_approved is True
    assert approval.lots == 4
    assert approval.approved_quantity == 100
    assert approval.total_risk_amount == 1500.0
    assert approval.total_capital_required == 100 * 135.0
    assert len(approval.rejection_reasons) == 0


def test_risk_manager_rejects_excessive_risk(risk_manager):
    # Proposal with 100 points risk on option!
    # Risk per lot (25 * 100 = 2500 INR) > 1500 INR limit
    proposal = TradeProposal(
        symbol="NIFTY_22700_CE",
        expected_entry_price=200.0,
        risk_points=100.0
    )

    approval = risk_manager.validate_and_size(proposal, lot_size=25)
    assert approval.is_approved is False
    assert approval.approved_quantity == 0
    assert "exceeds max per-trade risk budget" in approval.rejection_reasons[0]


def test_risk_manager_daily_circuit_breaker(risk_manager):
    proposal = TradeProposal(symbol="NIFTY_22700_CE", expected_entry_price=100.0, risk_points=10.0)

    # Simulate losing trades totaling -5200 INR (breaching 5000 limit)
    risk_manager.record_closed_trade_pnl(-3000.0)
    risk_manager.record_closed_trade_pnl(-2200.0)

    assert risk_manager.is_emergency_halt is True

    # Next proposal must be hard-rejected
    approval = risk_manager.validate_and_size(proposal, lot_size=25)
    assert approval.is_approved is False
    assert "Emergency trading halt is active" in approval.rejection_reasons[0]


def test_risk_manager_max_positions_limit(risk_manager):
    proposal = TradeProposal(symbol="NIFTY_22700_CE", expected_entry_price=100.0, risk_points=10.0)

    # Set open positions to 2 (limit is 2)
    risk_manager.set_open_positions_count(2)

    approval = risk_manager.validate_and_size(proposal, lot_size=25)
    assert approval.is_approved is False
    assert "Max open positions reached" in approval.rejection_reasons[0]


def test_risk_manager_deduplication(risk_manager):
    proposal = TradeProposal(
        symbol="NIFTY_22700_CE",
        direction=SignalDirection.BUY_CALL,
        expected_entry_price=100.0,
        risk_points=10.0
    )

    # First submission -> Approved
    first = risk_manager.validate_and_size(proposal, lot_size=25)
    assert first.is_approved is True

    # Immediate duplicate submission -> Rejected by cooldown deduplication
    second = risk_manager.validate_and_size(proposal, lot_size=25)
    assert second.is_approved is False
    assert "Duplicate order rejected" in second.rejection_reasons[0]
