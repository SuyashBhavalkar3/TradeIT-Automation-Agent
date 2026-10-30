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
        self.paper_engine.on_close_position_callback = self._on_engine_close_position

    def _on_engine_close_position(self, symbol: str, position: Position):
        if self.is_live:
            sec_id = getattr(position, "security_id", None) or "0"
            if sec_id and sec_id != "0":
                logger.critical("Submitting live square-off order to Dhan", symbol=symbol, sec_id=sec_id, qty=position.quantity)
                self.dhan_gateway.close_live_position(security_id=sec_id, symbol=symbol, quantity=position.quantity)

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

        sec_id = security_id or "0"

        if self.is_live:
            logger.critical("ROUTING EXECUTION TO LIVE DHAN BROKER", symbol=approval.proposal.symbol, qty=approval.approved_quantity)
            order = self.dhan_gateway.execute_live_order(approval, security_id=sec_id)
            if order and order.status in [OrderStatus.FILLED, OrderStatus.SUBMITTED]:
                # Track position locally for sub-second MTM calculation & automatic SL/TP monitoring
                pos = Position(
                    symbol=order.symbol,
                    direction=approval.proposal.direction.value,
                    quantity=order.quantity,
                    entry_price=order.filled_price,
                    stop_loss_price=approval.proposal.stop_loss,
                    target_price=approval.proposal.target,
                    strategy_name=approval.proposal.strategy_name
                )
                setattr(pos, "security_id", sec_id)
                self.paper_engine._positions[order.symbol] = pos
            return order
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
        pos = self.paper_engine._positions.get(symbol)
        sec_id = security_id or getattr(pos, "security_id", None) or "0"
        qty = quantity or (pos.quantity if pos else None)

        if self.is_live:
            logger.critical("ROUTING SQUARE-OFF TO LIVE DHAN BROKER", symbol=symbol, sec_id=sec_id, qty=qty)
            if sec_id and sec_id != "0" and qty:
                self.dhan_gateway.close_live_position(security_id=sec_id, symbol=symbol, quantity=qty)
            return await self.paper_engine.close_position(symbol=symbol, exit_price=exit_price, exit_reason=exit_reason)
        else:
            return await self.paper_engine.close_position(symbol=symbol, exit_price=exit_price, exit_reason=exit_reason)

    def get_open_positions(self) -> Dict[str, Position]:
        return self.paper_engine.open_positions

    def get_portfolio_summary(self) -> dict:
        summary = self.paper_engine.get_portfolio_summary()
        summary["trading_mode"] = self.mode.value
        summary["is_live"] = self.is_live
        return summary

