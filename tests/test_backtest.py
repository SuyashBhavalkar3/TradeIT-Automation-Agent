from datetime import datetime, timedelta
import pandas as pd
import pytest
from src.backtest.backtest_engine import HistoricalBacktestEngine


def test_historical_backtest_execution():
    engine = HistoricalBacktestEngine(initial_capital=100000.0, lot_size=25)

    # Generate 100 realistic bars with trending and pullback phases
    base_time = datetime(2026, 10, 28, 9, 30)
    data = []
    price = 22700.0

    for i in range(120):
        # Create an initial trend, then pullback, then target move
        if i < 40:
            price += 2.0  # Steady uptrend
        elif i < 50:
            price -= 1.0  # Pullback to EMA
        else:
            price += 3.0  # Trend continuation to target

        data.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": round(price - 2.0, 2),
            "high": round(price + 5.0, 2),
            "low": round(price - 3.0, 2),
            "close": round(price, 2),
            "volume": 5000 + (i * 50)
        })

    df = pd.DataFrame(data)
    metrics = engine.run(df, symbol="NIFTY")

    # Verify backtest executed without errors
    assert metrics is not None
    assert isinstance(metrics.win_rate_pct, float)
    assert isinstance(metrics.total_transaction_costs, float)
    assert isinstance(metrics.max_drawdown_amount, float)
