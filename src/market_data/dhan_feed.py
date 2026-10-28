import asyncio
from datetime import datetime
import json
import struct
from typing import Dict, List, Optional
import websockets
from config.settings import Settings
from src.core.events import EventBus, FeedState, TickEvent
from src.core.logging import get_logger
from src.market_data.data_monitor import DataQualityMonitor

logger = get_logger("dhan_feed")


class DhanMarketFeed:
    """Manages real-time WebSocket connection to the DhanHQ Market Data Feed."""

    DHAN_WSS_URL = "wss://api-feed.dhan.co"

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        data_monitor: DataQualityMonitor,
        subscribed_instruments: Optional[List[Dict[str, str]]] = None
    ):
        self.settings = settings
        self.event_bus = event_bus
        self.data_monitor = data_monitor
        # E.g. [{"ExchangeSegment": "NSE_FNO", "SecurityId": "49544", "Symbol": "NIFTY24OCT24500CE"}]
        self.subscribed_instruments = subscribed_instruments or []
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = 1.0
        self._symbol_map: Dict[str, str] = {
            item["SecurityId"]: item.get("Symbol", item["SecurityId"])
            for item in self.subscribed_instruments
        }

    def add_instrument(self, exchange_segment: str, security_id: str, symbol: str):
        self.subscribed_instruments.append({
            "ExchangeSegment": exchange_segment,
            "SecurityId": security_id,
            "Symbol": symbol
        })
        self._symbol_map[security_id] = symbol

    async def start(self):
        self._running = True
        while self._running:
            try:
                self.data_monitor.update_feed_state(FeedState.RECONNECTING, "Connecting to Dhan WebSocket feed...")
                async with websockets.connect(self.DHAN_WSS_URL, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    self.data_monitor.update_feed_state(FeedState.CONNECTED, "Dhan WebSocket connected")
                    self._reconnect_delay = 1.0  # Reset backoff

                    # Send authentication and subscription
                    await self._authenticate_and_subscribe()

                    # Listen for incoming stream packets
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)

            except (websockets.ConnectionClosed, OSError, Exception) as exc:
                self.data_monitor.update_feed_state(FeedState.DISCONNECTED, f"Feed error: {str(exc)}")
                logger.error("Dhan feed disconnected", error=str(exc), retry_in=self._reconnect_delay)
                if not self._running:
                    break
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(30.0, self._reconnect_delay * 1.5)

    async def _authenticate_and_subscribe(self):
        """Sends auth payload and subscription request to Dhan WebSocket."""
        if not self.settings.DHAN_CLIENT_ID or not self.settings.DHAN_ACCESS_TOKEN:
            logger.warning("Missing Dhan credentials; skipping remote auth payload.")
            return

        auth_payload = {
            "RequestCode": 11,  # Dhan auth request code
            "ClientId": self.settings.DHAN_CLIENT_ID,
            "Token": self.settings.DHAN_ACCESS_TOKEN
        }
        await self._ws.send(json.dumps(auth_payload))
        logger.info("Sent Dhan WebSocket authentication request")

        if self.subscribed_instruments:
            sub_payload = {
                "RequestCode": 15,  # Subscribe market data
                "InstrumentCount": len(self.subscribed_instruments),
                "InstrumentList": [
                    {
                        "ExchangeSegment": item["ExchangeSegment"],
                        "SecurityId": item["SecurityId"]
                    }
                    for item in self.subscribed_instruments
                ]
            }
            await self._ws.send(json.dumps(sub_payload))
            logger.info("Sent Dhan instrument subscription request", count=len(self.subscribed_instruments))

    async def _handle_message(self, message: bytes | str):
        """Decodes Dhan feed message (JSON or binary packet)."""
        try:
            if isinstance(message, str):
                data = json.loads(message)
                # JSON format fallback
                security_id = str(data.get("security_id", ""))
                symbol = self._symbol_map.get(security_id, security_id)
                ltp = float(data.get("ltp", 0.0))
                volume = int(data.get("volume", 0))

                tick = TickEvent(
                    security_id=security_id,
                    symbol=symbol,
                    ltp=ltp,
                    volume=volume,
                    bid_price=float(data.get("bid", 0.0)),
                    ask_price=float(data.get("ask", 0.0)),
                    open_interest=int(data.get("oi", 0)),
                    timestamp=datetime.now()
                )
            else:
                # Binary packet handling for Dhan's binary market feed protocol
                # Dhan binary packet format: 1 byte response code, 2 bytes msg length, 1 byte exchange, 4 bytes security_id, 4 bytes LTP
                if len(message) < 8:
                    return
                response_code = message[0]
                # Fast unpack of security id and LTP
                if len(message) >= 12:
                    security_id_int, ltp_int = struct.unpack_from("<II", message, 4)
                    security_id = str(security_id_int)
                    symbol = self._symbol_map.get(security_id, security_id)
                    ltp = round(ltp_int / 100.0, 2)
                    tick = TickEvent(
                        security_id=security_id,
                        symbol=symbol,
                        ltp=ltp,
                        volume=0,
                        timestamp=datetime.now()
                    )
                else:
                    return

            # Run through data quality monitor
            is_valid = await self.data_monitor.on_tick(tick)
            if is_valid:
                await self.event_bus.publish(tick)

        except Exception as exc:
            logger.debug("Error parsing feed message", error=str(exc))

    def stop(self):
        self._running = False
        if self._ws:
            asyncio.create_task(self._ws.close())
        logger.info("Dhan feed stopped")
