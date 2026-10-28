from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd
from src.analytics.market_state import MarketState
from src.core.logging import get_logger
from src.market_data.data_monitor import DataQualityMonitor
from src.regime.dynamic_thresholds import DynamicThresholdEngine

logger = get_logger("regime_classifier")


class MarketRegime(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    CHOPPY = "CHOPPY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    ABNORMAL_DATA = "ABNORMAL_DATA"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeClassification:
    symbol: str
    timeframe: str
    regime: MarketRegime
    confidence: float  # [0.0 - 1.0]
    primary_reason: str
    details: dict


class MarketRegimeClassifier:
    """Classifies the market environment dynamically using live statistical distributions."""

    def __init__(
        self,
        data_monitor: Optional[DataQualityMonitor] = None,
        threshold_engine: Optional[DynamicThresholdEngine] = None
    ):
        self.data_monitor = data_monitor
        self.threshold_engine = threshold_engine or DynamicThresholdEngine()

    def classify(self, state: MarketState, history_df: Optional[pd.DataFrame] = None) -> RegimeClassification:
        # Check 1: Data feed sanity & freshness
        if self.data_monitor and not self.data_monitor.is_healthy:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.ABNORMAL_DATA,
                confidence=1.0,
                primary_reason="Data feed is stale or reporting anomalies",
                details={"feed_state": self.data_monitor.feed_state.value}
            )

        # Calculate dynamic statistical thresholds from live data distribution
        df = history_df if history_df is not None else pd.DataFrame()
        thresholds = self.threshold_engine.compute_thresholds(df, state)

        # Check 2: Dynamic High Volatility Hazard Filter (> 2 std devs above mean)
        if thresholds.is_volatility_hazard or state.normalized_atr_pct > thresholds.volatility_hazard_threshold:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.HIGH_VOLATILITY,
                confidence=0.95,
                primary_reason=f"Dynamic volatility hazard: ATR is {state.normalized_atr_pct:.3f}% (dynamic threshold: {thresholds.volatility_hazard_threshold:.3f}%)",
                details={"atr": state.atr, "norm_atr_pct": state.normalized_atr_pct, "dynamic_hazard": thresholds.volatility_hazard_threshold}
            )

        # Check 3: Dynamic Choppiness Index (CI >= 61.8 Fibonacci bound) or low body ratio
        if thresholds.is_choppy or (state.body_ratio < 0.20 and state.adx < thresholds.trend_adx_threshold):
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.CHOPPY,
                confidence=0.88,
                primary_reason=f"Choppy market: Choppiness Index is {thresholds.choppiness_index:.1f} (>= 61.8 boundary) or low body ratio ({state.body_ratio:.2f})",
                details={"choppiness_index": thresholds.choppiness_index, "body_ratio": state.body_ratio, "adx": state.adx}
            )

        # Check 4: Trending Bullish
        is_bullish_trend = (
            state.adx >= thresholds.trend_adx_threshold
            and state.plus_di > state.minus_di
            and state.price_vs_vwap in ["ABOVE", "AT"]
            and state.ema_alignment in ["BULLISH", "MIXED"]
            and state.rsi > 48.0
        )
        if is_bullish_trend:
            confidence = min(1.0, 0.6 + (state.adx - thresholds.trend_adx_threshold) * 0.02 + (0.1 if state.ema_alignment == "BULLISH" else 0.0))
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.TRENDING_BULLISH,
                confidence=round(confidence, 2),
                primary_reason=f"Sustained bullish trend: ADX >= {thresholds.trend_adx_threshold:.1f}, +DI > -DI, Price >= VWAP",
                details={
                    "adx": state.adx,
                    "plus_di": state.plus_di,
                    "minus_di": state.minus_di,
                    "ema_alignment": state.ema_alignment,
                    "price_vs_vwap": state.price_vs_vwap,
                    "choppiness_index": thresholds.choppiness_index
                }
            )

        # Check 5: Trending Bearish
        is_bearish_trend = (
            state.adx >= thresholds.trend_adx_threshold
            and state.minus_di > state.plus_di
            and state.price_vs_vwap in ["BELOW", "AT"]
            and state.ema_alignment in ["BEARISH", "MIXED"]
            and state.rsi < 52.0
        )
        if is_bearish_trend:
            confidence = min(1.0, 0.6 + (state.adx - thresholds.trend_adx_threshold) * 0.02 + (0.1 if state.ema_alignment == "BEARISH" else 0.0))
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.TRENDING_BEARISH,
                confidence=round(confidence, 2),
                primary_reason=f"Sustained bearish trend: ADX >= {thresholds.trend_adx_threshold:.1f}, -DI > +DI, Price <= VWAP",
                details={
                    "adx": state.adx,
                    "plus_di": state.plus_di,
                    "minus_di": state.minus_di,
                    "ema_alignment": state.ema_alignment,
                    "price_vs_vwap": state.price_vs_vwap,
                    "choppiness_index": thresholds.choppiness_index
                }
            )

        # Check 6: Sideways / Ranging
        if state.adx < thresholds.range_adx_threshold:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.RANGING,
                confidence=0.80,
                primary_reason=f"Sideways range: ADX ({state.adx:.1f}) is below dynamic range threshold ({thresholds.range_adx_threshold:.1f})",
                details={"adx": state.adx, "rsi": state.rsi, "choppiness_index": thresholds.choppiness_index}
            )

        # Default fallback
        return RegimeClassification(
            symbol=state.symbol,
            timeframe=state.timeframe,
            regime=MarketRegime.CHOPPY,
            confidence=0.60,
            primary_reason="Conflicting signals: Indicators do not satisfy clean trend or range criteria",
            details={"adx": state.adx, "ema_alignment": state.ema_alignment, "choppiness_index": thresholds.choppiness_index}
        )

