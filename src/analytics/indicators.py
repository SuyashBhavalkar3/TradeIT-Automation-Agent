from typing import Tuple
import numpy as np
import pandas as pd


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates Average True Range (ATR) and Normalized ATR (% of close).
    
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Wilder's Smoothing for ATR
    atr = true_range.ewm(alpha=1.0 / period, adjust=False).mean()
    normalized_atr_pct = (atr / close) * 100.0

    return atr, normalized_atr_pct


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates Average Directional Index (ADX), +DI, and -DI.
    
    ADX > 25 indicates a strong trend.
    ADX < 20 indicates a choppy / sideways market.
    """
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing
    atr_smooth = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di_smooth = pd.Series(plus_dm, index=high.index).ewm(alpha=1.0 / period, adjust=False).mean()
    minus_di_smooth = pd.Series(minus_dm, index=high.index).ewm(alpha=1.0 / period, adjust=False).mean()

    # Avoid zero division
    atr_safe = atr_smooth.replace(0, np.nan)
    plus_di = (plus_di_smooth / atr_safe) * 100.0
    minus_di = (minus_di_smooth / atr_safe) * 100.0

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / di_sum) * 100.0
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean().fillna(0.0)

    return adx, plus_di.fillna(0.0), minus_di.fillna(0.0)


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Wilder's Relative Strength Index (RSI)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    # Calculate RS
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Handle edges where loss is zero
    rsi = rsi.fillna(100.0)
    return rsi


def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates Volume Weighted Average Price (VWAP) and standard deviation bands (1 sigma).
    
    Typical Price = (High + Low + Close) / 3
    VWAP = cumsum(Typical Price * Volume) / cumsum(Volume)
    """
    typical_price = (high + low + close) / 3.0
    cum_vol = volume.cumsum().replace(0, np.nan)
    cum_vol_price = (typical_price * volume).cumsum()

    vwap = cum_vol_price / cum_vol

    # Rolling variance of typical price relative to VWAP
    variance = ((typical_price - vwap) ** 2 * volume).cumsum() / cum_vol
    std_dev = np.sqrt(variance.clip(lower=0.0))

    upper_band = vwap + std_dev
    lower_band = vwap - std_dev

    return vwap.ffill(), upper_band.ffill(), lower_band.ffill()


def calculate_candle_metrics(
    open_p: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series
) -> pd.DataFrame:
    """
    Computes candle structural properties:
    - body_ratio: ratio of real body to total range [0.0 - 1.0]
    - upper_wick_ratio: upper wick / total range
    - lower_wick_ratio: lower wick / total range
    - is_bullish: True if close >= open
    """
    total_range = (high - low).replace(0, np.nan)
    body = (close - open_p).abs()
    is_bullish = close >= open_p

    upper_wick = np.where(is_bullish, high - close, high - open_p)
    lower_wick = np.where(is_bullish, open_p - low, close - low)

    body_ratio = (body / total_range).fillna(0.0)
    upper_wick_ratio = (pd.Series(upper_wick, index=high.index) / total_range).fillna(0.0)
    lower_wick_ratio = (pd.Series(lower_wick, index=high.index) / total_range).fillna(0.0)

    return pd.DataFrame({
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "is_bullish": is_bullish
    })

