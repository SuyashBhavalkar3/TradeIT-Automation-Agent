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
    base_time = datetime.now() - timedelta(minutes=30)
    price = 22700.0

    # Seed trending candles to demonstrate regime detector in action
    for i in range(25):
        price += 7.5  # Consistent upward trend
        c = CandleEvent(
            symbol="NIFTY",
            timeframe="1m",
            open=round(price - 2.0, 2),
            high=round(price + 6.0, 2),
            low=round(price - 2.5, 2),
            close=round(price, 2),
            volume=5000 + (i * 150),
            candle_start=base_time + timedelta(minutes=i),
            is_closed=True
        )
        import asyncio
        asyncio.run(event_bus.publish(c))

    res = client.get("/api/regime/NIFTY")
    print("\n--- Market Regime & Trade Permission Output (/api/regime/NIFTY) ---")
    print(json.dumps(res.json(), indent=2))

