import asyncio
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional
import aiohttp
from src.core.events import EventBus, FeedState, TickEvent
from src.core.logging import get_logger
from src.market_data.data_monitor import DataQualityMonitor
from src.analytics.options_pricing import BlackScholesEngine

logger = get_logger("live_market_fetcher")


class LiveMarketFetcher:
    """Fetches real live NSE index prices and computes dynamic Black-Scholes options pricing and Greeks."""

    SYMBOLS = {
        "NIFTY": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "INDIAVIX": "^INDIAVIX"
    }

    def __init__(
        self,
        event_bus: EventBus,
        data_monitor: DataQualityMonitor,
        poll_interval_seconds: float = 3.0
    ):
        self.event_bus = event_bus
        self.data_monitor = data_monitor
        self.poll_interval = poll_interval_seconds
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_prices: Dict[str, float] = {
            "NIFTY": 22700.0,
            "BANKNIFTY": 54300.0,
            "INDIAVIX": 16.0
        }

    async def start(self):
        self._running = True
        self._session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        self.data_monitor.update_feed_state(FeedState.CONNECTED, "Live Real-Time NSE Market Feed Active")
        logger.info("Live Market Fetcher started (Real NSE market sync)")

        while self._running:
            try:
                for symbol, ticker in self.SYMBOLS.items():
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                    async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result = data.get("chart", {}).get("result", [])
                            if result:
                                meta = result[0].get("meta", {})
                                ltp = round(float(meta.get("regularMarketPrice", 0.0)), 2)
                                vol = int(meta.get("regularMarketVolume", 0))

                                if ltp > 0:
                                    self._last_prices[symbol] = ltp
                                    spread = 0.50
                                    bid = round(ltp - (spread / 2), 2)
                                    ask = round(ltp + (spread / 2), 2)

                                    tick = TickEvent(
                                        security_id=symbol,
                                        symbol=symbol,
                                        ltp=ltp,
                                        volume=vol,
                                        bid_price=bid,
                                        ask_price=ask,
                                        timestamp=datetime.now()
                                    )
                                    is_valid = await self.data_monitor.on_tick(tick)
                                    if is_valid:
                                        await self.event_bus.publish(tick)

                # Calculate dynamic options prices using live Black-Scholes and live India VIX
                nifty_ltp = self._last_prices.get("NIFTY")
                india_vix = self._last_prices.get("INDIAVIX", 16.0)
                vol_annual = max(0.08, india_vix / 100.0)

                if nifty_ltp and nifty_ltp > 0:
                    # Dynamic strike: nearest 50-point strike
                    atm_strike = round(nifty_ltp / 50.0) * 50.0

                    # Dynamic time to weekly expiry (assume next Thursday 15:30 IST)
                    now_dt = datetime.now()
                    days_until_thursday = (3 - now_dt.weekday()) % 7
                    if days_until_thursday == 0 and now_dt.hour >= 15:
                        days_until_thursday = 7
                    expiry_dt = (now_dt + timedelta(days=days_until_thursday)).replace(hour=15, minute=30, second=0)
                    time_to_expiry_years = BlackScholesEngine.calculate_time_to_expiry_years(expiry_dt, now_dt)

                    for opt_type in ["CE", "PE"]:
                        greeks = BlackScholesEngine.calculate(
                            spot=nifty_ltp,
                            strike=atm_strike,
                            time_to_expiry_years=time_to_expiry_years,
                            volatility_annual=vol_annual,
                            risk_free_rate=0.065,
                            option_type=opt_type,
                            tick_size=0.05
                        )

                        opt_sym = f"NIFTY_{int(atm_strike)}_{opt_type}"
                        opt_tick = TickEvent(
                            security_id=opt_sym,
                            symbol=opt_sym,
                            ltp=greeks.theoretical_price,
                            volume=int(abs(greeks.delta) * 50000),
                            bid_price=greeks.bid,
                            ask_price=greeks.ask,
                            timestamp=now_dt
                        )
                        if await self.data_monitor.on_tick(opt_tick):
                            await self.event_bus.publish(opt_tick)

            except asyncio.TimeoutError:
                logger.debug("Market data fetch timeout; retrying in next cycle...")
            except Exception as e:
                logger.warning(
                    "Error fetching real market data",
                    error_type=type(e).__name__,
                    error=str(e) or repr(e)
                )

            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
        logger.info("Live Market Fetcher stopped")

