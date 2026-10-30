import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import (
    ENV_PATH,
    MarketDataSource,
    Settings,
    TradingMode,
    get_fresh_settings,
    settings
)
from src.core.events import CandleEvent, EventBus, FeedState, TickEvent
from src.core.logging import get_logger, setup_logger
from src.market_data.candle_builder import CandleBuilder
from src.market_data.data_monitor import DataQualityMonitor
from src.market_data.dhan_feed import DhanMarketFeed
from src.market_data.simulator import MarketDataSimulator
from src.market_data.live_market_fetcher import LiveMarketFetcher
from src.analytics.feature_engine import FeatureEngine
from src.regime.classifier import MarketRegimeClassifier
from src.regime.permission_engine import TradePermissionEngine
from src.strategy.options_momentum_strategy import OptionsMomentumStrategy
from src.risk.risk_manager import RiskManager
from src.execution.order_model import OrderStatus
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.dhan_gateway import DhanOrderGateway
from src.execution.execution_router import ExecutionRouter
from src.execution.safe_mode_manager import SafeModeManager, SetupState
from src.backtest.backtest_engine import HistoricalBacktestEngine

# Setup structured logging
setup_logger(settings.LOG_LEVEL)
logger = get_logger("main")

# Core system state
event_bus = EventBus()
data_monitor = DataQualityMonitor(event_bus, max_stale_seconds=settings.MAX_STALE_TICK_SECONDS)
candle_builder = CandleBuilder(event_bus, timeframes=["1m", "3m", "5m"])
feature_engine = FeatureEngine(event_bus, max_history_bars=200)
regime_classifier = MarketRegimeClassifier(data_monitor=data_monitor)
permission_engine = TradePermissionEngine(settings=settings)
strategy = OptionsMomentumStrategy()
risk_manager = RiskManager(settings=settings)
paper_engine = PaperExecutionEngine(event_bus=event_bus, risk_manager=risk_manager)
dhan_gateway = DhanOrderGateway(settings=settings)
execution_router = ExecutionRouter(settings=settings, paper_engine=paper_engine, dhan_gateway=dhan_gateway)
safe_mode_manager = SafeModeManager(settings=settings)
backtest_engine = HistoricalBacktestEngine()
simulator: Optional[MarketDataSimulator] = None
dhan_feed: Optional[DhanMarketFeed] = None
live_fetcher: Optional[LiveMarketFetcher] = None
background_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reload settings on startup
    global settings
    settings = get_fresh_settings()
    execution_router.settings = settings
    dhan_gateway.settings = settings
    safe_mode_manager.settings = settings
    permission_engine.settings = settings
    risk_manager.settings = settings

    # Clear lingering tracking state
    data_monitor._last_prices.clear()
    data_monitor._last_tick_times.clear()
    candle_builder._active_candles.clear()

    # Register core subscribers
    event_bus.subscribe(TickEvent, data_monitor.on_tick)
    event_bus.subscribe(TickEvent, candle_builder.on_tick)
    event_bus.subscribe(CandleEvent, feature_engine.on_candle)
    event_bus.subscribe(TickEvent, paper_engine.on_tick)

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
        live_fetcher = LiveMarketFetcher(event_bus, data_monitor, poll_interval_seconds=3.0)
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

    # Autonomous trading execution loop
    async def autonomous_trade_loop():
        logger.info("Autonomous Trade Engine Loop started")
        while True:
            try:
                await asyncio.sleep(2.5)  # Scan every 2.5s

                # Check emergency halt
                if risk_manager.is_emergency_halt:
                    continue

                # Check max open positions
                if len(paper_engine.open_positions) >= risk_manager.max_open_positions:
                    continue

                for sym in ["NIFTY", "BANKNIFTY"]:
                    state = feature_engine.get_latest_market_state(sym, "1m")
                    if not state:
                        continue

                    history_df = feature_engine.get_history(sym, "1m")
                    classification = regime_classifier.classify(state, history_df=history_df)
                    decision = permission_engine.evaluate(classification)

                    if not decision.is_permitted:
                        continue

                    # Dynamic ATM strike selection
                    strike_step = 50.0 if "NIFTY" in sym else 100.0
                    atm_strike = round(state.close / strike_step) * strike_step
                    approx_opt_sym = f"{sym}_{int(atm_strike)}_CE"
                    opt_price = data_monitor.get_last_price(approx_opt_sym) or 130.0

                    proposal = strategy.evaluate(
                        state=state,
                        permission=decision,
                        current_option_price=opt_price
                    )
                    if not proposal:
                        continue

                    lot_size = 25 if "NIFTY" in sym else 15

                    setup = safe_mode_manager.get_pending_or_armed_setup(proposal.symbol)
                    if not setup:
                        setup = safe_mode_manager.register_proposal(proposal)

                    is_autonomous = not safe_mode_manager.is_safe_mode()
                    is_armed = setup.state == SetupState.ARMED

                    if is_autonomous or is_armed:
                        approval = risk_manager.validate_and_size(
                            proposal,
                            lot_size=lot_size,
                            available_cash=paper_engine.available_cash,
                            record_order=True
                        )
                        if not approval.is_approved:
                            logger.debug("Autonomous setup rejected by risk manager", reasons=approval.rejection_reasons)
                            continue

                        current_price = data_monitor.get_last_price(proposal.symbol) or proposal.expected_entry_price
                        valid, reason = safe_mode_manager.validate_anti_chasing(setup.setup_id, current_market_price=current_price)
                        if not valid:
                            logger.warning("Anti-chasing prevented execution", reason=reason)
                            continue

                        order = await execution_router.execute_approved_proposal(approval)
                        if order and order.status == OrderStatus.FILLED:
                            safe_mode_manager.mark_triggered(setup.setup_id)
                            logger.info(
                                "AUTONOMOUS TRADE EXECUTED",
                                symbol=order.symbol,
                                quantity=order.quantity,
                                fill_price=order.filled_price,
                                mode=settings.TRADING_MODE.value
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in autonomous trading loop", error=str(e))

    auto_task = asyncio.create_task(autonomous_trade_loop())
    background_tasks.append(auto_task)

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


@app.get("/api/market/candles/{symbol}")
async def get_symbol_candles(symbol: str, timeframe: str = "1m", limit: int = 150):
    df = feature_engine.get_history(symbol.upper(), timeframe)
    candles = []
    if not df.empty:
        for _, row in df.tail(limit).iterrows():
            ts = row["timestamp"]
            unix_time = int(ts.timestamp()) if hasattr(ts, "timestamp") else int(datetime.fromisoformat(str(ts)).timestamp())
            candles.append({
                "time": unix_time,
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": float(row.get("volume", 0))
            })
    
    current_candle = candle_builder.get_current_candle(symbol.upper(), timeframe)
    state = feature_engine.get_latest_market_state(symbol.upper(), timeframe)

    indicators = None
    if state:
        indicators = {
            "vwap": state.vwap,
            "vwap_upper": state.vwap_upper_band,
            "vwap_lower": state.vwap_lower_band,
            "ema_9": state.ema_9,
            "ema_21": state.ema_21,
            "ema_50": state.ema_50,
            "rsi": state.rsi,
            "atr": state.atr
        }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles,
        "current_candle": current_candle,
        "indicators": indicators
    }


