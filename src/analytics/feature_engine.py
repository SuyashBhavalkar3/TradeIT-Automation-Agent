from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from src.analytics.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_candle_metrics,
    calculate_ema,
    calculate_rsi,
    calculate_vwap
)
from src.analytics.market_state import MarketState
from src.core.events import CandleEvent, EventBus
from src.core.logging import get_logger

logger = get_logger("feature_engine")


class FeatureEngine:
    """Consumes closed candles and updates quantitative market features and state."""

    def __init__(self, event_bus: EventBus, max_history_bars: int = 200):
        self.event_bus = event_bus
        self.max_history_bars = max_history_bars
        # Key: (symbol, timeframe) -> List of Candle records
        self._candle_history: Dict[tuple, List[dict]] = defaultdict(list)
        # Key: (symbol, timeframe) -> latest MarketState
        self._latest_states: Dict[tuple, MarketState] = {}

    async def on_candle(self, candle: CandleEvent):
        # We process feature updates whenever a candle closes
        if not candle.is_closed:
            return

        key = (candle.symbol, candle.timeframe)
        history = self._candle_history[key]

        history.append({
            "timestamp": candle.candle_start,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": max(1, candle.volume)
        })

        if len(history) > self.max_history_bars:
            self._candle_history[key] = history[-self.max_history_bars:]

        df = pd.DataFrame(self._candle_history[key])
        if len(df) < 5:
            # Not enough data for meaningful indicator calculation
            return

        state = self._compute_market_state(candle.symbol, candle.timeframe, df)
        self._latest_states[key] = state

        logger.debug(
            "Market state updated",
            symbol=state.symbol,
            tf=state.timeframe,
            close=state.close,
            adx=round(state.adx, 1),
            rsi=round(state.rsi, 1),
            trend=state.trend_bias,
            ema_align=state.ema_alignment
        )

        await self.event_bus.publish(state)

    def _compute_market_state(self, symbol: str, timeframe: str, df: pd.DataFrame) -> MarketState:
        open_s = df["open"]
        high_s = df["high"]
        low_s = df["low"]
        close_s = df["close"]
        vol_s = df["volume"]

        # Calculate indicators
        period = min(14, len(df) - 1)
        atr_s, norm_atr_s = calculate_atr(high_s, low_s, close_s, period=period)
        adx_s, pdi_s, mdi_s = calculate_adx(high_s, low_s, close_s, period=period)
        rsi_s = calculate_rsi(close_s, period=period)
        vwap_s, vwap_up_s, vwap_dn_s = calculate_vwap(high_s, low_s, close_s, vol_s)

        ema9 = calculate_ema(close_s, min(9, len(df))).iloc[-1]
        ema21 = calculate_ema(close_s, min(21, len(df))).iloc[-1]
        ema50 = calculate_ema(close_s, min(50, len(df))).iloc[-1]

        last_close = float(close_s.iloc[-1])
        last_atr = float(atr_s.iloc[-1])
        last_norm_atr = float(norm_atr_s.iloc[-1])
        last_adx = float(adx_s.iloc[-1])
        last_pdi = float(pdi_s.iloc[-1])
        last_mdi = float(mdi_s.iloc[-1])
        last_rsi = float(rsi_s.iloc[-1])
        last_vwap = float(vwap_s.iloc[-1])
        last_vwap_up = float(vwap_up_s.iloc[-1])
        last_vwap_dn = float(vwap_dn_s.iloc[-1])

        # Trend Bias & Strength
        is_trending = last_adx >= 25.0
        if last_pdi > last_mdi and (last_pdi - last_mdi) > 5.0:
            trend_bias = "BULLISH"
        elif last_mdi > last_pdi and (last_mdi - last_pdi) > 5.0:
            trend_bias = "BEARISH"
        else:
            trend_bias = "NEUTRAL"

        # Price vs VWAP
        if last_close > last_vwap * 1.0005:
            price_vs_vwap = "ABOVE"
        elif last_close < last_vwap * 0.9995:
            price_vs_vwap = "BELOW"
        else:
            price_vs_vwap = "AT"

        # RSI Classification
        if last_rsi >= 70.0:
            rsi_state = "OVERBOUGHT"
        elif last_rsi <= 30.0:
            rsi_state = "OVERSOLD"
        elif last_rsi >= 50.0:
            rsi_state = "BULLISH_ZONE"
        else:
            rsi_state = "BEARISH_ZONE"

        # EMA Alignment
        if ema9 > ema21 > ema50:
            ema_alignment = "BULLISH"
        elif ema9 < ema21 < ema50:
            ema_alignment = "BEARISH"
        else:
            ema_alignment = "MIXED"

        # Volume ratio vs 20-period moving average
        vol_ma20 = vol_s.rolling(window=min(20, len(vol_s))).mean().iloc[-1]
        last_vol = int(vol_s.iloc[-1])
        vol_ratio = round(last_vol / max(1.0, vol_ma20), 2)

        # Candle structure
        metrics = calculate_candle_metrics(open_s, high_s, low_s, close_s)
        last_body_ratio = round(float(metrics["body_ratio"].iloc[-1]), 2)

        # Consecutive bars in direction
        bullish_series = metrics["is_bullish"].values
        consecutive = 0
        last_dir = bullish_series[-1]
        for b in reversed(bullish_series):
            if b == last_dir:
                consecutive += 1
            else:
                break
        consecutive_bars = consecutive if last_dir else -consecutive

        return MarketState(
            symbol=symbol,
            timeframe=timeframe,
            close=round(last_close, 2),
            atr=round(last_atr, 2),
            normalized_atr_pct=round(last_norm_atr, 3),
            adx=round(last_adx, 2),
            plus_di=round(last_pdi, 2),
            minus_di=round(last_mdi, 2),
            is_trending=is_trending,
            trend_bias=trend_bias,
            vwap=round(last_vwap, 2),
            vwap_upper_band=round(last_vwap_up, 2),
            vwap_lower_band=round(last_vwap_dn, 2),
            price_vs_vwap=price_vs_vwap,
            rsi=round(last_rsi, 2),
            rsi_state=rsi_state,
            ema_9=round(ema9, 2),
            ema_21=round(ema21, 2),
            ema_50=round(ema50, 2),
            ema_alignment=ema_alignment,
            current_volume=last_vol,
            volume_ratio_20=vol_ratio,
            body_ratio=last_body_ratio,
            consecutive_direction_bars=consecutive_bars,
            candle_time=df["timestamp"].iloc[-1]
        )

    def get_latest_market_state(self, symbol: str, timeframe: str = "1m") -> Optional[MarketState]:
        return self._latest_states.get((symbol, timeframe))

    def get_history(self, symbol: str, timeframe: str = "1m") -> pd.DataFrame:
        history = self._candle_history.get((symbol, timeframe), [])
        return pd.DataFrame(history)

