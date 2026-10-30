import asyncio
from datetime import datetime
from typing import Dict, Optional
from src.core.events import EventBus, FeedState, FeedStatusEvent, TickEvent
from src.core.logging import get_logger

logger = get_logger("data_monitor")


class DataQualityMonitor:
    """Monitors live data feed latency, freshness, and structural sanity."""

    def __init__(
        self,
        event_bus: EventBus,
        max_stale_seconds: float = 5.0,
        max_tick_jump_pct: float = 0.20
    ):
        self.event_bus = event_bus
        self.max_stale_seconds = max_stale_seconds
        self.max_tick_jump_pct = max_tick_jump_pct

        self._last_tick_times: Dict[str, datetime] = {}
        self._last_prices: Dict[str, float] = {}
        self._feed_state: FeedState = FeedState.DISCONNECTED
        self._is_stale: bool = False
        self._monitor_task: Optional[asyncio.Task] = None

    @property
    def feed_state(self) -> FeedState:
        return self._feed_state

    @property
    def is_healthy(self) -> bool:
        return self._feed_state == FeedState.CONNECTED and not self._is_stale

    def update_feed_state(self, state: FeedState, message: str = ""):
        if self._feed_state != state:
            self._feed_state = state
            logger.info("Feed state changed", new_state=state.value, message=message)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.event_bus.publish(
                        FeedStatusEvent(source="dhan_feed", state=state, message=message)
                    )
                )
            except RuntimeError:
                pass

    async def on_tick(self, tick: TickEvent) -> bool:
        """Validates incoming tick. Returns True if valid, False if rejected."""
        symbol = tick.symbol or tick.security_id
        now = tick.timestamp or datetime.now()

        # Sanity check 1: Non-positive price
        if tick.ltp <= 0:
            logger.warning("Rejected tick: non-positive price", symbol=symbol, ltp=tick.ltp)
            return False

        # Sanity check 2: Inverted bid-ask spread
        if tick.bid_price > 0 and tick.ask_price > 0 and tick.bid_price > tick.ask_price:
            logger.warning("Rejected tick: crossed spread", symbol=symbol, bid=tick.bid_price, ask=tick.ask_price)
            return False

        # Sanity check 3: Spike jump filter (applies only to ticks received within 30s)
        last_price = self._last_prices.get(symbol)
        last_time = self._last_tick_times.get(symbol)
        if last_price and last_price > 0 and last_time and (now - last_time).total_seconds() < 30:
            # Options naturally have higher percentage volatility than index spots
            jump_limit = 0.80 if ("_CE" in symbol or "_PE" in symbol) else self.max_tick_jump_pct
            jump = abs(tick.ltp - last_price) / last_price
            if jump > jump_limit:
                logger.warning(
                    "Rejected tick: abnormal price jump",
                    symbol=symbol,
                    previous=last_price,
                    current=tick.ltp,
                    jump_pct=round(jump * 100, 2)
                )
                return False

        # Update tracking
        self._last_prices[symbol] = tick.ltp
        self._last_tick_times[symbol] = now

        if self._is_stale:
            self._is_stale = False
            self.update_feed_state(FeedState.CONNECTED, "Data flow restored")

        return True

    async def check_freshness(self) -> bool:
        """Periodic check for stale data."""
        if self._feed_state != FeedState.CONNECTED:
            return False

        now = datetime.now()
        for symbol, last_time in self._last_tick_times.items():
            age = (now - last_time).total_seconds()
            if age > self.max_stale_seconds:
                if not self._is_stale:
                    self._is_stale = True
                    self.update_feed_state(FeedState.STALE, f"No ticks for {symbol} in {round(age, 1)}s")
                return False
        return True

    def get_last_price(self, symbol: str) -> Optional[float]:
        return self._last_prices.get(symbol)

    def get_last_tick_time(self, symbol: str) -> Optional[datetime]:
        return self._last_tick_times.get(symbol)

