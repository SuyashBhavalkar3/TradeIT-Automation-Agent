"use client";

import React, { useState } from "react";
import { Shield, ShieldAlert, Zap, AlertOctagon, RefreshCw, Activity, Terminal } from "lucide-react";
import { HealthResponse, SafeModeStatusResponse, TradeITApi } from "@/lib/api";

interface Props {
  health: HealthResponse | null;
  safeMode: SafeModeStatusResponse | null;
  isEmergencyHalt: boolean;
  onRefresh: () => void;
  onPanicSuccess: () => void;
}

export default function Header({
  health,
  safeMode,
  isEmergencyHalt,
  onRefresh,
  onPanicSuccess,
}: Props) {
  const [isTogglingSafeMode, setIsTogglingSafeMode] = useState(false);
  const [isTogglingMode, setIsTogglingMode] = useState(false);
  const [isPanicking, setIsPanicking] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const handleToggleMode = async () => {
    const isPaper = health?.trading_mode === "PAPER";
    const targetMode = isPaper ? "LIVE" : "PAPER";
    const confirmed = window.confirm(
      `SWITCH TRADING MODE CONFIRMATION:\nAre you sure you want to switch to ${targetMode}?\n\n${
        targetMode === "LIVE"
          ? "CRITICAL: Armed trade setups will execute REAL orders on your Dhan broker account!"
          : "Switches to simulated paper trading with zero risk to capital."
      }`
    );
    if (!confirmed) return;

    try {
      setIsTogglingMode(true);
      await fetch("http://127.0.0.1:8000/api/settings/mode?mode=" + targetMode, {
        method: "POST",
      });
      onRefresh();
    } catch (e: any) {
      alert("Failed to switch mode: " + e.message);
    } finally {
      setIsTogglingMode(false);
    }
  };

  const handleToggleSafeMode = async () => {
    if (!safeMode) return;
    try {
      setIsTogglingSafeMode(true);
      await TradeITApi.toggleSafeMode(!safeMode.safe_mode_enabled);
      onRefresh();
    } catch (e) {
      console.error("Failed to toggle safe mode", e);
    } finally {
      setIsTogglingSafeMode(false);
    }
  };

  const handlePanicSquareOff = async () => {
    const confirmed = window.confirm(
      "EMERGENCY CONFIRMATION:\nAre you sure you want to SQUARE OFF ALL open positions immediately and HALT new orders?"
    );
    if (!confirmed) return;

    try {
      setIsPanicking(true);
      const res = await TradeITApi.panicCloseAll();
      alert(res.message);
      onPanicSuccess();
    } catch (e: any) {
      alert("Panic exit failed: " + e.message);
    } finally {
      setIsPanicking(false);
    }
  };

  const handleResetHalt = async () => {
    try {
      setIsResetting(true);
      await TradeITApi.resetEmergencyHalt();
      onRefresh();
    } catch (e: any) {
      alert("Failed to reset halt: " + e.message);
    } finally {
      setIsResetting(false);
    }
  };

  const isPaper = health?.trading_mode === "PAPER";
  const isHealthy = health?.status === "healthy";
  const safeModeEnabled = safeMode?.safe_mode_enabled ?? true;

  return (
    <header className="w-full bg-[#0d121c] border-b border-[#1f293d] px-6 py-4 sticky top-0 z-50 shadow-lg">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand & Market Feed Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-extrabold text-xl tracking-tight text-white">TradeIT</h1>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50">
                  F&O AI Engine
                </span>
              </div>
              <p className="text-xs text-slate-400">Intelligent Options Trading with Zero Capital Compromise</p>
            </div>
          </div>

          <div className="hidden lg:flex items-center gap-2 pl-4 border-l border-slate-700/60">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isHealthy ? "bg-emerald-500 animate-pulse" : "bg-amber-500"
              }`}
            />
            <span className="text-xs font-mono text-slate-300">
              {health?.feed_state || "NSE TICK FEED"}
            </span>
          </div>
        </div>

        {/* Control Badges & Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Trading Mode Display & 1-Click Toggle */}
          <button
            onClick={handleToggleMode}
            disabled={isTogglingMode}
            title="Click to toggle between Paper and Live Dhan mode"
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border font-mono text-xs font-semibold cursor-pointer transition-all hover:scale-105 active:scale-95 ${
              isPaper
                ? "bg-sky-950/60 border-sky-600/50 text-sky-300 hover:bg-sky-900/70"
                : "bg-red-950/80 border-red-600 text-red-300 animate-pulse hover:bg-red-900"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isPaper ? "bg-sky-400" : "bg-red-500"
              }`}
            />
            <span>MODE: {isPaper ? "SIMULATED PAPER" : "LIVE REAL DHAN"}</span>
          </button>

          {/* Safe Mode Pre-Approval Toggle */}
          <button
            onClick={handleToggleSafeMode}
            disabled={isTogglingSafeMode}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
              safeModeEnabled
                ? "bg-purple-950/70 border-purple-500 text-purple-200 hover:bg-purple-900/80 shadow-md shadow-purple-900/20"
                : "bg-amber-950/50 border-amber-500/80 text-amber-200 hover:bg-amber-900/60"
            }`}
          >
            {safeModeEnabled ? (
              <>
                <Shield className="w-4 h-4 text-purple-400" />
                <span>SAFE MODE: ON (Pre-Approval Req)</span>
              </>
            ) : (
              <>
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                <span>AUTONOMOUS (Auto-Pilot)</span>
              </>
            )}
          </button>

          {/* Emergency Halt Badge or Panic Button */}
          {isEmergencyHalt ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-900/90 text-red-100 border border-red-500 text-xs font-bold animate-bounce">
                <AlertOctagon className="w-4 h-4" />
                TRADING HALTED
              </span>
              <button
                onClick={handleResetHalt}
                disabled={isResetting}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-white border border-slate-600 font-medium"
              >
                Reset Halt
              </button>
            </div>
          ) : (
            <button
              onClick={handlePanicSquareOff}
              disabled={isPanicking}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition-all shadow-lg shadow-red-600/30 active:scale-95"
            >
              <AlertOctagon className="w-4 h-4" />
              <span>{isPanicking ? "Closing..." : "PANIC SQUARE OFF"}</span>
            </button>
          )}

          {/* Manual Refresh Button */}
          <button
            onClick={onRefresh}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition-all"
            title="Refresh Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

