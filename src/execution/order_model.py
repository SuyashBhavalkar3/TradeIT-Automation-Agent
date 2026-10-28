from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    requested_price: float
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float = 0.0
    filled_quantity: int = 0
    slippage: float = 0.0
    fees: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    rejection_reason: Optional[str] = None


@dataclass
class Position:
    symbol: str
    underlying: str
    option_type: str
    quantity: int
    average_entry_price: float
    current_market_price: float
    stop_loss_price: float
    target_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    strategy_name: str = ""

    def update_price(self, ltp: float):
        self.current_market_price = ltp
        self.unrealized_pnl = round((self.current_market_price - self.average_entry_price) * self.quantity, 2)


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    underlying: str
    option_type: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    gross_pnl: float
    statutory_costs: float
    net_pnl: float
    return_pct: float
    exit_reason: str  # "TARGET_ACHIEVED", "STOP_LOSS_TRIGGERED", "TIME_CUTOFF", "MANUAL"
    strategy_name: str
    market_regime: str

