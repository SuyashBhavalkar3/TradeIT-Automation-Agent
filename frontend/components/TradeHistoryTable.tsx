"use client";

import React from "react";
import { History, CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { TradeRecordItem } from "@/lib/api";

interface Props {
  trades: TradeRecordItem[];
}

export default function TradeHistoryTable({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg">
        <div className="flex items-center justify-between pb-3 border-b border-cardBorder">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-400" />
            <h3 className="font-bold text-base text-white">Closed Trade Journal</h3>
          </div>
          <span className="text-xs font-mono text-slate-400">0 Trades</span>
        </div>
        <div className="py-8 text-center text-slate-400 text-sm">
          No closed trades recorded yet for today's session.
        </div>
      </div>
    );
  }

  const getExitReasonBadge = (reason: string) => {
    if (reason.includes("TARGET")) {
      return (
        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-bold">
          TARGET HIT
        </span>
      );
    }
    if (reason.includes("STOP_LOSS")) {
      return (
        <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 text-[10px] font-bold">
          STOP LOSS HIT
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]">
        {reason}
      </span>
    );
  };

  return (
    <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg overflow-hidden">
      <div className="flex items-center justify-between pb-3 border-b border-cardBorder mb-3">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-indigo-400" />
          <h3 className="font-bold text-base text-white">Closed Trade Journal</h3>
        </div>
        <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
          {trades.length} Completed
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <th className="py-2.5 px-3">Trade ID</th>
              <th className="py-2.5 px-3">Contract</th>
              <th className="py-2.5 px-3">Qty</th>
              <th className="py-2.5 px-3">Entry</th>
              <th className="py-2.5 px-3">Exit</th>
              <th className="py-2.5 px-3">Taxes & Costs</th>
              <th className="py-2.5 px-3">Exit Reason</th>
              <th className="py-2.5 px-3 text-right">Net P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {trades.map((t, idx) => {
              const isWin = t.net_pnl > 0;
              return (
                <tr key={idx} className="hover:bg-slate-900/50 transition-colors">
                  <td className="py-3 px-3 text-slate-400 font-bold">{t.trade_id}</td>
                  <td className="py-3 px-3 text-white font-bold">{t.symbol}</td>
                  <td className="py-3 px-3 text-slate-300">{t.quantity}</td>
                  <td className="py-3 px-3 text-slate-300">₹{t.entry_price.toFixed(2)}</td>
                  <td className="py-3 px-3 text-white font-bold">₹{t.exit_price.toFixed(2)}</td>
                  <td className="py-3 px-3 text-slate-400">₹{t.taxes_and_costs.toFixed(2)}</td>
                  <td className="py-3 px-3">{getExitReasonBadge(t.exit_reason)}</td>
                  <td
                    className={`py-3 px-3 text-right font-bold text-sm ${
                      isWin ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isWin ? "+" : ""}₹{t.net_pnl.toFixed(2)} ({t.return_pct > 0 ? "+" : ""}
                    {t.return_pct.toFixed(1)}%)
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

