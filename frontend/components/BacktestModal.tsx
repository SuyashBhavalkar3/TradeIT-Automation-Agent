"use client";

import React, { useState } from "react";
import { BarChart2, X, Play, Award, AlertCircle, Percent } from "lucide-react";
import { BacktestResponse, TradeITApi } from "@/lib/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  activeSymbol: string;
}

export default function BacktestModal({ isOpen, onClose, activeSymbol }: Props) {
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleRunBacktest = async () => {
    try {
      setIsRunning(true);
      setError(null);
      const data = await TradeITApi.runBacktest(activeSymbol);
      if (data.status === "insufficient_data") {
        setError(data.status + ": " + (data as any).message);
        setResult(null);
      } else {
        setResult(data);
      }
    } catch (e: any) {
      setError(e.message || "Failed to execute backtest");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121721] border border-[#1f2937] rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl p-6 text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-6 h-6 text-blue-400" />
            <div>
              <h2 className="text-lg font-bold text-white">Historical Backtest Simulator</h2>
              <p className="text-xs text-slate-400">
                Replays live captured candles through the full Strategy, Regime & Statutory Cost Engine
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Action Bar */}
        <div className="mt-4 flex items-center justify-between p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div>
            <span className="text-xs text-slate-400">Symbol Target:</span>
            <span className="ml-2 font-mono font-bold text-white text-sm">{activeSymbol}</span>
          </div>

          <button
            onClick={handleRunBacktest}
            disabled={isRunning}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-blue-600/30 transition-all active:scale-95 disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-white" />
            <span>{isRunning ? "Running Simulation..." : "Run Multi-Bar Backtest"}</span>
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="mt-6 space-y-4">
            {/* Top Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-center font-mono">
                <span className="text-[10px] text-slate-400 uppercase">Win Rate</span>
                <div className="text-xl font-extrabold text-emerald-400 mt-1">
                  {result.win_rate_pct.toFixed(1)}%
                </div>
                <span className="text-[10px] text-slate-500">{result.total_trades} trades</span>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-center font-mono">
                <span className="text-[10px] text-slate-400 uppercase">Net Realized P&L</span>
                <div
                  className={`text-xl font-extrabold mt-1 ${
                    result.net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {result.net_pnl >= 0 ? "+" : ""}₹{result.net_pnl.toFixed(2)}
                </div>
                <span className="text-[10px] text-slate-500">After taxes</span>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-center font-mono">
                <span className="text-[10px] text-slate-400 uppercase">Profit Factor</span>
                <div className="text-xl font-extrabold text-sky-400 mt-1">
                  {result.profit_factor.toFixed(2)}
                </div>
                <span className="text-[10px] text-slate-500">Gross W / Gross L</span>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-center font-mono">
                <span className="text-[10px] text-slate-400 uppercase">Max Drawdown</span>
                <div className="text-xl font-extrabold text-amber-400 mt-1">
                  {result.max_drawdown_pct.toFixed(2)}%
                </div>
                <span className="text-[10px] text-slate-500">₹{result.max_drawdown_amount.toFixed(0)}</span>
              </div>
            </div>

            {/* Statutory Cost Disclosure */}
            <div className="p-3 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400">Total Statutory Costs (Brokerage + STT + GST + SEBI):</span>
              <span className="text-rose-400 font-bold">
                ₹{result.total_taxes_and_brokerage.toFixed(2)}
              </span>
            </div>

            {/* Regime Breakdown */}
            {result.regime_breakdown && Object.keys(result.regime_breakdown).length > 0 && (
              <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
                <h4 className="text-xs font-bold text-slate-300 uppercase mb-2">
                  Performance by Market Regime
                </h4>
                <div className="space-y-1.5 font-mono text-xs">
                  {Object.entries(result.regime_breakdown).map(([reg, count], idx) => (
                    <div key={idx} className="flex justify-between text-slate-400">
                      <span>{reg}</span>
                      <span className="text-white font-bold">{count} trades</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

