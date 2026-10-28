from dataclasses import dataclass
from datetime import datetime
import math
from typing import Optional


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function using math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


@dataclass(frozen=True)
class OptionGreeks:
    theoretical_price: float
    delta: float
    gamma: float
    theta: float       # 1-day theta decay in INR
    vega: float        # Price change per 1% change in IV
    intrinsic_value: float
    time_value: float
    bid: float
    ask: float


class BlackScholesEngine:
    """Calculates mathematical option pricing and Greeks dynamically without static estimates."""

    @staticmethod
    def calculate_time_to_expiry_years(expiry_dt: datetime, current_dt: Optional[datetime] = None) -> float:
        now = current_dt or datetime.now()
        diff_seconds = (expiry_dt - now).total_seconds()
        # Minimum 1 hour to prevent division by zero on expiry afternoon
        diff_seconds = max(3600.0, diff_seconds)
        return diff_seconds / (365.25 * 86400.0)

    @staticmethod
    def calculate(
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility_annual: float,       # e.g., 0.16 for 16% VIX
        risk_free_rate: float = 0.065,  # 6.5% RBI repo rate
        option_type: str = "CE",
        tick_size: float = 0.05
    ) -> OptionGreeks:
        S = max(0.01, spot)
        K = max(0.01, strike)
        T = max(0.0001, time_to_expiry_years)
        sigma = max(0.01, volatility_annual)
        r = risk_free_rate
        is_call = option_type.upper() == "CE"

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        # Standard normal distributions
        N_d1 = _norm_cdf(d1)
        N_d2 = _norm_cdf(d2)
        n_d1 = _norm_pdf(d1)

        # Discount factor
        exp_rT = math.exp(-r * T)

        if is_call:
            price = S * N_d1 - K * exp_rT * N_d2
            delta = N_d1
            intrinsic = max(0.0, S - K)
            # 1-day theta
            theta = (- (S * n_d1 * sigma) / (2 * sqrt_T) - r * K * exp_rT * N_d2) / 365.25
        else:
            N_neg_d1 = _norm_cdf(-d1)
            N_neg_d2 = _norm_cdf(-d2)
            price = K * exp_rT * N_neg_d2 - S * N_neg_d1
            delta = N_d1 - 1.0
            intrinsic = max(0.0, K - S)
            # 1-day theta
            theta = (- (S * n_d1 * sigma) / (2 * sqrt_T) + r * K * exp_rT * N_neg_d2) / 365.25

        gamma = n_d1 / (S * sigma * sqrt_T)
        vega = (S * sqrt_T * n_d1) / 100.0  # per 1% change in vol

        theo_price = max(tick_size, round(round(price / tick_size) * tick_size, 2))
        time_value = max(0.0, round(theo_price - intrinsic, 2))

        # Dynamic spread based on Delta and price liquidity
        spread_multiplier = 1 if theo_price > 50 else 2
        dynamic_spread = tick_size * spread_multiplier
        bid = max(tick_size, round(theo_price - (dynamic_spread / 2), 2))
        ask = round(theo_price + (dynamic_spread / 2), 2)

        return OptionGreeks(
            theoretical_price=theo_price,
            delta=round(delta, 3),
            gamma=round(gamma, 6),
            theta=round(theta, 2),
            vega=round(vega, 2),
            intrinsic_value=round(intrinsic, 2),
            time_value=time_value,
            bid=bid,
            ask=ask
        )
