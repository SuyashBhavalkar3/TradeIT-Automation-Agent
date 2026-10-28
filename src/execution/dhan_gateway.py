from datetime import datetime
from typing import Dict, List, Optional
from dhanhq import DhanContext, dhanhq
from config.settings import Settings, TradingMode
from src.core.logging import get_logger
from src.execution.order_model import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradeRecord
)
from src.risk.risk_manager import RiskApproval

logger = get_logger("dhan_gateway")


class DhanOrderGateway:
    """
    Operationally critical real-money broker order gateway for Dhan.
    Executes actual orders on the National Stock Exchange (NSE) via DhanHQ API.
    Guarded with strict safety assertion checks.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client_id = settings.DHAN_CLIENT_ID
        self.access_token = settings.DHAN_ACCESS_TOKEN
        self._dhan: Optional[dhanhq] = None

    def _get_client(self) -> dhanhq:
        if self._dhan is None:
            if not self.client_id or not self.access_token or "dummy" in self.client_id:
                raise ValueError("Cannot initialize live Dhan client: DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN is missing in .env")
            ctx = DhanContext(self.client_id, self.access_token)
            self._dhan = dhanhq(ctx)
        return self._dhan

    def execute_live_order(
        self,
        approval: RiskApproval,
        security_id: str
    ) -> Order:
        """Submits a real order to Dhan broker with strict validation."""
        # CRITICAL SAFETY ASSERTION 1: TRADING_MODE must be LIVE
        if self.settings.TRADING_MODE != TradingMode.LIVE:
            msg = f"SAFETY REFUSAL: Attempted to submit real order while TRADING_MODE is '{self.settings.TRADING_MODE.value}'! Order aborted."
            logger.critical(msg)
            raise RuntimeError(msg)

        proposal = approval.proposal
        quantity = approval.approved_quantity
        req_price = proposal.expected_entry_price

        # CRITICAL SAFETY ASSERTION 2: Non-zero positive quantity and valid security_id
        if quantity <= 0:
            raise ValueError(f"Invalid order quantity: {quantity}")
        if not security_id or str(security_id).strip() == "":
            raise ValueError("Invalid security_id: cannot submit order without valid Dhan security_id")

        client = self._get_client()

        # Map to Dhan constants
        txn_type = client.BUY if proposal.direction.value == "BUY_CALL" or proposal.direction.value == "BUY" else client.SELL
        order_type = client.MARKET  # Default to market order for reliable options fill
        exch_seg = client.NSE_FNO
        product_type = client.INTRA
        validity = client.DAY

        logger.info(
            "SUBMITTING REAL LIVE ORDER TO DHAN",
            security_id=security_id,
            symbol=proposal.symbol,
            quantity=quantity,
            txn_type="BUY" if txn_type == client.BUY else "SELL",
            expected_price=req_price
        )

        try:
            response = client.place_order(
                security_id=str(security_id),
                exchange_segment=exch_seg,
                transaction_type=txn_type,
                quantity=quantity,
                order_type=order_type,
                product_type=product_type,
                price=0.0,  # 0.0 for MARKET orders in Dhan API
                validity=validity
            )

            status = response.get("status")
            data = response.get("data", {})
            order_id = str(data.get("orderId", ""))

            if status == "success" and order_id:
                logger.info("Dhan order placed successfully", order_id=order_id, response=response)
                return Order(
                    order_id=order_id,
                    symbol=proposal.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    requested_price=req_price,
                    status=OrderStatus.SUBMITTED,
                    filled_price=req_price,
                    filled_quantity=quantity,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
            else:
                remarks = response.get("remarks", str(response))
                logger.error("Dhan broker rejected order placement", remarks=remarks)
                return Order(
                    order_id="",
                    symbol=proposal.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    requested_price=req_price,
                    status=OrderStatus.REJECTED,
                    rejection_reason=f"Broker rejection: {remarks}",
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )

        except Exception as exc:
            logger.critical("Exception during Dhan live order submission", error=str(exc))
            # Fallback: check order book before treating as failure
            try:
                orders = client.get_order_list().get("data", [])
                for o in orders:
                    if str(o.get("securityId")) == str(security_id) and o.get("quantity") == quantity:
                        oid = str(o.get("orderId"))
                        logger.warning("Discovered order was submitted despite network exception", order_id=oid)
                        return Order(
                            order_id=oid,
                            symbol=proposal.symbol,
                            side=OrderSide.BUY,
                            order_type=OrderType.MARKET,
                            quantity=quantity,
                            requested_price=req_price,
                            status=OrderStatus.SUBMITTED
                        )
            except Exception:
                pass

            return Order(
                order_id="",
                symbol=proposal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                requested_price=req_price,
                status=OrderStatus.REJECTED,
                rejection_reason=f"Connection exception: {str(exc)}"
            )

    def close_live_position(
        self,
        security_id: str,
        symbol: str,
        quantity: int
    ) -> Optional[str]:
        """Submits market square-off sell order to Dhan."""
        if self.settings.TRADING_MODE != TradingMode.LIVE:
            raise RuntimeError("SAFETY REFUSAL: Cannot close live position when TRADING_MODE is not LIVE")

        client = self._get_client()
        logger.info("SUBMITTING LIVE SQUARE-OFF TO DHAN", security_id=security_id, symbol=symbol, qty=quantity)

        try:
            resp = client.place_order(
                security_id=str(security_id),
                exchange_segment=client.NSE_FNO,
                transaction_type=client.SELL,
                quantity=quantity,
                order_type=client.MARKET,
                product_type=client.INTRA,
                price=0.0,
                validity=client.DAY
            )
            if resp.get("status") == "success":
                order_id = resp.get("data", {}).get("orderId", "")
                logger.info("Square-off order placed on Dhan", order_id=order_id)
                return str(order_id)
            else:
                logger.error("Dhan square-off failed", remarks=resp.get("remarks"))
                return None
        except Exception as e:
            logger.critical("Exception during live square-off order", error=str(e))
            return None

