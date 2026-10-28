from datetime import datetime, time
import pytest
from config.settings import Settings
from src.analytics.market_state import MarketState
from src.core.events import EventBus, FeedState
from src.market_data.data_monitor import DataQualityMonitor
from src.regime.classifier import MarketRegime, MarketRegimeClassifier
from src.regime.permission_engine import TradePermissionEngine, TradePermissionState


@pytest.fixture
def test_setup():
    settings = Settings()
    bus = EventBus()
    monitor = DataQualityMonitor(bus)
    monitor.update_feed_state(FeedState.CONNECTED)
    classifier = MarketRegimeClassifier(data_monitor=monitor)
    permission_engine = TradePermissionEngine(settings)
    return monitor, classifier, permission_engine


def test_bullish_trend_permitted(test_setup):
    _, classifier, permission_engine = test_setup

    state = MarketState(
        symbol="NIFTY",
        close=22700.0,
        adx=30.0,
        plus_di=28.0,
        minus_di=12.0,
        price_vs_vwap="ABOVE",
        ema_alignment="BULLISH",
        rsi=62.0,
        normalized_atr_pct=0.06,
        body_ratio=0.60
    )

    classification = classifier.classify(state)
    assert classification.regime == MarketRegime.TRENDING_BULLISH
    assert classification.confidence >= 0.70

    # Test during valid market hours (e.g. 10:30 AM)
    test_time = datetime(2026, 10, 28, 10, 30, 0)
    decision = permission_engine.evaluate(classification, current_time=test_time)

    assert decision.is_permitted is True
    assert decision.state == TradePermissionState.PERMITTED
    assert decision.allowed_directions == ["CE"]
    assert "Bullish trend confirmed" in decision.reasons[0]


def test_bearish_trend_permitted(test_setup):
    _, classifier, permission_engine = test_setup

    state = MarketState(
        symbol="NIFTY",
        close=22650.0,
        adx=32.0,
        plus_di=10.0,
        minus_di=30.0,
        price_vs_vwap="BELOW",
        ema_alignment="BEARISH",
        rsi=38.0,
        normalized_atr_pct=0.06,
        body_ratio=0.55
    )

    classification = classifier.classify(state)
    assert classification.regime == MarketRegime.TRENDING_BEARISH

    test_time = datetime(2026, 10, 28, 11, 0, 0)
    decision = permission_engine.evaluate(classification, current_time=test_time)

    assert decision.is_permitted is True
    assert decision.state == TradePermissionState.PERMITTED
    assert decision.allowed_directions == ["PE"]


def test_choppy_market_blocked(test_setup):
    _, classifier, permission_engine = test_setup

    state = MarketState(
        symbol="NIFTY",
        close=22700.0,
        adx=16.0,
        plus_di=15.0,
        minus_di=15.0,
        price_vs_vwap="AT",
        ema_alignment="MIXED",
        rsi=49.0,
        normalized_atr_pct=0.05,
        body_ratio=0.15  # Tiny body with long wicks = chop
    )

    classification = classifier.classify(state)
    assert classification.regime == MarketRegime.CHOPPY

    test_time = datetime(2026, 10, 28, 12, 0, 0)
    decision = permission_engine.evaluate(classification, current_time=test_time)

    assert decision.is_permitted is False
    assert decision.state == TradePermissionState.RESTRICTED_MANAGE_ONLY
    assert decision.allowed_directions == []
    assert "Choppy market" in decision.reasons[0]


def test_high_volatility_blocked(test_setup):
    _, classifier, permission_engine = test_setup

    state = MarketState(
        symbol="NIFTY",
        close=22700.0,
        adx=28.0,
        normalized_atr_pct=0.25,  # Exceeds 0.12% limit
        body_ratio=0.50
    )

    classification = classifier.classify(state)
    assert classification.regime == MarketRegime.HIGH_VOLATILITY

    test_time = datetime(2026, 10, 28, 13, 0, 0)
    decision = permission_engine.evaluate(classification, current_time=test_time)

    assert decision.is_permitted is False
    assert "High volatility hazard" in decision.reasons[0]


def test_outside_hours_blocked(test_setup):
    _, classifier, permission_engine = test_setup

    state = MarketState(
        symbol="NIFTY",
        close=22700.0,
        adx=30.0,
        plus_di=28.0,
        minus_di=12.0,
        price_vs_vwap="ABOVE",
        ema_alignment="BULLISH",
        rsi=62.0,
        normalized_atr_pct=0.06,
        body_ratio=0.60
    )
    classification = classifier.classify(state)

    # 1. Early morning (09:16 AM -> before 09:20 cooloff)
    early_time = datetime(2026, 10, 28, 9, 16, 0)
    decision_early = permission_engine.evaluate(classification, current_time=early_time)
    assert decision_early.is_permitted is False
    assert "opening cool-off" in decision_early.reasons[0]

    # 2. Late afternoon (15:05 PM -> after 15:00 cutoff)
    late_time = datetime(2026, 10, 28, 15, 5, 0)
    decision_late = permission_engine.evaluate(classification, current_time=late_time)
    assert decision_late.is_permitted is False
    assert "Cutoff passed" in decision_late.reasons[0]


def test_abnormal_data_feed_blocked(test_setup):
    monitor, classifier, permission_engine = test_setup
    # Simulate stale / disconnected feed
    monitor.update_feed_state(FeedState.STALE, "No ticks received")

    state = MarketState(symbol="NIFTY", close=22700.0)
    classification = classifier.classify(state)
    assert classification.regime == MarketRegime.ABNORMAL_DATA

    decision = permission_engine.evaluate(classification, current_time=datetime(2026, 10, 28, 11, 0, 0))
    assert decision.is_permitted is False
    assert decision.state == TradePermissionState.BLOCKED
    assert "Data feed compromised" in decision.reasons[0]