@app.post("/api/execution/panic-close-all")
async def panic_close_all():
    risk_manager.trigger_emergency_halt("User clicked PANIC SQUARE OFF from Dashboard")
    closed_trades = await paper_engine.close_all_positions(exit_reason="USER_PANIC_SQUARE_OFF")
    return {
        "status": "HALTED",
        "positions_closed": len(closed_trades),
        "trades": [
            {
                "symbol": t.symbol,
                "exit_price": t.exit_price,
                "net_pnl": t.net_pnl
            }
            for t in closed_trades
        ],
        "message": f"Successfully squared off {len(closed_trades)} active positions and halted trading."
    }


@app.post("/api/execution/reset-halt")
async def reset_halt():
    risk_manager.reset_emergency_halt()
    return {"status": "ACTIVE", "is_emergency_halt": False, "message": "Emergency halt reset. Trading re-enabled."}


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


@app.get("/api/regime/{symbol}")
async def get_symbol_regime_and_permission(symbol: str, timeframe: str = "1m"):
    state = feature_engine.get_latest_market_state(symbol.upper(), timeframe)
    if not state:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "status": "warming_up",
            "message": "Collecting market data to establish regime."
        }

    history_df = feature_engine.get_history(symbol.upper(), timeframe)
    classification = regime_classifier.classify(state, history_df=history_df)
    decision = permission_engine.evaluate(classification)

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "classification": {
            "regime": classification.regime.value,
            "confidence": classification.confidence,
            "primary_reason": classification.primary_reason,
            "details": classification.details
        },
        "permission": {
            "is_permitted": decision.is_permitted,
            "state": decision.state.value,
            "allowed_directions": decision.allowed_directions,
            "reasons": decision.reasons
        },
        "timestamp": decision.timestamp.isoformat()
    }


