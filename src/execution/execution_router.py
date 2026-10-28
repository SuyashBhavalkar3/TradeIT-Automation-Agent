from typing import Dict, List, Optional
from config.settings import Settings, TradingMode
from src.core.logging import get_logger
from src.execution.dhan_gateway import DhanOrderGateway
from src.execution.order_model import Order, Position, TradeRecord
from src.execution.paper_engine import PaperExecutionEngine
from src.risk.risk_manager import RiskApproval

logger = get_logger("execution_router")


class ExecutionRouter:
    """
    Unified Execution Router.
    Directs trade execution to either Paper Engine or Live Dhan Broker Gateway based on TRADING_MODE in .env.
    Guarantees seamless, single-switch transition between simulated and real-money execution.
    """

    def __init__(
        self,
        settings: Settings,
        paper_engine: PaperExecutionEngine,
        dhan_gateway: DhanOrderGateway
    ):
        self.settings = settings
        self.paper_engine = paper_engine
        self.dhan_gateway = dhan_gateway

    @property
    def mode(self) -> TradingMode:
        return self.settings.TRADING_MODE

    @property
    def is_live(self) -> bool:
        return self.settings.TRADING_MODE == TradingMode.LIVE

    async def execute_approved_proposal(
        self,
        approval: RiskApproval,
        security_id: Optional[str] = None
    ) -> Optional[Order]:
        """Routes execution based strictly on TRADING_MODE configuration."""
        if not approval.is_approved:
            logger.warning("Rejected attempt to execute unapproved proposal", symbol=approval.proposal.symbol)
            return None

        if self.is_live:
            logger.critical("ROUTING EXECUTION TO LIVE DHAN BROKER", symbol=approval.proposal.symbol, qty=approval.approved_quantity)
            sec_id = security_id or "0"
            return self.dhan_gateway.execute_live_order(approval, security_id=sec_id)
        else:
            logger.info("ROUTING EXECUTION TO VIRTUAL PAPER ENGINE", symbol=approval.proposal.symbol, qty=approval.approved_quantity)
            return await self.paper_engine.execute_approved_proposal(approval)

    async def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        security_id: Optional[str] = None,
        quantity: Optional[int] = None
    ) -> Optional[TradeRecord]:
        """Routes position closing / square-off."""
        if self.is_live:
            logger.critical("ROUTING SQUARE-OFF TO LIVE DHAN BROKER", symbol=symbol)
            if security_id and quantity:
                self.dhan_gateway.close_live_position(security_id=security_id, symbol=symbol, quantity=quantity)
            return None
        else:
            return await self.paper_engine.close_position(symbol=symbol, exit_price=exit_price, exit_reason=exit_reason)

    def get_open_positions(self) -> Dict[str, Position]:
        if self.is_live:
            # Query positions from Dhan REST
            try:
                positions_resp = self.dhan_gateway._get_client().get_positions()
                # Return empty dict if no positions or parse data
                return {}
            except Exception as e:
                logger.error("Error fetching live Dhan positions", error=str(e))
                return {}
        else:
            return self.paper_engine.open_positions

    def get_portfolio_summary(self) -> dict:
        summary = self.paper_engine.get_portfolio_summary()
        summary["trading_mode"] = self.mode.value
        summary["is_live"] = self.is_live
        return summary
