import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import MarketDataSource, Settings, TradingMode, settings
from src.core.events import CandleEvent, EventBus, FeedState, TickEvent
from src.core.logging import get_logger, setup_logger
from src.market_data.candle_builder import CandleBuilder
from src.market_data.data_monitor import DataQualityMonitor
from src.market_data.dhan_feed import DhanMarketFeed
from src.market_data.simulator import MarketDataSimulator
from src.market_data.live_market_fetcher import LiveMarketFetcher
from src.analytics.feature_engine import FeatureEngine

# Setup structured logging
setup_logger(settings.LOG_LEVEL)
logger = get_logger("main")

# Core system state
event_bus = EventBus()
data_monitor = DataQualityMonitor(event_bus, max_stale_seconds=settings.MAX_STALE_TICK_SECONDS)
candle_builder = CandleBuilder(event_bus, timeframes=["1m", "3m", "5m"])
feature_engine = FeatureEngine(event_bus, max_history_bars=200)
simulator: Optional[MarketDataSimulator] = None
dhan_feed: Optional[DhanMarketFeed] = None
live_fetcher: Optional[LiveMarketFetcher] = None
background_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reload settings on startup
    global settings
    settings = Settings()

    # Clear lingering tracking state
    data_monitor._last_prices.clear()
    data_monitor._last_tick_times.clear()
    candle_builder._active_candles.clear()

    # Register core subscribers
    event_bus.subscribe(TickEvent, data_monitor.on_tick)
    event_bus.subscribe(TickEvent, candle_builder.on_tick)
    event_bus.subscribe(CandleEvent, feature_engine.on_candle)

    logger.info(
        "TradeIT Engine Initialized",
        mode=settings.TRADING_MODE.value,
        data_source=settings.MARKET_DATA_SOURCE.value,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_risk_per_trade=settings.MAX_PER_TRADE_RISK
    )

    global simulator, dhan_feed, live_fetcher

    # Start Feed according to configuration
    if settings.MARKET_DATA_SOURCE == MarketDataSource.LIVE_SYNC:
        live_fetcher = LiveMarketFetcher(event_bus, data_monitor, poll_interval_seconds=1.5)
        task = asyncio.create_task(live_fetcher.start())
        background_tasks.append(task)
    elif settings.MARKET_DATA_SOURCE == MarketDataSource.SIMULATED:
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
    if live_fetcher:
        live_fetcher.stop()
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
    # Return all symbols currently tracked with real prices
    tracked = list(data_monitor._last_prices.keys())
    if not tracked:
        tracked = ["NIFTY", "BANKNIFTY"]
    snapshot = {}
    for sym in tracked:
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


@app.get("/api/analytics/{symbol}")
async def get_symbol_analytics(symbol: str, timeframe: str = "1m"):
    state = feature_engine.get_latest_market_state(symbol.upper(), timeframe)
    if not state:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "status": "warming_up",
            "message": "Collecting initial candles to compute indicators (requires at least 5 bars)."
        }
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "close": state.close,
        "volatility": {
            "atr": state.atr,
            "normalized_atr_pct": state.normalized_atr_pct
        },
        "trend": {
            "adx": state.adx,
            "plus_di": state.plus_di,
            "minus_di": state.minus_di,
            "is_trending": state.is_trending,
            "trend_bias": state.trend_bias
        },
        "vwap": {
            "vwap": state.vwap,
            "upper_band": state.vwap_upper_band,
            "lower_band": state.vwap_lower_band,
            "price_vs_vwap": state.price_vs_vwap
        },
        "momentum": {
            "rsi": state.rsi,
            "rsi_state": state.rsi_state
        },
        "moving_averages": {
            "ema_9": state.ema_9,
            "ema_21": state.ema_21,
            "ema_50": state.ema_50,
            "alignment": state.ema_alignment
        },
        "volume": {
            "current": state.current_volume,
            "volume_ratio_20": state.volume_ratio_20
        },
        "candle_structure": {
            "body_ratio": state.body_ratio,
            "consecutive_direction_bars": state.consecutive_direction_bars
        },
        "timestamp": state.candle_time.isoformat() if state.candle_time else None
    }
