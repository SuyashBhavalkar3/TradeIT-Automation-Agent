import asyncio
from datetime import datetime
import random
from typing import Dict, List, Optional
from src.core.events import EventBus, FeedState, TickEvent
from src.core.logging import get_logger

logger = get_logger("market_simulator")


class MarketDataSimulator:
    """Simulates realistic live market tick feeds for paper trading and offline testing."""

    def __init__(
        self,
        event_bus: EventBus,
        symbols_with_base_price: Optional[Dict[str, float]] = None,
        tick_interval_seconds: float = 0.5
    ):
        self.event_bus = event_bus
        self.prices = symbols_with_base_price or {
            "NIFTY": 22702.40,
            "BANKNIFTY": 54256.35,
            "NIFTY22700CE": 135.50,
            "NIFTY22700PE": 128.00
        }
        self.tick_interval_seconds = tick_interval_seconds
        self._running = False
        self._volumes: Dict[str, int] = {k: 50000 for k in self.prices}

    async def start(self):
        self._running = True
        logger.info("Market data simulator started", symbols=list(self.prices.keys()))
        while self._running:
            for symbol, current_price in list(self.prices.items()):
                # Generate realistic micro-fluctuation (drift + volatility)
                pct_change = random.gauss(0, 0.0008)  # ~0.08% std dev
                new_price = round(max(0.05, current_price * (1 + pct_change)), 2)
                # Ensure 0.05 tick size
                new_price = round(round(new_price / 0.05) * 0.05, 2)
                self.prices[symbol] = new_price

                # Spread
                spread = 0.05 if "CE" in symbol or "PE" in symbol else 0.50
                bid = round(new_price - (spread / 2), 2)
                ask = round(new_price + (spread / 2), 2)

                vol_delta = random.randint(25, 250)
                self._volumes[symbol] += vol_delta

                tick = TickEvent(
                    security_id=symbol,
                    symbol=symbol,
                    ltp=new_price,
                    volume=self._volumes[symbol],
                    bid_price=bid,
                    ask_price=ask,
                    open_interest=random.randint(100000, 200000),
                    timestamp=datetime.now()
                )
                await self.event_bus.publish(tick)

            await asyncio.sleep(self.tick_interval_seconds)

    def stop(self):
        self._running = False
        logger.info("Market data simulator stopped")

