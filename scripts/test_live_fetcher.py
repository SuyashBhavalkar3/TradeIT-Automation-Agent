import asyncio
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from src.core.events import EventBus, TickEvent
from src.market_data.data_monitor import DataQualityMonitor
from src.market_data.live_market_fetcher import LiveMarketFetcher

async def main():
    bus = EventBus()
    monitor = DataQualityMonitor(bus)
    
    received_ticks = []
    async def on_tick(tick: TickEvent):
        received_ticks.append(tick)
        print(f"[{tick.timestamp.strftime('%H:%M:%S')}] {tick.symbol:<12} LTP: {tick.ltp:>10.2f} (Bid: {tick.bid_price}, Ask: {tick.ask_price})")

    bus.subscribe(TickEvent, on_tick)
    fetcher = LiveMarketFetcher(bus, monitor, poll_interval_seconds=1.0)
    
    task = asyncio.create_task(fetcher.start())
    print("--- Fetching 100% Real Live NSE Exchange Prices ---")
    
    # Wait for 3 seconds of ticks
    await asyncio.sleep(4.0)
    fetcher.stop()
    await task

if __name__ == "__main__":
    asyncio.run(main())
