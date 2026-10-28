# TradeIT — Intelligent F&O Trading Engine

An automated Futures & Options (F&O) algorithmic trading engine integrated with Dhan.

**Core Philosophy:**
- **Selective Trading & Capital Protection:** The bot prioritizes risk controls and capital preservation over trade frequency. It is comfortable doing nothing in choppy or unfavorable market regimes.
- **Safety First:** Live trading is hard-disabled by default (`TRADING_MODE=PAPER`). All orders must pass through an independent, deterministic risk management layer.
- **Data Integrity:** Strict detection of stale feeds, inverted spreads, abnormal tick jumps, and automatic reconnection.

---

## Architecture Overview

```
TradeIT/
├── config/
│   ├── settings.py           # Pydantic v2 settings (environment, credentials, risk limits)
│   └── instruments.py        # Nifty & Bank Nifty contract specs (lot sizes, strike steps)
├── src/
│   ├── core/
│   │   ├── events.py         # Asynchronous EventBus & strongly-typed event models
│   │   └── logging.py        # Structured JSON logging via structlog
│   ├── market_data/
│   │   ├── dhan_feed.py      # DhanHQ WebSocket market data feed with auto-reconnection
│   │   ├── candle_builder.py # Real-time OHLCV candle aggregator (1m, 3m, 5m, 15m)
│   │   ├── data_monitor.py   # Data freshness, stale feed detection, tick validation
│   │   └── simulator.py      # High-fidelity market tick simulator for offline/testing
│   └── main.py               # FastAPI application with lifecycle management
├── tests/
│   ├── test_milestone1.py    # Unit tests for core events, candle aggregation, and filters
│   └── test_api.py           # Integration tests for FastAPI endpoints
├── .env.example              # Environment variables template
├── pytest.ini                # Pytest configuration
└── requirements.txt          # Python dependencies
```

---

## Quickstart

### 1. Environment Setup

Copy `.env.example` to `.env` and fill in your Dhan credentials:

```bash
cp .env.example .env
```

```ini
TRADING_MODE=PAPER
DHAN_CLIENT_ID=your_dhan_client_id
DHAN_ACCESS_TOKEN=your_dhan_access_token
MARKET_DATA_SOURCE=SIMULATED  # Change to DHAN_LIVE when connecting to live feed
```

### 2. Run Tests

```powershell
python -m pytest tests/
```

### 3. Launch Engine

```powershell
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

- **System Health:** `http://localhost:8000/api/health`
- **Live Snapshot:** `http://localhost:8000/api/market/snapshot`
- **API Documentation:** `http://localhost:8000/docs`

---

## Roadmap

- [x] **Milestone 1:** Project foundation & Dhan market data feed with candle builder and stale data detection
- [ ] **Milestone 2:** Quantitative analysis engine (ATR, ADX, VWAP, RSI, options Greeks)
- [ ] **Milestone 3:** Market-regime classifier and Trade Permission Engine
- [ ] **Milestone 4:** Strategy & independent Risk Management Engine
- [ ] **Milestone 5:** Historical backtesting engine
- [ ] **Milestone 6:** High-fidelity live paper trading engine
- [ ] **Milestone 7:** Next.js dashboard and monitoring interface
- [ ] **Milestone 8:** Dhan broker order execution gateway & position reconciliation
- [ ] **Milestone 9:** Controlled deployment & live validation