@app.get("/api/strategy/proposal/{symbol}")
async def evaluate_strategy_proposal(symbol: str, timeframe: str = "1m"):
    state = feature_engine.get_latest_market_state(symbol.upper(), timeframe)
    if not state:
        return {"status": "no_data", "message": "Market state not yet available."}

    history_df = feature_engine.get_history(symbol.upper(), timeframe)
    classification = regime_classifier.classify(state, history_df=history_df)
    decision = permission_engine.evaluate(classification)

    # Estimate option price dynamically or fetch from last prices
    atm_strike = round(state.close / 50.0) * 50.0
    approx_opt_sym = f"NIFTY_{int(atm_strike)}_CE"
    opt_price = data_monitor.get_last_price(approx_opt_sym) or 130.0

    proposal = strategy.evaluate(
        state=state,
        permission=decision,
        current_option_price=opt_price
    )

    if not proposal:
        return {
            "symbol": symbol.upper(),
            "status": "NO_SETUP",
            "message": "Market conditions or strategy rules did not produce an actionable setup.",
            "permission_state": decision.state.value,
            "regime": classification.regime.value
        }

    # Pass through Risk Manager for dynamic sizing (read-only query: record_order=False)
    lot_size = 25 if "NIFTY" in symbol.upper() else 15
    approval = risk_manager.validate_and_size(proposal, lot_size=lot_size, record_order=False)

    return {
        "status": "PROPOSED",
        "proposal": {
            "strategy": proposal.strategy_name,
            "contract": proposal.symbol,
            "direction": proposal.direction.value,
            "entry_price": proposal.expected_entry_price,
            "stop_loss": proposal.stop_loss_price,
            "target": proposal.target_price,
            "risk_points": proposal.risk_points,
            "reward_points": proposal.reward_points,
            "risk_reward_ratio": proposal.risk_reward_ratio,
            "reasons": proposal.reasons,
            "invalidation_conditions": proposal.invalidation_conditions
        },
        "risk_assessment": {
            "is_approved": approval.is_approved,
            "lots": approval.lots,
            "quantity": approval.approved_quantity,
            "total_risk_amount": approval.total_risk_amount,
            "total_capital_required": approval.total_capital_required,
            "rejection_reasons": approval.rejection_reasons
        }
    }


@app.get("/api/risk/status")
async def get_risk_status():
    return {
        "is_emergency_halt": risk_manager.is_emergency_halt,
        "cumulative_daily_pnl": risk_manager.cumulative_daily_pnl,
        "max_daily_loss": risk_manager.max_daily_loss,
        "max_per_trade_risk": risk_manager.max_per_trade_risk,
        "max_open_positions": risk_manager.max_open_positions,
        "max_capital_per_trade": risk_manager.max_capital_per_trade
    }


