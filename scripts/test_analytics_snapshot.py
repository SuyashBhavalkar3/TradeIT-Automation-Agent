import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from src.core.events import CandleEvent
from src.main import app, event_bus

client = TestClient(app)

with client:
    # Seed 25 realistic 1m candles around today's live Nifty level (22,700)
    base_time = datetime.now() - timedelta(minutes=30)
    price = 22700.0

    print("--- Seeding 25 1-minute historical candles into Feature Engine ---")
    for i in range(25):
        price += (i % 4 - 1.5) * 4.5
        c = CandleEvent(
            symbol="NIFTY",
            timeframe="1m",
            open=round(price - 3.0, 2),
            high=round(price + 8.0, 2),
            low=round(price - 6.0, 2),
            close=round(price, 2),
            volume=4500 + (i * 120),
            candle_start=base_time + timedelta(minutes=i),
            is_closed=True
        )
        import asyncio
        asyncio.run(event_bus.publish(c))

    res = client.get("/api/analytics/NIFTY")
    print("\n--- Analytics Endpoint Output (/api/analytics/NIFTY) ---")
    print(json.dumps(res.json(), indent=2))

