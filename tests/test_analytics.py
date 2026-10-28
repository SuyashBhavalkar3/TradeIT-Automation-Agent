from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytest
from src.analytics.feature_engine import FeatureEngine
from src.analytics.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_candle_metrics,
    calculate_ema,
    calculate_rsi,
    calculate_vwap
)
from src.analytics.market_state import MarketState
from src.core.events import CandleEvent, EventBus


def test_ema_calculation():
    prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    ema = calculate_ema(prices, period=3)
    assert len(ema) == len(prices)
    assert ema.iloc[-1] > ema.iloc[0]


def test_atr_calculation():
    # 5 bars with constant range 10
    high = pd.Series([110.0, 115.0, 120.0, 125.0, 130.0])
    low = pd.Series([100.0, 105.0, 110.0, 115.0, 120.0])
    close = pd.Series([108.0, 112.0, 118.0, 122.0, 128.0])

    atr, norm_atr = calculate_atr(high, low, close, period=3)
    assert len(atr) == 5
    assert (atr > 0).all()
    assert (norm_atr > 0).all()
    # Normalized ATR % is (ATR / close) * 100
    assert norm_atr.iloc[-1] == pytest.approx((atr.iloc[-1] / close.iloc[-1]) * 100.0)


def test_rsi_calculation():
    # Monotonically increasing prices -> RSI should be high (> 80)
    uptrend = pd.Series([float(i) for i in range(100, 130)])
    rsi_up = calculate_rsi(uptrend, period=14)
    assert rsi_up.iloc[-1] > 80.0

    # Monotonically decreasing prices -> RSI should be low (< 20)
    downtrend = pd.Series([float(i) for i in range(130, 100, -1)])
    rsi_down = calculate_rsi(downtrend, period=14)
    assert rsi_down.iloc[-1] < 20.0


def test_vwap_and_bands():
    high = pd.Series([105.0, 110.0, 115.0])
    low = pd.Series([95.0, 100.0, 105.0])
    close = pd.Series([100.0, 105.0, 110.0])
    volume = pd.Series([1000, 2000, 1500])

    vwap, upper, lower = calculate_vwap(high, low, close, volume)
    assert len(vwap) == 3
    assert (upper >= vwap).all()
    assert (vwap >= lower).all()


def test_candle_metrics():
    open_p = pd.Series([100.0, 108.0])
    high = pd.Series([110.0, 110.0])
    low = pd.Series([95.0, 95.0])
    close = pd.Series([108.0, 100.0])

    metrics = calculate_candle_metrics(open_p, high, low, close)
    assert bool(metrics["is_bullish"].iloc[0]) is True
    assert bool(metrics["is_bullish"].iloc[1]) is False
    assert 0.0 <= metrics["body_ratio"].iloc[0] <= 1.0


@pytest.mark.asyncio
async def test_feature_engine_integration():
    bus = EventBus()
    engine = FeatureEngine(bus, max_history_bars=50)

    states_received = []

    async def on_state(state: MarketState):
        states_received.append(state)

    bus.subscribe(MarketState, on_state)
    bus.subscribe(CandleEvent, engine.on_candle)

    # Publish 10 sequential closed candles
    base_time = datetime(2026, 10, 28, 9, 15)
    price = 22700.0

    for i in range(15):
        price += (i % 3 - 1) * 10  # realistic movement
        candle = CandleEvent(
            symbol="NIFTY",
            timeframe="1m",
            open=price - 5,
            high=price + 10,
            low=price - 10,
            close=price,
            volume=5000 + (i * 100),
            candle_start=base_time + timedelta(minutes=i),
            is_closed=True
        )
        await bus.publish(candle)

    # After at least 5 candles, states should be published
    assert len(states_received) > 0
    latest = engine.get_latest_market_state("NIFTY", "1m")
    assert latest is not None
    assert latest.symbol == "NIFTY"
    assert latest.atr > 0
    assert 0 <= latest.rsi <= 100
    assert latest.vwap > 0
    assert latest.trend_bias in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert latest.ema_alignment in ["BULLISH", "BEARISH", "MIXED"]

