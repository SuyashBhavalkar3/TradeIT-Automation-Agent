from datetime import datetime
from typing import Optional
from src.analytics.market_state import MarketState
from src.analytics.options_pricing import BlackScholesEngine
from src.core.logging import get_logger
from src.regime.permission_engine import TradePermissionDecision
from src.strategy.base_strategy import BaseStrategy, SignalDirection, TradeProposal

logger = get_logger("options_strategy")


class OptionsMomentumStrategy(BaseStrategy):
    """
    Intraday Trend Pullback Options Buying Strategy.
    All levels (strikes, stops, targets, risk/reward) are computed dynamically from market volatility.
    """

    def __init__(self, name: str = "DYNAMIC_OPTIONS_MOMENTUM"):
        super().__init__(name)

    def evaluate(
        self,
        state: MarketState,
        permission: TradePermissionDecision,
        current_option_price: float,
        india_vix: float = 16.0,
        pe_option_price: Optional[float] = None
    ) -> Optional[TradeProposal]:
        # Rule 1: Trade Permission Engine must explicitly permit trading
        if not permission.is_permitted:
            return None

        symbol = state.symbol.upper()
        spot = state.close
        atr = state.atr

        # Rule 2: Minimum ATR requirement (market must have sufficient price range)
        if atr <= 0:
            return None

        # Determine dynamic ATM strike
        strike_step = 100.0 if "BANK" in symbol else 50.0
        atm_strike = round(spot / strike_step) * strike_step

        # Dynamic R:R ratio based on trend strength (ADX)
        # Stronger trends justify holding for larger targets (1.6 to 2.5)
        dynamic_rr = round(min(2.5, 1.6 + max(0.0, state.adx - 25.0) * 0.04), 2)

        # --------------------------------------------------------------------
        # SETUP A: BULLISH PULLBACK (CALL BUYING)
        # --------------------------------------------------------------------
        if "CE" in permission.allowed_directions:
            # Entry condition:
            # 1. Price above VWAP
            # 2. EMA 9 >= EMA 21 (bullish alignment)
            # 3. Pullback check: current price within 0.15% of EMA 21 or EMA 9
            ema_distance_pct = abs(spot - state.ema_21) / spot * 100.0
            pullback_valid = ema_distance_pct <= 0.25 and spot >= state.vwap

            if pullback_valid and state.rsi >= 48.0:
                # Estimate option delta dynamically
                vol_annual = max(0.08, india_vix / 100.0)
                greeks = BlackScholesEngine.calculate(
                    spot=spot,
                    strike=atm_strike,
                    time_to_expiry_years=3.0 / 365.25,
                    volatility_annual=vol_annual,
                    option_type="CE"
                )
                delta = max(0.35, min(0.65, abs(greeks.delta)))

                # Dynamic Option Stop Distance based on underlying ATR and Delta
                # Underlying SL distance = 1.25 * ATR
                underlying_sl_distance = atr * 1.25
                option_sl_distance = max(4.0, round(underlying_sl_distance * delta, 2))

                # Setup A is CALL BUYING: uses CE option price
                entry_price = round(current_option_price, 2)
                stop_loss = max(1.0, round(entry_price - option_sl_distance, 2))
                target = round(entry_price + (option_sl_distance * dynamic_rr), 2)
                reward_points = round(target - entry_price, 2)

                return TradeProposal(
                    strategy_name=self.name,
                    symbol=f"{symbol}_{int(atm_strike)}_CE",
                    underlying_symbol=symbol,
                    direction=SignalDirection.BUY_CALL,
                    option_type="CE",
                    strike=atm_strike,
                    underlying_spot=spot,
                    expected_entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    target_price=target,
                    risk_points=option_sl_distance,
                    reward_points=reward_points,
                    risk_reward_ratio=dynamic_rr,
                    market_regime=permission.regime.value,
                    reasons=[
                        f"Bullish trend confirmed (ADX {state.adx:.1f})",
                        f"Clean pullback to EMA 21 ({state.ema_21:.2f}) above VWAP ({state.vwap:.2f})",
                        f"Dynamic Stop Loss: {option_sl_distance} pts (derived from ATR {atr:.2f} * Delta {delta:.2f})",
                        f"Dynamic Target: {reward_points} pts (Dynamic R:R 1:{dynamic_rr})"
                    ],
                    invalidation_conditions=[
                        "Underlying breaks and closes below VWAP",
                        "ADX drops below 20 (loss of momentum)",
                        "Option price breaches stop loss level"
                    ],
                    created_at=datetime.now()
                )

        # --------------------------------------------------------------------
        # SETUP B: BEARISH PULLBACK (PUT BUYING)
        # --------------------------------------------------------------------
        if "PE" in permission.allowed_directions:
            ema_distance_pct = abs(spot - state.ema_21) / spot * 100.0
            pullback_valid = ema_distance_pct <= 0.25 and spot <= state.vwap

            if pullback_valid and state.rsi <= 52.0:
                vol_annual = max(0.08, india_vix / 100.0)
                greeks = BlackScholesEngine.calculate(
                    spot=spot,
                    strike=atm_strike,
                    time_to_expiry_years=3.0 / 365.25,
                    volatility_annual=vol_annual,
                    option_type="PE"
                )
                delta = max(0.35, min(0.65, abs(greeks.delta)))

                underlying_sl_distance = atr * 1.25
                option_sl_distance = max(4.0, round(underlying_sl_distance * delta, 2))

                # Setup B is PUT BUYING: uses PE option price
                pe_price = pe_option_price if pe_option_price is not None and pe_option_price > 0 else current_option_price
                entry_price = round(pe_price, 2)
                stop_loss = max(1.0, round(entry_price - option_sl_distance, 2))
                target = round(entry_price + (option_sl_distance * dynamic_rr), 2)
                reward_points = round(target - entry_price, 2)

                return TradeProposal(
                    strategy_name=self.name,
                    symbol=f"{symbol}_{int(atm_strike)}_PE",
                    underlying_symbol=symbol,
                    direction=SignalDirection.BUY_PUT,
                    option_type="PE",
                    strike=atm_strike,
                    underlying_spot=spot,
                    expected_entry_price=entry_price,
                    stop_loss_price=stop_loss,
                    target_price=target,
                    risk_points=option_sl_distance,
                    reward_points=reward_points,
                    risk_reward_ratio=dynamic_rr,
                    market_regime=permission.regime.value,
                    reasons=[
                        f"Bearish trend confirmed (ADX {state.adx:.1f})",
                        f"Pullback to EMA 21 ({state.ema_21:.2f}) below VWAP ({state.vwap:.2f})",
                        f"Dynamic Stop Loss: {option_sl_distance} pts (derived from ATR {atr:.2f} * Delta {delta:.2f})",
                        f"Dynamic Target: {reward_points} pts (Dynamic R:R 1:{dynamic_rr})"
                    ],
                    invalidation_conditions=[
                        "Underlying breaks and closes above VWAP",
                        "ADX drops below 20 (loss of momentum)",
                        "Option price breaches stop loss level"
                    ],
                    created_at=datetime.now()
                )

        return None
