"use client";

import React, { useState } from "react";
import { Target, Shield, Check, X, ArrowUpRight, ArrowDownRight, Zap } from "lucide-react";
import { StrategyProposalResponse, SafeModeStatusResponse, TradeITApi } from "@/lib/api";

interface Props {
  symbol: string;
  proposalData: StrategyProposalResponse | null;
  safeMode: SafeModeStatusResponse | null;
  onActionSuccess: () => void;
}

export default function StrategyProposalCard({
  symbol,
  proposalData,
  safeMode,
  onActionSuccess,
}: Props) {
  const [isArming, setIsArming] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);

  const proposal = proposalData?.proposal;
  const risk = proposalData?.risk_assessment;
  const activeSetups = safeMode?.active_setups || {};

  // Find if an active setup matches this symbol
  const matchingSetup = Object.values(activeSetups).find((s) => s.symbol.includes(symbol));

  const handleArmSetup = async (setupId: string) => {
    try {
      setIsArming(true);
      const res = await TradeITApi.armSetup(setupId);
      alert(res.message);
      onActionSuccess();
    } catch (e: any) {
      alert("Arming failed: " + e.message);
    } finally {
      setIsArming(false);
    }
  };

  const handleDisarmSetup = async (setupId: string) => {
    try {
      setIsArming(true);
      const res = await TradeITApi.disarmSetup(setupId);
      alert(res.message);
      onActionSuccess();
    } catch (e: any) {
      alert("Disarm failed: " + e.message);
    } finally {
      setIsArming(false);
    }
  };

  const handleExecuteNow = async () => {
    try {
      setIsExecuting(true);
      const res = await TradeITApi.executeTrade(symbol);
      if (res.status === "EXECUTED") {
        alert(`Trade Executed!\nOrder ID: ${res.order_id}\nFill Price: ₹${res.fill_price}\nQuantity: ${res.quantity}`);
      } else {
        alert(`Execution Result: ${res.status}\nMessage: ${res.message || JSON.stringify(res.reasons)}`);
      }
      onActionSuccess();
    } catch (e: any) {
      alert("Execution failed: " + e.message);
    } finally {
      setIsExecuting(false);
    }
  };

  if (!proposal || proposalData?.status !== "PROPOSED") {
    return (
      <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-3 border-b border-cardBorder">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-indigo-400" />
              <h3 className="font-bold text-base text-white">Active Strategy Setup</h3>
            </div>
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-xs font-mono">
              STANDBY
            </span>
          </div>
          <div className="py-8 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center mx-auto mb-3 text-slate-500">
              <Zap className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-slate-300">No Actionable Setup Under Current Regime</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {proposalData?.message ||
                "The bot is waiting for confirmed trend pullback alignment and acceptable risk-reward."}
            </p>
          </div>
        </div>

        <div className="pt-3 border-t border-cardBorder text-[11px] text-slate-500 flex items-center justify-between">
          <span>Anti-Chasing Protection: ACTIVE (1.0% Max Cap)</span>
          <span>Status: Monitoring live ticks</span>
        </div>
      </div>
    );
  }

  const isCall = proposal.direction === "BUY_CALL";
  const setupStatus = matchingSetup ? matchingSetup.status : "PENDING_APPROVAL";
  const antiChasingCeiling = (proposal.entry_price * 1.01).toFixed(2);

  return (
    <div className="bg-card border border-cardBorder rounded-xl p-5 shadow-lg flex flex-col justify-between">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-cardBorder">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-indigo-400" />
            <h3 className="font-bold text-base text-white">Active Strategy Setup</h3>
          </div>
          <span
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-bold font-mono ${
              isCall
                ? "bg-emerald-950 text-emerald-300 border border-emerald-600"
                : "bg-rose-950 text-rose-300 border border-rose-600"
            }`}
          >
            {isCall ? (
              <ArrowUpRight className="w-3.5 h-3.5" />
            ) : (
              <ArrowDownRight className="w-3.5 h-3.5" />
            )}
            {proposal.contract}
          </span>
        </div>

        {/* Pricing Metrics Grid */}
        <div className="mt-4 grid grid-cols-3 gap-2 text-center font-mono">
          <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-400 block uppercase">Entry Target</span>
            <span className="text-base font-bold text-amber-400">₹{proposal.entry_price}</span>
          </div>
          <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-400 block uppercase">Stop Loss</span>
            <span className="text-base font-bold text-rose-400">₹{proposal.stop_loss}</span>
          </div>
          <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
            <span className="text-[10px] text-slate-400 block uppercase">Profit Target</span>
            <span className="text-base font-bold text-emerald-400">₹{proposal.target}</span>
          </div>
        </div>

        {/* Risk & Reward Analysis */}
        <div className="mt-3 p-3 rounded-lg bg-slate-900/40 border border-slate-800 flex items-center justify-between text-xs font-mono">
          <div>
            <span className="text-slate-400">Risk:Reward: </span>
            <span className="font-bold text-white">1:{proposal.risk_reward_ratio}</span>
          </div>
          <div>
            <span className="text-slate-400">Size: </span>
            <span className="font-bold text-white">
              {risk?.lots ?? 1} Lot ({risk?.quantity ?? 25} qty)
            </span>
          </div>
          <div>
            <span className="text-slate-400">Max Risk: </span>
            <span className="font-bold text-rose-400">₹{risk?.total_risk_amount}</span>
          </div>
        </div>

        {/* Anti-Chasing Ceiling Protection Indicator */}
        <div className="mt-3 px-3 py-2 rounded-lg bg-purple-950/30 border border-purple-800/40 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-purple-300">
            <Shield className="w-3.5 h-3.5 text-purple-400" />
            <span>Anti-Chasing Price Ceiling:</span>
          </div>
          <span className="font-mono font-bold text-purple-200">₹{antiChasingCeiling} (+1.0% max)</span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="mt-4 pt-3 border-t border-cardBorder flex items-center gap-3">
        {matchingSetup && matchingSetup.status === "ARMED" ? (
          <div className="flex items-center justify-between w-full gap-2">
            <span className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-purple-900/60 text-purple-200 border border-purple-500 text-xs font-bold font-mono animate-pulse flex-1 justify-center">
              <Zap className="w-4 h-4 text-purple-400" />
              SETUP ARMED & MONITORING
            </span>
            <button
              onClick={() => handleDisarmSetup(matchingSetup.setup_id)}
              disabled={isArming}
              className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-rose-300 border border-slate-700 font-semibold"
            >
              Disarm
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2 w-full">
            {matchingSetup ? (
              <button
                onClick={() => handleArmSetup(matchingSetup.setup_id)}
                disabled={isArming}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition-all active:scale-98"
              >
                <Zap className="w-4 h-4 text-amber-300" />
                <span>{isArming ? "Arming..." : "ARM SETUP (PRE-APPROVE)"}</span>
              </button>
            ) : null}

            <button
              onClick={handleExecuteNow}
              disabled={isExecuting}
              className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-lg shadow-emerald-600/20 transition-all"
            >
              {isExecuting ? "Executing..." : "Execute Paper Trade"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
