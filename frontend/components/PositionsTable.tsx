"use client";

import React from "react";
import { Layers, ArrowUpRight, ArrowDownRight, Clock } from "lucide-react";
import { PositionItem } from "@/lib/api";

interface Props {
  positions: PositionItem[];
  onRefresh: () => void;
}

export default function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg">
        <div className="flex items-center justify-between pb-3 border-b border-cardBorder">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            <h3 className="font-bold text-base text-white">Open Active Positions</h3>
          </div>
          <span className="text-xs font-mono text-slate-400">0 Active</span>
        </div>
        <div className="py-8 text-center text-slate-400 text-sm">
          No active positions currently open. Risk limits fully protected.
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg overflow-hidden">
      <div className="flex items-center justify-between pb-3 border-b border-cardBorder mb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-indigo-400" />
          <h3 className="font-bold text-base text-white">Open Active Positions</h3>
        </div>
        <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
          {positions.length} Live Trade(s)
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <th className="py-2.5 px-3">Contract</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Qty</th>
              <th className="py-2.5 px-3">Avg Entry</th>
              <th className="py-2.5 px-3">LTP</th>
              <th className="py-2.5 px-3">SL</th>
              <th className="py-2.5 px-3">Target</th>
              <th className="py-2.5 px-3 text-right">MTM P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {positions.map((pos, idx) => {
              const isProfit = pos.unrealized_pnl >= 0;
              const isCall = pos.option_type === "CE";
              return (
                <tr key={idx} className="hover:bg-slate-900/50 transition-colors">
                  <td className="py-3 px-3 font-bold text-white flex items-center gap-1.5">
                    {isCall ? (
                      <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
                    )}
                    {pos.symbol}
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isCall
                          ? "bg-emerald-950 text-emerald-300"
                          : "bg-rose-950 text-rose-300"
                      }`}
                    >
                      {pos.option_type}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-slate-200">{pos.quantity}</td>
                  <td className="py-3 px-3 text-slate-300">₹{pos.avg_entry_price.toFixed(2)}</td>
                  <td className="py-3 px-3 text-white font-bold">
                    ₹{pos.current_price.toFixed(2)}
                  </td>
                  <td className="py-3 px-3 text-rose-400">₹{pos.stop_loss.toFixed(2)}</td>
                  <td className="py-3 px-3 text-emerald-400">₹{pos.target.toFixed(2)}</td>
                  <td
                    className={`py-3 px-3 text-right font-bold text-sm ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}₹{pos.unrealized_pnl.toFixed(2)}
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

