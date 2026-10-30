import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dhanhq import DhanContext, dhanhq, MarketFeed
from config.settings import Settings
from src.core.events import CandleEvent, EventBus, FeedState, TickEvent
from src.core.logging import get_logger
from src.market_data.data_monitor import DataQualityMonitor

logger = get_logger("dhan_feed")


class DhanMarketFeed:
    """
    Direct Real-Time Live Market Feed powered by DhanHQ Data API & WebSockets.
    Streams live ticks for NIFTY 50, BANKNIFTY, and active ATM option strikes
    with live LTP, Greeks, and preloaded intraday 1-minute bars.
    """

    NIFTY_SEC_ID = "13"
    BANKNIFTY_SEC_ID = "25"

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        data_monitor: DataQualityMonitor
    ):
        self.settings = settings
        self.event_bus = event_bus
        self.data_monitor = data_monitor
        self._running = False
        self._reconnect_delay = 1.0

        # Dhan context & REST client
        self._ctx = DhanContext(self.settings.DHAN_CLIENT_ID, self.settings.DHAN_ACCESS_TOKEN)
        self._dhan = dhanhq(self._ctx)

        # Mapping: security_id (str) -> symbol name (e.g., '13' -> 'NIFTY')
        self._symbol_map: Dict[str, str] = {
            self.NIFTY_SEC_ID: "NIFTY",
            self.BANKNIFTY_SEC_ID: "BANKNIFTY"
        }
        self._subscribed_tuples: List[tuple] = [
            (MarketFeed.IDX, self.NIFTY_SEC_ID, MarketFeed.Quote),
            (MarketFeed.IDX, self.BANKNIFTY_SEC_ID, MarketFeed.Quote)
        ]
        self._last_spot_prices: Dict[str, float] = {
            "NIFTY": 23100.0,
            "BANKNIFTY": 54900.0
        }
        self._active_strikes: Dict[str, float] = {}
        self._market_feed: Optional[MarketFeed] = None

    def get_security_id(self, symbol: str) -> Optional[str]:
        """Returns the Dhan numeric security ID for a symbol name."""
        for sec_id, sym in self._symbol_map.items():
            if sym == symbol:
                return sec_id
        return None

    async def preload_history(self, num_bars: int = 60):
        """Preloads real intraday 1-minute historical candles from Dhan for instant indicator warmup."""
        logger.info("Preloading live intraday historical candles from Dhan...")
        today_str = datetime.now().strftime("%Y-%m-%d")

        for sec_id, symbol in [(self.NIFTY_SEC_ID, "NIFTY"), (self.BANKNIFTY_SEC_ID, "BANKNIFTY")]:
            try:
                hist = await asyncio.to_thread(
                    self._dhan.intraday_minute_data,
                    security_id=sec_id,
                    exchange_segment="IDX_I",
                    instrument_type="INDEX",
                    from_date=today_str,
                    to_date=today_str
                )
                if hist.get("status") == "success" and "data" in hist:
                    d = hist["data"]
                    opens = d.get("open", [])
                    highs = d.get("high", [])
                    lows = d.get("low", [])
                    closes = d.get("close", [])
                    timestamps = d.get("start_Time", [])
                    volumes = d.get("volume", [1000] * len(opens))

                    count = len(opens)
                    start_idx = max(0, count - num_bars)
                    loaded_count = 0

                    for i in range(start_idx, count):
                        candle_dt = datetime.now()
                        if i < len(timestamps) and timestamps[i]:
                            try:
                                candle_dt = datetime.fromtimestamp(float(timestamps[i]))
                            except Exception:
                                pass

                        candle = CandleEvent(
                            symbol=symbol,
                            timeframe="1m",
                            open=round(float(opens[i]), 2),
                            high=round(float(highs[i]), 2),
                            low=round(float(lows[i]), 2),
                            close=round(float(closes[i]), 2),
                            volume=int(volumes[i] if i < len(volumes) else 1000),
                            candle_start=candle_dt,
                            is_closed=True
                        )
                        await self.event_bus.publish(candle)
                        loaded_count += 1

                    if count > 0 and closes:
                        self._last_spot_prices[symbol] = round(float(closes[-1]), 2)
                    logger.info("Preloaded Dhan candles successfully", symbol=symbol, bars_loaded=loaded_count)
            except Exception as exc:
                logger.warning("Failed to preload Dhan historical candles", symbol=symbol, error=str(exc))

    async def _resolve_and_subscribe_atm_options(self):
        """Fetches Dhan option chain to map ATM strike security IDs and subscribe to live ticks."""
        nifty_expiry = self.settings.NIFTY_EXPIRY_DATE[:10] if self.settings.NIFTY_EXPIRY_DATE else "2026-11-03"
        banknifty_expiry = self.settings.BANKNIFTY_EXPIRY_DATE[:10] if self.settings.BANKNIFTY_EXPIRY_DATE else "2026-11-23"

        # 1. Resolve NIFTY ATM
        try:
            nifty_spot = self._last_spot_prices.get("NIFTY", 23100.0)
            nifty_atm = round(nifty_spot / 50.0) * 50
            chain = await asyncio.to_thread(self._dhan.option_chain, 13, "IDX_I", nifty_expiry)
            oc = chain.get("data", {}).get("data", {}).get("oc", {})
            strike_key = f"{nifty_atm:.6f}"
            if strike_key in oc:
                for opt_type, data in [("CE", oc[strike_key].get("ce", {})), ("PE", oc[strike_key].get("pe", {}))]:
                    sec_id = str(data.get("security_id"))
                    if sec_id and sec_id != "None":
                        sym = f"NIFTY_{int(nifty_atm)}_{opt_type}"
                        self._symbol_map[sec_id] = sym
                        self._subscribed_tuples.append((MarketFeed.NSE_FNO, sec_id, MarketFeed.Quote))
                        logger.info("Mapped Dhan NIFTY ATM option", symbol=sym, security_id=sec_id, ltp=data.get("last_price"))
        except Exception as e:
            logger.warning("Error resolving NIFTY option chain", error=str(e))

        # 2. Resolve BANKNIFTY ATM
        try:
            bn_spot = self._last_spot_prices.get("BANKNIFTY", 54900.0)
            bn_atm = round(bn_spot / 100.0) * 100
            chain_bn = await asyncio.to_thread(self._dhan.option_chain, 25, "IDX_I", banknifty_expiry)
            oc_bn = chain_bn.get("data", {}).get("data", {}).get("oc", {})
            strike_key_bn = f"{bn_atm:.6f}"
            if strike_key_bn in oc_bn:
                for opt_type, data in [("CE", oc_bn[strike_key_bn].get("ce", {})), ("PE", oc_bn[strike_key_bn].get("pe", {}))]:
                    sec_id = str(data.get("security_id"))
                    if sec_id and sec_id != "None":
                        sym = f"BANKNIFTY_{int(bn_atm)}_{opt_type}"
                        self._symbol_map[sec_id] = sym
                        self._subscribed_tuples.append((MarketFeed.NSE_FNO, sec_id, MarketFeed.Quote))
                        logger.info("Mapped Dhan BANKNIFTY ATM option", symbol=sym, security_id=sec_id, ltp=data.get("last_price"))
        except Exception as e:
            logger.warning("Error resolving BANKNIFTY option chain", error=str(e))

    async def start(self):
        """Starts real-time Dhan market feed."""
        self._running = True
        logger.info("Starting Dhan Live Market Feed...")

        # Preload history for instant warm indicators
        await self.preload_history(num_bars=60)

        # Resolve ATM options from Dhan
        await self._resolve_and_subscribe_atm_options()

        self.data_monitor.update_feed_state(FeedState.CONNECTED, "Dhan Live Market Feed Active (WebSocket)")

        while self._running:
            try:
                # Initialize MarketFeed with unique tuples
                unique_instruments = list(dict.fromkeys(self._subscribed_tuples))
                self._market_feed = MarketFeed(
                    self._ctx,
                    unique_instruments,
                    version="v2"
                )
                await self._market_feed.connect()
                logger.info("Dhan WebSocket stream connected successfully", instruments=len(unique_instruments))
                self.data_monitor.update_feed_state(FeedState.CONNECTED, "Dhan Live Stream Connected")
                self._reconnect_delay = 1.0

                while self._running:
                    packet = await self._market_feed.get_instrument_data()
                    if not packet or not self._running:
                        break
                    await self._process_tick_packet(packet)

            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as exc:
                self.data_monitor.update_feed_state(FeedState.RECONNECTING, f"Dhan feed reconnecting: {str(exc)}")
                logger.warning("Dhan feed stream interrupted, reconnecting...", error=str(exc), retry_in=self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(30.0, self._reconnect_delay * 1.5)

    async def _process_tick_packet(self, packet: dict):
        """Translates raw Dhan packet into a validated TickEvent."""
        try:
            sec_id = str(packet.get("security_id", ""))
            symbol = self._symbol_map.get(sec_id)
            if not symbol:
                return

            raw_ltp = packet.get("LTP")
            if not raw_ltp:
                return
            ltp = float(raw_ltp)
            if ltp <= 0:
                return

            volume = int(packet.get("volume", 0) or 0)
            oi = int(packet.get("oi", 0) or 0)
            depth = packet.get("depth", {})
            bid = float(depth.get("buy", [{}])[0].get("price", 0.0) or ltp)
            ask = float(depth.get("sell", [{}])[0].get("price", 0.0) or ltp)

            # Update cache
            if symbol in self._last_spot_prices:
                self._last_spot_prices[symbol] = ltp

            tick = TickEvent(
                security_id=sec_id,
                symbol=symbol,
                ltp=ltp,
                volume=volume,
                bid_price=bid,
                ask_price=ask,
                open_interest=oi,
                timestamp=datetime.now()
            )

            is_valid = await self.data_monitor.on_tick(tick)
            if is_valid:
                await self.event_bus.publish(tick)

        except Exception as e:
            logger.debug("Error processing Dhan tick packet", error=str(e))

    def stop(self):
        self._running = False
        if self._market_feed:
            try:
                asyncio.create_task(self._market_feed.disconnect())
            except Exception:
                pass
        logger.info("Dhan Live Market Feed stopped")
