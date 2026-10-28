"use client";

import React from "react";
import { TrendingUp, TrendingDown, DollarSign, Wallet, ShieldAlert } from "lucide-react";
import { PortfolioResponse, RiskStatusResponse } from "@/lib/api";

interface Props {
  portfolio: PortfolioResponse | null;
  risk: RiskStatusResponse | null;
}

export default function PnLStrip({ portfolio, risk }: Props) {
  const equity = portfolio?.total_equity ?? 100000;
  const cash = portfolio?.available_cash ?? 100000;
  const marginUsed = portfolio?.margin_used ?? 0;
  const unrealized = portfolio?.unrealized_pnl ?? 0;
  const realized = portfolio?.realized_pnl ?? 0;

  const maxLoss = risk?.max_daily_loss ?? 5000;
  const dailyPnL = risk?.cumulative_daily_pnl ?? 0;

  // Circuit breaker calculation
  // E.g. If daily loss is negative, compute percentage of maxDailyLoss consumed
  const lossConsumedPct =
    dailyPnL < 0 ? Math.min(100, Math.round((Math.abs(dailyPnL) / maxLoss) * 100)) : 0;

  const isCircuitBreakerNear = lossConsumedPct >= 70;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 w-full">
      {/* Total Equity */}
      <div className="bg-card border border-cardBorder rounded-xl p-4 shadow-md flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs">
          <span>Total Net Equity</span>
          <Wallet className="w-4 h-4 text-blue-400" />
        </div>
        <div className="mt-2">
          <div className="text-xl font-extrabold text-white font-mono">
            ₹{equity.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
          <span className="text-[11px] text-slate-400">Capital + Live MTM</span>
        </div>
      </div>

      {/* Realized P&L */}
      <div className="bg-card border border-cardBorder rounded-xl p-4 shadow-md flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs">
          <span>Realized P&L (Today)</span>
          {realized >= 0 ? (
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          ) : (
            <TrendingDown className="w-4 h-4 text-rose-400" />
          )}
        </div>
        <div className="mt-2">
          <div
            className={`text-xl font-extrabold font-mono ${
              realized >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {realized >= 0 ? "+" : ""}₹
            {realized.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
          <span className="text-[11px] text-slate-400">Post-statutory costs</span>
        </div>
      </div>

      {/* Unrealized MTM P&L */}
      <div className="bg-card border border-cardBorder rounded-xl p-4 shadow-md flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs">
          <span>Unrealized Live MTM</span>
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              unrealized !== 0 ? "bg-amber-400 animate-ping" : "bg-slate-600"
            }`}
          />
        </div>
        <div className="mt-2">
          <div
            className={`text-xl font-extrabold font-mono ${
              unrealized > 0
                ? "text-emerald-400"
                : unrealized < 0
                ? "text-rose-400"
                : "text-slate-300"
            }`}
          >
            {unrealized >= 0 ? "+" : ""}₹
            {unrealized.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
          <span className="text-[11px] text-slate-400">
            {portfolio?.open_positions_count ?? 0} active position(s)
          </span>
        </div>
      </div>

      {/* Margin / Available Cash */}
      <div className="bg-card border border-cardBorder rounded-xl p-4 shadow-md flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs">
          <span>Available Cash</span>
          <DollarSign className="w-4 h-4 text-sky-400" />
        </div>
        <div className="mt-2">
          <div className="text-xl font-extrabold text-white font-mono">
            ₹{cash.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
          <span className="text-[11px] text-slate-400">
            Margin Deployed: ₹{marginUsed.toLocaleString("en-IN")}
          </span>
        </div>
      </div>

      {/* Daily Circuit Breaker */}
      <div
        className={`border rounded-xl p-4 shadow-md flex flex-col justify-between ${
          isCircuitBreakerNear
            ? "bg-rose-950/40 border-rose-600"
            : "bg-card border-cardBorder"
        }`}
      >
        <div className="flex items-center justify-between text-xs">
          <span className={isCircuitBreakerNear ? "text-rose-300 font-bold" : "text-slate-400"}>
            Daily Loss Circuit Breaker
          </span>
          <ShieldAlert
            className={`w-4 h-4 ${
              isCircuitBreakerNear ? "text-rose-400 animate-bounce" : "text-slate-400"
            }`}
          />
        </div>
        <div className="mt-2">
          <div className="flex items-baseline justify-between text-xs font-mono mb-1">
            <span className="text-slate-300 font-bold">
              ₹{Math.abs(Math.min(0, dailyPnL)).toLocaleString("en-IN")} / ₹
              {maxLoss.toLocaleString("en-IN")}
            </span>
            <span
              className={
                lossConsumedPct > 50
                  ? "text-rose-400 font-bold"
                  : "text-slate-400"
              }
            >
              {lossConsumedPct}%
            </span>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                lossConsumedPct >= 80
                  ? "bg-rose-500"
                  : lossConsumedPct >= 50
                  ? "bg-amber-500"
                  : "bg-blue-500"
              }`}
              style={{ width: `${lossConsumedPct}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-400 mt-1 block">
            Automatic Emergency Halt at ₹{maxLoss.toLocaleString("en-IN")}
          </span>
        </div>
      </div>
    </div>
  );
}

