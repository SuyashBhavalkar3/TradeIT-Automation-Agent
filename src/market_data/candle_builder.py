from datetime import datetime, timedelta
from typing import Dict, List, Optional
from src.core.events import CandleEvent, EventBus, TickEvent
from src.core.logging import get_logger

logger = get_logger("candle_builder")

TIMEFRAME_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15
}


class Candle:
    def __init__(self, symbol: str, timeframe: str, start_time: datetime, initial_price: float, initial_volume: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_time = start_time
        self.open = initial_price
        self.high = initial_price
        self.low = initial_price
        self.close = initial_price
        self.volume = initial_volume
        self.tick_count = 1

    def update(self, price: float, volume_delta: int):
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += volume_delta
        self.tick_count += 1

    def to_event(self, is_closed: bool) -> CandleEvent:
        return CandleEvent(
            symbol=self.symbol,
            timeframe=self.timeframe,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            candle_start=self.start_time,
            is_closed=is_closed
        )


class CandleBuilder:
    """Aggregates real-time ticks into OHLCV candles across multiple timeframes."""

    def __init__(self, event_bus: EventBus, timeframes: Optional[List[str]] = None):
        self.event_bus = event_bus
        self.timeframes = timeframes or ["1m", "5m"]
        # Key: (symbol, timeframe) -> Current Candle
        self._active_candles: Dict[tuple, Candle] = {}
        # Key: symbol -> last cumulative volume to compute delta
        self._last_volumes: Dict[str, int] = {}

    def _get_candle_start(self, ts: datetime, minutes: int) -> datetime:
        # Align to candle boundary
        minute = (ts.minute // minutes) * minutes
        return ts.replace(minute=minute, second=0, microsecond=0)

    async def on_tick(self, tick: TickEvent):
        symbol = tick.symbol or tick.security_id
        if not symbol or tick.ltp <= 0:
            return

        # Calculate volume delta from cumulative exchange volume
        if symbol not in self._last_volumes:
            self._last_volumes[symbol] = tick.volume
            vol_delta = 0
        else:
            last_vol = self._last_volumes[symbol]
            vol_delta = max(0, tick.volume - last_vol) if tick.volume >= last_vol else tick.volume
            self._last_volumes[symbol] = tick.volume

        tick_time = tick.timestamp

        for tf in self.timeframes:
            minutes = TIMEFRAME_MINUTES.get(tf, 1)
            bucket_start = self._get_candle_start(tick_time, minutes)
            key = (symbol, tf)

            current_candle = self._active_candles.get(key)

            if current_candle is None:
                # First candle
                self._active_candles[key] = Candle(
                    symbol=symbol,
                    timeframe=tf,
                    start_time=bucket_start,
                    initial_price=tick.ltp,
                    initial_volume=vol_delta
                )
            elif current_candle.start_time == bucket_start:
                # In current candle
                current_candle.update(tick.ltp, vol_delta)
            else:
                # Candle rolled over: close the previous candle
                closed_event = current_candle.to_event(is_closed=True)
                await self.event_bus.publish(closed_event)
                logger.debug(
                    "Candle closed",
                    symbol=symbol,
                    tf=tf,
                    open=closed_event.open,
                    high=closed_event.high,
                    low=closed_event.low,
                    close=closed_event.close,
                    volume=closed_event.volume,
                    time=closed_event.candle_start.isoformat()
                )

                # Initialize new candle
                self._active_candles[key] = Candle(
                    symbol=symbol,
                    timeframe=tf,
                    start_time=bucket_start,
                    initial_price=tick.ltp,
                    initial_volume=vol_delta
                )

    def get_current_candle(self, symbol: str, timeframe: str) -> Optional[CandleEvent]:
        key = (symbol, timeframe)
        candle = self._active_candles.get(key)
        return candle.to_event(is_closed=False) if candle else None
