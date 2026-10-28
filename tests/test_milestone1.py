from datetime import datetime, timedelta
import pytest
from config.instruments import get_instrument_config, SUPPORTED_INSTRUMENTS
from config.settings import Settings, TradingMode
from src.core.events import CandleEvent, EventBus, FeedState, TickEvent
from src.market_data.candle_builder import CandleBuilder
from src.market_data.data_monitor import DataQualityMonitor


def test_settings_safety_defaults():
    s = Settings()
    assert s.TRADING_MODE == TradingMode.PAPER
    assert s.MAX_DAILY_LOSS > 0
    assert s.MAX_PER_TRADE_RISK > 0
    assert s.MAX_OPEN_POSITIONS > 0


def test_instrument_config():
    nifty = get_instrument_config("NIFTY")
    assert nifty.lot_size == 25
    assert nifty.strike_interval == 50
    assert nifty.tick_size == 0.05

    banknifty = get_instrument_config("BANKNIFTY")
    assert banknifty.lot_size == 15
    assert banknifty.strike_interval == 100


@pytest.mark.asyncio
async def test_event_bus():
    bus = EventBus()
    received = []

    async def sample_handler(event: TickEvent):
        received.append(event)

    bus.subscribe(TickEvent, sample_handler)
    tick = TickEvent(symbol="NIFTY", ltp=24500.0)
    await bus.publish(tick)

    assert len(received) == 1
    assert received[0].ltp == 24500.0


@pytest.mark.asyncio
async def test_candle_builder():
    bus = EventBus()
    closed_candles = []

    async def on_candle(candle: CandleEvent):
        if candle.is_closed:
            closed_candles.append(candle)

    bus.subscribe(CandleEvent, on_candle)
    builder = CandleBuilder(bus, timeframes=["1m"])

    # Tick 1: Minute 0, second 10
    t0 = datetime(2026, 10, 28, 9, 15, 10)
    await builder.on_tick(TickEvent(symbol="NIFTY", ltp=24500.0, volume=100, timestamp=t0))

    # Tick 2: Minute 0, second 30 (new high and close)
    t1 = datetime(2026, 10, 28, 9, 15, 30)
    await builder.on_tick(TickEvent(symbol="NIFTY", ltp=24520.0, volume=250, timestamp=t1))

    # Tick 3: Minute 0, second 50 (new low and close)
    t2 = datetime(2026, 10, 28, 9, 15, 50)
    await builder.on_tick(TickEvent(symbol="NIFTY", ltp=24490.0, volume=400, timestamp=t2))

    # Verify in-progress candle
    current = builder.get_current_candle("NIFTY", "1m")
    assert current is not None
    assert current.open == 24500.0
    assert current.high == 24520.0
    assert current.low == 24490.0
    assert current.close == 24490.0

    # Tick 4: Minute 1, second 5 -> should trigger close of Minute 0 candle
    t3 = datetime(2026, 10, 28, 9, 16, 5)
    await builder.on_tick(TickEvent(symbol="NIFTY", ltp=24510.0, volume=500, timestamp=t3))

    assert len(closed_candles) == 1
    closed = closed_candles[0]
    assert closed.is_closed is True
    assert closed.open == 24500.0
    assert closed.high == 24520.0
    assert closed.low == 24490.0
    assert closed.close == 24490.0
    assert closed.volume == 300  # 150 + 150 delta accumulated since baseline tick


@pytest.mark.asyncio
async def test_data_quality_monitor_filters():
    bus = EventBus()
    monitor = DataQualityMonitor(bus, max_stale_seconds=2.0, max_tick_jump_pct=0.10)
    monitor.update_feed_state(FeedState.CONNECTED)

    # 1. Valid tick
    valid_tick = TickEvent(symbol="NIFTY", ltp=24500.0, bid_price=24499.5, ask_price=24500.5)
    assert await monitor.on_tick(valid_tick) is True

    # 2. Invalid price (negative or 0)
    bad_price_tick = TickEvent(symbol="NIFTY", ltp=0.0)
    assert await monitor.on_tick(bad_price_tick) is False

    # 3. Crossed spread (bid > ask)
    crossed_tick = TickEvent(symbol="NIFTY", ltp=24500.0, bid_price=24510.0, ask_price=24500.0)
    assert await monitor.on_tick(crossed_tick) is False

    # 4. Spike jump (> 10% instant move)
    spike_tick = TickEvent(symbol="NIFTY", ltp=28000.0)
    assert await monitor.on_tick(spike_tick) is False

    # Price should remain at 24500.0
    assert monitor.get_last_price("NIFTY") == 24500.0
