from datetime import datetime, timedelta
import pytest
from src.analytics.options_pricing import BlackScholesEngine


def test_black_scholes_call_delta_bounds():
    # Spot 22700, Strike 22700, 3 days to expiry, 16% VIX
    expiry = datetime.now() + timedelta(days=3)
    t = BlackScholesEngine.calculate_time_to_expiry_years(expiry)

    greeks = BlackScholesEngine.calculate(
        spot=22700.0,
        strike=22700.0,
        time_to_expiry_years=t,
        volatility_annual=0.16,
        risk_free_rate=0.065,
        option_type="CE"
    )

    assert 0.40 <= greeks.delta <= 0.60  # ATM Call delta ~ 0.50
    assert greeks.theoretical_price > 0
    assert greeks.theta < 0              # Theta decay is negative for long buyers
    assert greeks.gamma > 0
    assert greeks.vega > 0
    assert greeks.ask > greeks.bid


def test_black_scholes_put_delta_bounds():
    expiry = datetime.now() + timedelta(days=3)
    t = BlackScholesEngine.calculate_time_to_expiry_years(expiry)

    greeks = BlackScholesEngine.calculate(
        spot=22700.0,
        strike=22700.0,
        time_to_expiry_years=t,
        volatility_annual=0.16,
        risk_free_rate=0.065,
        option_type="PE"
    )

    assert -0.60 <= greeks.delta <= -0.40  # ATM Put delta ~ -0.50
    assert greeks.theoretical_price > 0
    assert greeks.theta < 0


def test_volatility_sensitivity():
    expiry = datetime.now() + timedelta(days=5)
    t = BlackScholesEngine.calculate_time_to_expiry_years(expiry)

    # Low vol (12% VIX) vs High vol (24% VIX)
    low_vol = BlackScholesEngine.calculate(22700.0, 22700.0, t, 0.12, option_type="CE")
    high_vol = BlackScholesEngine.calculate(22700.0, 22700.0, t, 0.24, option_type="CE")

    # Higher volatility must dynamically produce higher option prices
    assert high_vol.theoretical_price > low_vol.theoretical_price
