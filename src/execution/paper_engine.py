import asyncio
from datetime import datetime, time
from typing import Dict, List, Optional
import uuid
from src.core.events import EventBus, TickEvent
from src.core.logging import get_logger
from src.execution.cost_model import IndianFOCostModel
from src.execution.order_model import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradeRecord
)
from src.risk.risk_manager import RiskApproval, RiskManager

logger = get_logger("paper_engine")


class PaperExecutionEngine:
    """
    Virtual Broker Execution Gateway for high-fidelity paper trading.
    Simulates realistic fills, slippage, statutory transaction costs, and live position lifecycle.
    """

    def __init__(
        self,
        event_bus: EventBus,
        risk_manager: RiskManager,
        initial_capital: float = 100000.0,
        slippage_pct: float = 0.001  # 0.1% dynamic slippage
    ):
        self.event_bus = event_bus
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.slippage_pct = slippage_pct

        # Active state
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._closed_trades: List[TradeRecord] = []
        self._last_tick_prices: Dict[str, float] = {}

    @property
    def open_positions(self) -> Dict[str, Position]:
        return self._positions

    @property
    def closed_trades(self) -> List[TradeRecord]:
        return self._closed_trades

    def get_portfolio_summary(self) -> dict:
        total_unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        total_realized = sum(t.net_pnl for t in self._closed_trades)
        current_positions_value = sum(p.current_market_price * p.quantity for p in self._positions.values())
        total_equity = round(self.available_cash + current_positions_value, 2)
        margin_used = sum(p.average_entry_price * p.quantity for p in self._positions.values())

        return {
            "initial_capital": self.initial_capital,
            "available_cash": round(self.available_cash, 2),
            "margin_used": round(margin_used, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "realized_pnl": round(total_realized, 2),
            "total_equity": total_equity,
            "open_positions_count": len(self._positions),
            "total_trades_count": len(self._closed_trades)
        }

    async def on_tick(self, tick: TickEvent):
        """Processes incoming market ticks, updates open position mark-to-market, and monitors SL/Target."""
        symbol = tick.symbol or tick.security_id
        if not symbol or tick.ltp <= 0:
            return

        self._last_tick_prices[symbol] = tick.ltp

        position = self._positions.get(symbol)
        if not position:
            return

        # 1. Update mark-to-market P&L
        position.update_price(tick.ltp)

        # 2. Check Target Execution
        if tick.ltp >= position.target_price:
            logger.info("Target achieved! Closing position", symbol=symbol, ltp=tick.ltp, target=position.target_price)
            await self.close_position(symbol, exit_price=tick.bid_price or tick.ltp, exit_reason="TARGET_ACHIEVED")
            return

        # 3. Check Stop-Loss Execution
        if tick.ltp <= position.stop_loss_price:
            logger.warning("Stop-loss triggered! Closing position", symbol=symbol, ltp=tick.ltp, sl=position.stop_loss_price)
            await self.close_position(symbol, exit_price=tick.bid_price or tick.ltp, exit_reason="STOP_LOSS_TRIGGERED")
            return

        # 4. Intraday auto square-off cutoff (15:15 IST)
        now_time = tick.timestamp.time() if tick.timestamp else datetime.now().time()
        if now_time >= time(15, 15, 0):
            logger.info("Intraday time cutoff reached. Auto square-off", symbol=symbol)
            await self.close_position(symbol, exit_price=tick.bid_price or tick.ltp, exit_reason="TIME_CUTOFF")

    async def execute_approved_proposal(self, approval: RiskApproval) -> Optional[Order]:
        """Submits a virtual buy order for an approved strategy proposal."""
        if not approval.is_approved or approval.approved_quantity <= 0:
            return None

        proposal = approval.proposal
        symbol = proposal.symbol
        quantity = approval.approved_quantity
        req_price = proposal.expected_entry_price

        # Check if already in position
        if symbol in self._positions:
            logger.warning("Already holding position in symbol; rejecting duplicate buy", symbol=symbol)
            return None

        # Apply realistic slippage on buy side
        dynamic_slippage = max(0.05, round(req_price * self.slippage_pct, 2))
        fill_price = round(req_price + dynamic_slippage, 2)
        capital_required = round(fill_price * quantity, 2)

        if capital_required > self.available_cash:
            logger.warning("Insufficient virtual cash for order", required=capital_required, available=self.available_cash)
            return None

        order_id = f"ORD_{uuid.uuid4().hex[:8].upper()}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
            requested_price=req_price,
            status=OrderStatus.FILLED,
            filled_price=fill_price,
            filled_quantity=quantity,
            slippage=dynamic_slippage,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        self._orders[order_id] = order

        # Deduct cash
        self.available_cash -= capital_required

        # Create active position
        self._positions[symbol] = Position(
            symbol=symbol,
            underlying=proposal.underlying_symbol,
            option_type=proposal.option_type,
            quantity=quantity,
            average_entry_price=fill_price,
            current_market_price=fill_price,
            stop_loss_price=proposal.stop_loss_price,
            target_price=proposal.target_price,
            entry_time=datetime.now(),
            strategy_name=proposal.strategy_name
        )

        self.risk_manager.set_open_positions_count(len(self._positions))

        logger.info(
            "Paper Order FILLED",
            order_id=order_id,
            symbol=symbol,
            quantity=quantity,
            fill_price=fill_price,
            sl=proposal.stop_loss_price,
            target=proposal.target_price
        )

        return order

    async def close_position(self, symbol: str, exit_price: float, exit_reason: str) -> Optional[TradeRecord]:
        position = self._positions.pop(symbol, None)
        if not position:
            return None

        # Apply realistic slippage on sell side
        dynamic_slippage = max(0.05, round(exit_price * self.slippage_pct, 2))
        fill_exit_price = max(0.05, round(exit_price - dynamic_slippage, 2))

        # Calculate gross and net P&L
        quantity = position.quantity
        gross_pnl = round((fill_exit_price - position.average_entry_price) * quantity, 2)

        costs = IndianFOCostModel.calculate_option_trade_costs(
            buy_price=position.average_entry_price,
            sell_price=fill_exit_price,
            quantity=quantity
        )

        net_pnl = round(gross_pnl - costs.total_costs, 2)
        capital_returned = round(fill_exit_price * quantity, 2)

        # Restore virtual cash
        self.available_cash += capital_returned

        # Return % on deployed capital
        deployed = position.average_entry_price * quantity
        return_pct = round((net_pnl / max(1.0, deployed)) * 100.0, 2)

        trade = TradeRecord(
            trade_id=f"TRD_{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol,
            underlying=position.underlying,
            option_type=position.option_type,
            quantity=quantity,
            entry_price=position.average_entry_price,
            exit_price=fill_exit_price,
            entry_time=position.entry_time,
            exit_time=datetime.now(),
            gross_pnl=gross_pnl,
            statutory_costs=costs.total_costs,
            net_pnl=net_pnl,
            return_pct=return_pct,
            exit_reason=exit_reason,
            strategy_name=position.strategy_name,
            market_regime="LIVE_PAPER"
        )

        self._closed_trades.append(trade)

        # Update Risk Manager metrics
        self.risk_manager.set_open_positions_count(len(self._positions))
        self.risk_manager.record_closed_trade_pnl(net_pnl)

        logger.info(
            "Paper Position CLOSED",
            symbol=symbol,
            entry=position.average_entry_price,
            exit=fill_exit_price,
            gross_pnl=gross_pnl,
            taxes=costs.total_costs,
            net_pnl=net_pnl,
            reason=exit_reason
        )

        return trade

    async def close_all_positions(self, exit_reason: str = "PANIC_SQUARE_OFF") -> List[TradeRecord]:
        """Emergency square off all open positions immediately."""
        symbols = list(self._positions.keys())
        closed = []
        for sym in symbols:
            pos = self._positions.get(sym)
            if pos:
                exit_price = pos.current_market_price
                record = await self.close_position(sym, exit_price=exit_price, exit_reason=exit_reason)
                if record:
                    closed.append(record)
        return closed


