"use client";

import React from "react";
import { Compass, CheckCircle2, XCircle, AlertTriangle, Info } from "lucide-react";
import { RegimeResponse } from "@/lib/api";

interface Props {
  regime: RegimeResponse | null;
}

export default function RegimeIntelligenceCard({ regime }: Props) {
  if (!regime || !regime.classification) {
    return (
      <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-800 rounded w-2/3" />
      </div>
    );
  }

  const { classification, permission } = regime;
  const regimeName = classification.regime;
  const ci = classification.details?.choppiness_index ?? 50;
  const adx = classification.details?.adx ?? 20;
  const chopThresh = classification.details?.chop_threshold ?? 61.8;
  const trendThresh = classification.details?.trend_threshold ?? 38.2;

  // Color mapping for regime
  const getRegimeColor = (name: string) => {
    switch (name) {
      case "TRENDING_BULLISH":
        return "bg-emerald-950/70 border-emerald-500 text-emerald-300";
      case "TRENDING_BEARISH":
        return "bg-rose-950/70 border-rose-500 text-rose-300";
      case "RANGING":
        return "bg-sky-950/70 border-sky-500 text-sky-300";
      case "CHOPPY":
        return "bg-amber-950/70 border-amber-500 text-amber-300";
      case "HIGH_VOLATILITY":
        return "bg-purple-950/70 border-purple-500 text-purple-300";
      default:
        return "bg-slate-800 border-slate-600 text-slate-300";
    }
  };

  const getPermissionBadge = (state: string) => {
    switch (state) {
      case "PERMITTED":
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 text-xs font-semibold">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            PERMITTED TO TRADE
          </span>
        );
      case "MANAGE_ONLY":
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-950 text-amber-300 border border-amber-600 text-xs font-semibold">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            MANAGE EXITS ONLY
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-rose-950 text-rose-300 border border-rose-600 text-xs font-semibold">
            <XCircle className="w-3.5 h-3.5 text-rose-400" />
            NEW ENTRIES BLOCKED
          </span>
        );
    }
  };

  return (
    <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg flex flex-col justify-between">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-cardBorder">
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-indigo-400" />
            <h3 className="font-bold text-base text-white">Market Intelligence & Regime</h3>
          </div>
          {getPermissionBadge(permission.state)}
        </div>

        {/* Current Regime Tag */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Classified Regime:</span>
            <span
              className={`px-3 py-1 rounded-lg border text-xs font-mono font-bold tracking-wide uppercase ${getRegimeColor(
                regimeName
              )}`}
            >
              {regimeName}
            </span>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            Confidence: {Math.round(classification.confidence * 100)}%
          </span>
        </div>

        {/* Choppiness & ADX Gauges */}
        <div className="mt-4 grid grid-cols-2 gap-3">
          {/* Choppiness Index */}
          <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Choppiness Index (CI)</span>
              <span className="font-mono font-bold text-white">{ci.toFixed(1)}</span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full mt-2 overflow-hidden flex">
              <div
                className={`h-full transition-all duration-300 ${
                  ci > chopThresh
                    ? "bg-amber-500"
                    : ci < trendThresh
                    ? "bg-emerald-500"
                    : "bg-blue-500"
                }`}
                style={{ width: `${Math.min(100, ci)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-400 mt-1 font-mono">
              <span>Trend &lt;{trendThresh.toFixed(1)}</span>
              <span>Chop &gt;{chopThresh.toFixed(1)}</span>
            </div>
          </div>

          {/* ADX Trend Strength */}
          <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>ADX Strength</span>
              <span className="font-mono font-bold text-white">{adx.toFixed(1)}</span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full mt-2 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  adx >= 25 ? "bg-emerald-500" : "bg-slate-500"
                }`}
                style={{ width: `${Math.min(100, (adx / 60) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-400 mt-1 font-mono">
              <span>Weak &lt;20</span>
              <span>Strong &gt;25</span>
            </div>
          </div>
        </div>

        {/* Explainability / Rationale Strip */}
        <div className="mt-4 p-3 rounded-lg bg-blue-950/20 border border-blue-900/40 text-xs">
          <div className="flex items-start gap-2">
            <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-blue-200">
                {classification.primary_reason || "Analyzing price structure and volatility."}
              </p>
              {permission.reasons && permission.reasons.length > 0 && (
                <ul className="mt-1.5 space-y-0.5 text-slate-400 text-[11px] list-disc list-inside">
                  {permission.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-cardBorder text-[11px] text-slate-400 italic">
        "Rule 1: Capital preservation is the highest priority. Doing nothing in choppy markets protects capital."
      </div>
    </div>
  );
}

