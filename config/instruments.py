from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str
    underlying_name: str
    lot_size: int
    strike_interval: int
    tick_size: float = 0.05
    exchange_segment: str = "NSE_FNO"


SUPPORTED_INSTRUMENTS: Dict[str, InstrumentConfig] = {
    "NIFTY": InstrumentConfig(
        symbol="NIFTY",
        underlying_name="NIFTY 50",
        lot_size=25,  # NSE revised Nifty lot size
        strike_interval=50,
        tick_size=0.05,
        exchange_segment="NSE_FNO"
    ),
    "BANKNIFTY": InstrumentConfig(
        symbol="BANKNIFTY",
        underlying_name="NIFTY BANK",
        lot_size=15,  # NSE Bank Nifty lot size
        strike_interval=100,
        tick_size=0.05,
        exchange_segment="NSE_FNO"
    )
}


def get_instrument_config(symbol: str) -> InstrumentConfig:
    key = symbol.upper()
    if key not in SUPPORTED_INSTRUMENTS:
        raise ValueError(f"Instrument {symbol} is not supported. Supported: {list(SUPPORTED_INSTRUMENTS.keys())}")
    return SUPPORTED_INSTRUMENTS[key]

