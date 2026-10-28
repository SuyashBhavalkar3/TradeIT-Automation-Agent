import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import MarketDataSource, TradingMode, settings
from src.core.events import EventBus, FeedState, TickEvent
from src.core.logging import get_logger, setup_logger
from src.market_data.candle_builder import CandleBuilder
from src.market_data.data_monitor import DataQualityMonitor
from src.market_data.dhan_feed import DhanMarketFeed
from src.market_data.simulator import MarketDataSimulator

# Setup structured logging
setup_logger(settings.LOG_LEVEL)
logger = get_logger("main")

# Core system state
event_bus = EventBus()
data_monitor = DataQualityMonitor(event_bus, max_stale_seconds=settings.MAX_STALE_TICK_SECONDS)
candle_builder = CandleBuilder(event_bus, timeframes=["1m", "3m", "5m"])
simulator: Optional[MarketDataSimulator] = None
dhan_feed: Optional[DhanMarketFeed] = None
background_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register core subscribers
    event_bus.subscribe(TickEvent, data_monitor.on_tick)
    event_bus.subscribe(TickEvent, candle_builder.on_tick)

    logger.info(
        "TradeIT Engine Initialized",
        mode=settings.TRADING_MODE.value,
        data_source=settings.MARKET_DATA_SOURCE.value,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_risk_per_trade=settings.MAX_PER_TRADE_RISK
    )

    global simulator, dhan_feed

    # Start Feed according to configuration
    if settings.MARKET_DATA_SOURCE == MarketDataSource.SIMULATED:
        simulator = MarketDataSimulator(event_bus)
        task = asyncio.create_task(simulator.start())
        background_tasks.append(task)
        data_monitor.update_feed_state(FeedState.CONNECTED, "Market Simulator active")
    else:
        dhan_feed = DhanMarketFeed(settings, event_bus, data_monitor)
        task = asyncio.create_task(dhan_feed.start())
        background_tasks.append(task)

    # Periodic freshness monitor task
    async def freshness_loop():
        while True:
            await asyncio.sleep(2.0)
            await data_monitor.check_freshness()

    freshness_task = asyncio.create_task(freshness_loop())
    background_tasks.append(freshness_task)

    yield

    # Graceful shutdown
    logger.info("Initiating graceful shutdown...")
    if simulator:
        simulator.stop()
    if dhan_feed:
        dhan_feed.stop()
    for task in background_tasks:
        task.cancel()
    logger.info("TradeIT Engine stopped cleanly")


app = FastAPI(
    title="TradeIT Algorithmic Engine",
    description="Intelligent AI-Powered F&O Trading Engine with Hard Risk Guardrails",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy" if data_monitor.is_healthy else "degraded",
        "timestamp": datetime.now().isoformat(),
        "trading_mode": settings.TRADING_MODE.value,
        "market_data_source": settings.MARKET_DATA_SOURCE.value,
        "feed_state": data_monitor.feed_state.value,
        "is_healthy": data_monitor.is_healthy,
        "live_trading_enabled": settings.TRADING_MODE == TradingMode.LIVE
    }


@app.get("/api/market/snapshot")
async def get_market_snapshot():
    symbols = ["NIFTY", "BANKNIFTY", "NIFTY24OCT24500CE", "NIFTY24OCT24500PE"]
    snapshot = {}
    for sym in symbols:
        snapshot[sym] = {
            "last_price": data_monitor.get_last_price(sym),
            "last_tick_time": (
                data_monitor.get_last_tick_time(sym).isoformat()
                if data_monitor.get_last_tick_time(sym)
                else None
            ),
            "candle_1m": candle_builder.get_current_candle(sym, "1m")
        }
    return snapshot
