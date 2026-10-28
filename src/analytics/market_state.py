from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from src.core.events import Event


@dataclass(frozen=True)
class MarketState(Event):
    """Immutable, strongly-typed quantitative representation of an instrument's current state."""

    symbol: str = ""
    timeframe: str = "1m"
    close: float = 0.0

    # Volatility
    atr: float = 0.0
    normalized_atr_pct: float = 0.0  # ATR as % of price

    # Trend & Directional Movement
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    is_trending: bool = False
    trend_bias: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL

    # Benchmark & Institutional Order Flow
    vwap: float = 0.0
    vwap_upper_band: float = 0.0
    vwap_lower_band: float = 0.0
    price_vs_vwap: str = "AT"  # ABOVE, BELOW, AT

    # Momentum
    rsi: float = 50.0
    rsi_state: str = "NEUTRAL"  # OVERBOUGHT (>70), OVERSOLD (<30), BULLISH_ZONE (50-70), BEARISH_ZONE (30-50)

    # Moving Averages
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    ema_alignment: str = "MIXED"  # BULLISH (9 > 21 > 50), BEARISH (9 < 21 < 50), MIXED

    # Volume & Liquidity
    current_volume: int = 0
    volume_ratio_20: float = 1.0  # Volume / 20-bar avg volume

    # Candle Structure
    body_ratio: float = 0.0
    consecutive_direction_bars: int = 0  # +N for consecutive green bars, -N for red bars

    candle_time: Optional[datetime] = None

