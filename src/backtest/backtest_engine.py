from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from config.settings import Settings
from src.analytics.feature_engine import FeatureEngine
from src.analytics.market_state import MarketState
from src.core.events import CandleEvent, EventBus
from src.core.logging import get_logger
from src.execution.cost_model import IndianFOCostModel
from src.execution.order_model import TradeRecord
from src.regime.classifier import MarketRegimeClassifier
from src.regime.permission_engine import TradePermissionEngine
from src.risk.risk_manager import RiskManager
from src.strategy.options_momentum_strategy import OptionsMomentumStrategy

logger = get_logger("backtest_engine")


@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    total_transaction_costs: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_amount: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sharpe_ratio: float = 0.0
    regime_breakdown: Dict[str, dict] = field(default_factory=dict)
    trades: List[dict] = field(default_factory=list)


class HistoricalBacktestEngine:
    """
    Simulates strategy decisions, regime filtering, risk limits, and order execution
    across historical candle data with realistic Indian F&O slippage and statutory taxes.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        lot_size: int = 25,
        slippage_pct: float = 0.001
    ):
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.slippage_pct = slippage_pct

    def run(self, df: pd.DataFrame, symbol: str = "NIFTY") -> BacktestMetrics:
        """
        Runs candle-by-candle replay simulation.
        Requires columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        if len(df) < 30:
            logger.warning("Historical dataset too small for backtesting", bars=len(df))
            return BacktestMetrics()

        settings = Settings()
        bus = EventBus()
        feature_engine = FeatureEngine(bus, max_history_bars=100)
        regime_classifier = MarketRegimeClassifier()
        permission_engine = TradePermissionEngine(settings)
        strategy = OptionsMomentumStrategy()
        risk_manager = RiskManager(settings)

        active_trade: Optional[dict] = None
        closed_trades: List[TradeRecord] = []
        equity_curve: List[float] = [self.initial_capital]
        current_capital = self.initial_capital

        logger.info("Starting historical backtest", symbol=symbol, total_bars=len(df))

        for idx, row in df.iterrows():
            ts = row.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            elif not isinstance(ts, datetime):
                ts = datetime.now()

            # 1. Simulate candle close into Feature Engine
            candle = CandleEvent(
                symbol=symbol,
                timeframe="1m",
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row.get("volume", 1000)),
                candle_start=ts,
                is_closed=True
            )
            # Sync ingestion into feature engine
            key = (candle.symbol, candle.timeframe)
            feature_engine._candle_history[key].append({
                "timestamp": candle.candle_start,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": max(1, candle.volume)
            })
            if len(feature_engine._candle_history[key]) > feature_engine.max_history_bars:
                feature_engine._candle_history[key] = feature_engine._candle_history[key][-feature_engine.max_history_bars:]

            history_df = pd.DataFrame(feature_engine._candle_history[key])
            if len(history_df) < 15:
                continue

            state = feature_engine._compute_market_state(symbol, "1m", history_df)
            feature_engine._latest_states[key] = state

            # 2. If in active trade, monitor stop-loss and target triggers
            if active_trade is not None:
                trade_opt = active_trade["option_type"]
                # Approximate option movement via underlying delta
                spot_change = state.close - active_trade["spot_at_entry"]
                opt_price_delta = spot_change * active_trade["delta"] if trade_opt == "CE" else -spot_change * active_trade["delta"]
                current_opt_price = max(0.50, round(active_trade["entry_price"] + opt_price_delta, 2))

                is_exit = False
                exit_reason = ""
                exit_price = current_opt_price

                # Check Target
                if current_opt_price >= active_trade["target"]:
                    is_exit = True
                    exit_reason = "TARGET_ACHIEVED"
                    exit_price = active_trade["target"]
                # Check Stop Loss
                elif current_opt_price <= active_trade["stop_loss"]:
                    is_exit = True
                    exit_reason = "STOP_LOSS_TRIGGERED"
                    exit_price = active_trade["stop_loss"]
                # Check Intraday Square-off
                elif ts.time() >= datetime.strptime("15:15:00", "%H:%M:%S").time():
                    is_exit = True
                    exit_reason = "TIME_CUTOFF"

                if is_exit:
                    # Apply slippage on exit
                    fill_exit = max(0.05, round(exit_price * (1.0 - self.slippage_pct), 2))
                    qty = active_trade["quantity"]
                    gross_pnl = round((fill_exit - active_trade["entry_price"]) * qty, 2)
                    costs = IndianFOCostModel.calculate_option_trade_costs(
                        buy_price=active_trade["entry_price"],
                        sell_price=fill_exit,
                        quantity=qty
                    )
                    net_pnl = round(gross_pnl - costs.total_costs, 2)
                    current_capital += net_pnl
                    equity_curve.append(current_capital)

                    rec = TradeRecord(
                        trade_id=f"BT_{len(closed_trades) + 1}",
                        symbol=active_trade["symbol"],
                        underlying=symbol,
                        option_type=trade_opt,
                        quantity=qty,
                        entry_price=active_trade["entry_price"],
                        exit_price=fill_exit,
                        entry_time=active_trade["entry_time"],
                        exit_time=ts,
                        gross_pnl=gross_pnl,
                        statutory_costs=costs.total_costs,
                        net_pnl=net_pnl,
                        return_pct=round((net_pnl / max(1.0, active_trade["entry_price"] * qty)) * 100.0, 2),
                        exit_reason=exit_reason,
                        strategy_name="DYNAMIC_OPTIONS_MOMENTUM",
                        market_regime=active_trade["regime"]
                    )
                    closed_trades.append(rec)
                    risk_manager.record_closed_trade_pnl(net_pnl)
                    active_trade = None
                continue

            # 3. If no active position, evaluate regime and trade permission
            classification = regime_classifier.classify(state, history_df=history_df)
            decision = permission_engine.evaluate(classification, current_time=ts)

            if not decision.is_permitted:
                continue

            # 4. Evaluate Strategy Proposal
            # Approximate current ATM option price based on moneyness & volatility
            atm_strike = round(state.close / 50.0) * 50.0
            approx_opt_price = max(10.0, round(state.atr * 4.0, 2))
            proposal = strategy.evaluate(
                state=state,
                permission=decision,
                current_option_price=approx_opt_price
            )

            if not proposal:
                continue

            # 5. Risk Assessment & Sizing
            approval = risk_manager.validate_and_size(
                proposal=proposal,
                lot_size=self.lot_size,
                available_cash=current_capital
            )

            if not approval.is_approved or approval.approved_quantity <= 0:
                continue

            # 6. Execute Simulated Entry
            fill_entry = round(proposal.expected_entry_price * (1.0 + self.slippage_pct), 2)
            active_trade = {
                "symbol": proposal.symbol,
                "option_type": proposal.option_type,
                "quantity": approval.approved_quantity,
                "entry_price": fill_entry,
                "stop_loss": proposal.stop_loss_price,
                "target": proposal.target_price,
                "spot_at_entry": state.close,
                "delta": 0.50,
                "regime": classification.regime.value,
                "entry_time": ts
            }

        # Calculate final performance metrics
        return self._compute_metrics(closed_trades, equity_curve)

    def _compute_metrics(self, trades: List[TradeRecord], equity_curve: List[float]) -> BacktestMetrics:
        if not trades:
            return BacktestMetrics()

        total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = round((winning_trades / total_trades) * 100.0, 2)

        gross_profit = round(sum(t.gross_pnl for t in wins), 2)
        gross_loss = round(abs(sum(t.gross_pnl for t in losses)), 2)
        total_costs = round(sum(t.statutory_costs for t in trades), 2)
        net_pnl = round(sum(t.net_pnl for t in trades), 2)

        profit_factor = round(gross_profit / max(1.0, gross_loss), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Max Drawdown
        peak = self.initial_capital
        max_dd_amount = 0.0
        max_dd_pct = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = (dd / peak) * 100.0
            if dd > max_dd_amount:
                max_dd_amount = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        avg_trade = round(net_pnl / total_trades, 2)
        avg_win = round(sum(t.net_pnl for t in wins) / max(1, winning_trades), 2)
        avg_loss = round(sum(t.net_pnl for t in losses) / max(1, losing_trades), 2)

        # Sharpe Ratio (annualized assuming daily samples)
        returns = [t.return_pct / 100.0 for t in trades]
        std_ret = np.std(returns) if len(returns) > 1 else 0.0
        sharpe = round((np.mean(returns) / max(1e-4, std_ret)) * np.sqrt(252), 2) if std_ret > 0 else 0.0

        # Performance Breakdown by Market Regime
        regime_stats = {}
        for reg in set(t.market_regime for t in trades):
            reg_trades = [t for t in trades if t.market_regime == reg]
            reg_wins = len([t for t in reg_trades if t.net_pnl > 0])
            regime_stats[reg] = {
                "trades": len(reg_trades),
                "win_rate": round((reg_wins / len(reg_trades)) * 100.0, 2),
                "net_pnl": round(sum(t.net_pnl for t in reg_trades), 2)
            }

        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_pnl=net_pnl,
            total_transaction_costs=total_costs,
            profit_factor=profit_factor,
            max_drawdown_amount=round(max_dd_amount, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            avg_trade_pnl=avg_trade,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sharpe_ratio=sharpe,
            regime_breakdown=regime_stats,
            trades=[
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "type": t.option_type,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "net_pnl": t.net_pnl,
                    "return_pct": t.return_pct,
                    "exit_reason": t.exit_reason,
                    "regime": t.market_regime
                }
                for t in trades
            ]
        )

