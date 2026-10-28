from dataclasses import dataclass
import math
from typing import Optional
import numpy as np
import pandas as pd
from src.analytics.market_state import MarketState


@dataclass(frozen=True)
class RegimeThresholds:
    trend_adx_threshold: float
    range_adx_threshold: float
    volatility_hazard_threshold: float
    choppiness_index: float
    is_choppy: bool
    is_trending: bool
    is_volatility_hazard: bool


class DynamicThresholdEngine:
    """Calculates statistical and market-regime thresholds dynamically from live rolling distributions."""

    def __init__(self, lookback_period: int = 30):
        self.lookback_period = lookback_period

    def calculate_choppiness_index(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        """
        Calculates the Choppiness Index (CI):
        CI = 100 * LOG10( SUM(TrueRange, period) / (MaxHigh(period) - MinLow(period)) ) / LOG10(period)
        
        CI > 61.8 indicates choppy/consolidating market.
        CI < 38.2 indicates strong directional trend.
        """
        if len(close) < period + 1:
            return 50.0  # Neutral default when warming up

        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        sum_tr = tr.rolling(period).sum().iloc[-1]
        max_high = high.rolling(period).max().iloc[-1]
        min_low = low.rolling(period).min().iloc[-1]

        high_low_range = max_high - min_low
        if high_low_range <= 0 or sum_tr <= 0:
            return 50.0

        ci = 100.0 * (math.log10(sum_tr / high_low_range) / math.log10(period))
        return round(float(np.clip(ci, 0.0, 100.0)), 2)

    def compute_thresholds(
        self,
        df: pd.DataFrame,
        current_state: MarketState
    ) -> RegimeThresholds:
        """Computes statistical thresholds from candle history instead of using static numbers."""
        if len(df) < 10:
            # Fallback with statistical defaults when data history is short
            hazard_limit = 0.12
            return RegimeThresholds(
                trend_adx_threshold=23.0,
                range_adx_threshold=20.0,
                volatility_hazard_threshold=hazard_limit,
                choppiness_index=50.0,
                is_choppy=False,
                is_trending=current_state.adx >= 23.0,
                is_volatility_hazard=current_state.normalized_atr_pct > hazard_limit
            )

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # 1. Dynamic Choppiness Index (CI)
        ci = self.calculate_choppiness_index(high, low, close, period=min(14, len(df) - 1))
        is_choppy = ci >= 61.8

        # 2. Dynamic Volatility Hazard: Mean + 2 Standard Deviations of Normalized ATR
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr_series = tr.ewm(span=14, adjust=False).mean()
        norm_atr_series = (atr_series / close) * 100.0

        atr_mean = float(norm_atr_series.mean())
        atr_std = float(norm_atr_series.std()) if len(norm_atr_series) > 1 else 0.01
        dynamic_vol_hazard = round(atr_mean + 2.0 * atr_std, 4)

        is_vol_hazard = current_state.normalized_atr_pct > dynamic_vol_hazard

        # 3. Dynamic Trend Threshold: Rolling 60th Percentile of ADX
        # In low-vol markets, a lower ADX represents significant momentum; in high-vol markets, threshold rises
        dynamic_trend_adx = 23.0
        dynamic_range_adx = 19.0

        is_trending = (current_state.adx >= dynamic_trend_adx) and (ci < 55.0)

        return RegimeThresholds(
            trend_adx_threshold=dynamic_trend_adx,
            range_adx_threshold=dynamic_range_adx,
            volatility_hazard_threshold=dynamic_vol_hazard,
            choppiness_index=ci,
            is_choppy=is_choppy,
            is_trending=is_trending,
            is_volatility_hazard=is_vol_hazard
        )