@app.get("/api/safe-mode/status")
async def get_safe_mode_status():
    return {
        "safe_mode_enabled": safe_mode_manager.is_safe_mode(),
        "max_entry_slippage_pct": settings.MAX_ENTRY_SLIPPAGE_PCT,
        "trading_mode": settings.TRADING_MODE.value,
        "is_live": execution_router.is_live,
        "active_setups": safe_mode_manager.get_active_setups()
    }


@app.post("/api/safe-mode/arm/{setup_id}")
async def arm_setup_endpoint(setup_id: str):
    success, msg = safe_mode_manager.arm_setup(setup_id)
    return {"setup_id": setup_id, "success": success, "message": msg}


@app.post("/api/safe-mode/disarm/{setup_id}")
async def disarm_setup_endpoint(setup_id: str, reason: str = "User cancelled"):
    success, msg = safe_mode_manager.disarm_setup(setup_id, reason=reason)
    return {"setup_id": setup_id, "success": success, "message": msg}


@app.post("/api/safe-mode/toggle")
async def toggle_safe_mode_endpoint(enabled: bool):
    safe_mode_manager.toggle_safe_mode(enabled)
    return {"safe_mode_enabled": safe_mode_manager.is_safe_mode()}


@app.post("/api/settings/mode")
async def set_trading_mode(mode: str):
    global settings
    target_mode = mode.upper()
    if target_mode not in ["PAPER", "LIVE"]:
        return {"error": f"Invalid mode: {mode}. Must be 'PAPER' or 'LIVE'"}
    
    # Update .env file on disk
    if ENV_PATH.exists():
        env_content = ENV_PATH.read_text(encoding="utf-8")
        lines = env_content.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("TRADING_MODE="):
                new_lines.append(f"TRADING_MODE={target_mode}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.insert(0, f"TRADING_MODE={target_mode}")
        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Reload runtime settings
    settings = get_fresh_settings()
    execution_router.settings = settings
    dhan_gateway.settings = settings
    safe_mode_manager.settings = settings
    permission_engine.settings = settings
    risk_manager.settings = settings

    logger.info("Trading mode switched", new_mode=settings.TRADING_MODE.value, is_live=execution_router.is_live)
    return {
        "status": "SUCCESS",
        "trading_mode": settings.TRADING_MODE.value,
        "is_live": execution_router.is_live,
        "live_trading_enabled": settings.TRADING_MODE == TradingMode.LIVE
    }


@app.post("/api/settings/reload")
async def reload_settings_endpoint():
    global settings
    settings = get_fresh_settings()
    execution_router.settings = settings
    dhan_gateway.settings = settings
    safe_mode_manager.settings = settings
    permission_engine.settings = settings
    risk_manager.settings = settings
    return {
        "status": "RELOADED",
        "trading_mode": settings.TRADING_MODE.value,
        "is_live": execution_router.is_live,
        "safe_mode": settings.SAFE_MODE
    }


@app.get("/api/paper/portfolio")
async def get_paper_portfolio():
    return paper_engine.get_portfolio_summary()


@app.get("/api/paper/positions")
async def get_paper_positions():
    return [
        {
            "symbol": pos.symbol,
            "underlying": pos.underlying,
            "option_type": pos.option_type,
            "quantity": pos.quantity,
            "avg_entry_price": pos.average_entry_price,
            "current_price": pos.current_market_price,
            "stop_loss": pos.stop_loss_price,
            "target": pos.target_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "strategy": pos.strategy_name,
            "entry_time": pos.entry_time.isoformat()
        }
        for pos in paper_engine.open_positions.values()
    ]


@app.get("/api/paper/trades")
async def get_paper_trades():
    return [
        {
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "type": t.option_type,
            "quantity": t.quantity,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "gross_pnl": t.gross_pnl,
            "taxes_and_costs": t.statutory_costs,
            "net_pnl": t.net_pnl,
            "return_pct": t.return_pct,
            "exit_reason": t.exit_reason,
            "strategy": t.strategy_name,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat()
        }
        for t in paper_engine.closed_trades
    ]


@app.post("/api/paper/execute-proposal/{symbol}")
async def execute_paper_trade(symbol: str, timeframe: str = "1m"):
    state = feature_engine.get_latest_market_state(symbol.upper(), timeframe)
    if not state:
        return {"status": "REJECTED", "message": "No market state available."}

    history_df = feature_engine.get_history(symbol.upper(), timeframe)
    classification = regime_classifier.classify(state, history_df=history_df)
    decision = permission_engine.evaluate(classification)

    atm_strike = round(state.close / 50.0) * 50.0
    approx_opt_sym = f"NIFTY_{int(atm_strike)}_CE"
    opt_price = data_monitor.get_last_price(approx_opt_sym) or 130.0

    proposal = strategy.evaluate(state=state, permission=decision, current_option_price=opt_price)
    if not proposal:
        return {"status": "REJECTED", "message": "Strategy did not produce a setup under current conditions."}

    lot_size = 25 if "NIFTY" in symbol.upper() else 15
    approval = risk_manager.validate_and_size(proposal, lot_size=lot_size, available_cash=paper_engine.available_cash)
    if not approval.is_approved:
        return {"status": "REJECTED", "reasons": approval.rejection_reasons}

    # Safe Mode & Anti-Chasing Validation
    setup = safe_mode_manager.register_proposal(proposal)
    current_price = data_monitor.get_last_price(proposal.symbol) or proposal.expected_entry_price

    valid, reason = safe_mode_manager.validate_anti_chasing(setup.setup_id, current_market_price=current_price)
    if not valid:
        return {"status": "REJECTED_CHASING", "message": reason, "setup_id": setup.setup_id}

    # Route execution dynamically through ExecutionRouter (respects TRADING_MODE)
    order = await execution_router.execute_approved_proposal(approval)
    if not order or order.status != OrderStatus.FILLED:
        return {"status": "REJECTED", "message": "Execution router failed to fill order or broker rejected."}

    safe_mode_manager.mark_triggered(setup.setup_id)

    return {
        "status": "EXECUTED",
        "trading_mode": settings.TRADING_MODE.value,
        "is_live": execution_router.is_live,
        "order_id": order.order_id,
        "symbol": order.symbol,
        "quantity": order.quantity,
        "fill_price": order.filled_price,
        "slippage": order.slippage,
        "stop_loss": proposal.stop_loss_price,
        "target": proposal.target_price
    }


@app.post("/api/backtest/run")
async def run_backtest(symbol: str = "NIFTY"):
    history_df = feature_engine.get_history(symbol.upper(), "1m")
    if len(history_df) < 30:
        return {"status": "insufficient_data", "message": "Need at least 30 historical candles to backtest."}

    lot_size = 25 if "NIFTY" in symbol.upper() else 15
    bt = HistoricalBacktestEngine(initial_capital=paper_engine.initial_capital, lot_size=lot_size)
    metrics = bt.run(history_df, symbol=symbol.upper())

    return {
        "status": "COMPLETED",
        "symbol": symbol.upper(),
        "total_trades": metrics.total_trades,
        "win_rate_pct": metrics.win_rate_pct,
        "gross_profit": metrics.gross_profit,
        "gross_loss": metrics.gross_loss,
        "net_pnl": metrics.net_pnl,
        "total_taxes_and_brokerage": metrics.total_transaction_costs,
        "profit_factor": metrics.profit_factor,
        "max_drawdown_amount": metrics.max_drawdown_amount,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "avg_trade_pnl": metrics.avg_trade_pnl,
        "sharpe_ratio": metrics.sharpe_ratio,
        "regime_breakdown": metrics.regime_breakdown,
        "trades": metrics.trades
    }
