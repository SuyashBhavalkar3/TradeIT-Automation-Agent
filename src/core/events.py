import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Type


class EventType(str, Enum):
    TICK = "TICK"
    CANDLE = "CANDLE"
    FEED_STATUS = "FEED_STATUS"
    REGIME_CHANGE = "REGIME_CHANGE"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    ORDER_UPDATE = "ORDER_UPDATE"
    RISK_ALERT = "RISK_ALERT"


@dataclass(frozen=True)
class Event:
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class TickEvent(Event):
    security_id: str = ""
    symbol: str = ""
    ltp: float = 0.0
    volume: int = 0
    bid_price: float = 0.0
    ask_price: float = 0.0
    open_interest: int = 0


@dataclass(frozen=True)
class CandleEvent(Event):
    symbol: str = ""
    timeframe: str = "1m"  # e.g., 1m, 3m, 5m, 15m
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    candle_start: datetime = field(default_factory=datetime.now)
    is_closed: bool = False


class FeedState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    STALE = "STALE"
    RECONNECTING = "RECONNECTING"


@dataclass(frozen=True)
class FeedStatusEvent(Event):
    source: str = ""
    state: FeedState = FeedState.DISCONNECTED
    message: str = ""


HandlerType = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Lightweight, non-blocking asynchronous pub/sub event bus."""

    def __init__(self):
        self._subscribers: Dict[Type[Event], List[HandlerType]] = {}

    def subscribe(self, event_type: Type[Event], handler: HandlerType):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[Event], handler: HandlerType):
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event: Event):
        handlers = self._subscribers.get(type(event), [])
        if not handlers:
            return
        # Run handlers concurrently without blocking the publisher
        tasks = [asyncio.create_task(self._safe_call(handler, event)) for handler in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: HandlerType, event: Event):
        try:
            await handler(event)
        except Exception as exc:
            # Prevent subscriber errors from bubbling into the event loop publisher
            import structlog
            logger = structlog.get_logger("event_bus")
            logger.error("Error executing event handler", handler=handler.__name__, event=type(event).__name__, error=str(exc))
