from dataclasses import dataclass
from enum import Enum
from typing import Optional
from src.analytics.market_state import MarketState
from src.core.logging import get_logger
from src.market_data.data_monitor import DataQualityMonitor

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
    """Classifies the market environment to decide whether trading conditions are favorable."""

    def __init__(
        self,
        data_monitor: Optional[DataQualityMonitor] = None,
        adx_trend_threshold: float = 23.0,
        adx_range_threshold: float = 20.0,
        max_normalized_atr_pct: float = 0.12,  # >0.12% 1m ATR considered hazard for index
        min_body_ratio: float = 0.25           # Average candle real body vs wicks
    ):
        self.data_monitor = data_monitor
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold
        self.max_normalized_atr_pct = max_normalized_atr_pct
        self.min_body_ratio = min_body_ratio

    def classify(self, state: MarketState) -> RegimeClassification:
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

        # Check 2: High Volatility Hazard Filter
        if state.normalized_atr_pct > self.max_normalized_atr_pct:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.HIGH_VOLATILITY,
                confidence=0.95,
                primary_reason=f"Volatility hazard: Normalized ATR is {state.normalized_atr_pct:.3f}% (limit: {self.max_normalized_atr_pct}%)",
                details={"atr": state.atr, "norm_atr_pct": state.normalized_atr_pct}
            )

        # Check 3: Choppy / Indecisive Candle Structure
        # Small bodies with long wicks + low ADX or mixed EMAs indicate chop
        if state.body_ratio < self.min_body_ratio and state.adx < self.adx_trend_threshold:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.CHOPPY,
                confidence=0.85,
                primary_reason=f"Choppy price action: low body ratio ({state.body_ratio:.2f}) and weak trend (ADX {state.adx:.1f})",
                details={"body_ratio": state.body_ratio, "adx": state.adx}
            )

        # Check 4: Trending Bullish
        # ADX >= 23, +DI > -DI, Price above VWAP, EMA alignment bullish
        is_bullish_trend = (
            state.adx >= self.adx_trend_threshold
            and state.plus_di > state.minus_di
            and state.price_vs_vwap in ["ABOVE", "AT"]
            and state.ema_alignment in ["BULLISH", "MIXED"]
            and state.rsi > 48.0
        )
        if is_bullish_trend:
            confidence = min(1.0, 0.6 + (state.adx - self.adx_trend_threshold) * 0.02 + (0.1 if state.ema_alignment == "BULLISH" else 0.0))
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.TRENDING_BULLISH,
                confidence=round(confidence, 2),
                primary_reason="Sustained bullish trend: ADX >= 23, +DI > -DI, Price >= VWAP",
                details={
                    "adx": state.adx,
                    "plus_di": state.plus_di,
                    "minus_di": state.minus_di,
                    "ema_alignment": state.ema_alignment,
                    "price_vs_vwap": state.price_vs_vwap
                }
            )

        # Check 5: Trending Bearish
        # ADX >= 23, -DI > +DI, Price below VWAP, EMA alignment bearish
        is_bearish_trend = (
            state.adx >= self.adx_trend_threshold
            and state.minus_di > state.plus_di
            and state.price_vs_vwap in ["BELOW", "AT"]
            and state.ema_alignment in ["BEARISH", "MIXED"]
            and state.rsi < 52.0
        )
        if is_bearish_trend:
            confidence = min(1.0, 0.6 + (state.adx - self.adx_trend_threshold) * 0.02 + (0.1 if state.ema_alignment == "BEARISH" else 0.0))
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.TRENDING_BEARISH,
                confidence=round(confidence, 2),
                primary_reason="Sustained bearish trend: ADX >= 23, -DI > +DI, Price <= VWAP",
                details={
                    "adx": state.adx,
                    "plus_di": state.plus_di,
                    "minus_di": state.minus_di,
                    "ema_alignment": state.ema_alignment,
                    "price_vs_vwap": state.price_vs_vwap
                }
            )

        # Check 6: Sideways / Ranging
        if state.adx < self.adx_range_threshold:
            return RegimeClassification(
                symbol=state.symbol,
                timeframe=state.timeframe,
                regime=MarketRegime.RANGING,
                confidence=0.80,
                primary_reason=f"Sideways range: ADX ({state.adx:.1f}) is below range threshold ({self.adx_range_threshold:.1f})",
                details={"adx": state.adx, "rsi": state.rsi}
            )

        # Default fallback: Choppy / unclassified
        return RegimeClassification(
            symbol=state.symbol,
            timeframe=state.timeframe,
            regime=MarketRegime.CHOPPY,
            confidence=0.60,
            primary_reason="Conflicting signals: Indicators do not satisfy clean trend or clean range criteria",
            details={"adx": state.adx, "ema_alignment": state.ema_alignment, "trend_bias": state.trend_bias}
        )
