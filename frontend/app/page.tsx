"use client";

import React, { useEffect, useState, useCallback } from "react";
import Header from "@/components/Header";
import PnLStrip from "@/components/PnLStrip";
import TradingViewChart from "@/components/TradingViewChart";
import RegimeIntelligenceCard from "@/components/RegimeIntelligenceCard";
import StrategyProposalCard from "@/components/StrategyProposalCard";
import PositionsTable from "@/components/PositionsTable";
import TradeHistoryTable from "@/components/TradeHistoryTable";
import BacktestModal from "@/components/BacktestModal";
import {
  CandlesResponse,
  HealthResponse,
  PortfolioResponse,
  PositionItem,
  RegimeResponse,
  RiskStatusResponse,
  SafeModeStatusResponse,
  StrategyProposalResponse,
  TradeITApi,
  TradeRecordItem,
} from "@/lib/api";
import { BarChart3, RefreshCw } from "lucide-react";

export default function Dashboard() {
  const [symbol, setSymbol] = useState<string>("NIFTY");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [safeMode, setSafeMode] = useState<SafeModeStatusResponse | null>(null);
  const [risk, setRisk] = useState<RiskStatusResponse | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [trades, setTrades] = useState<TradeRecordItem[]>([]);
  const [candlesData, setCandlesData] = useState<CandlesResponse | null>(null);
  const [regime, setRegime] = useState<RegimeResponse | null>(null);
  const [proposal, setProposal] = useState<StrategyProposalResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"positions" | "journal">("positions");
  const [isBacktestOpen, setIsBacktestOpen] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  const fetchAllData = useCallback(async () => {
    try {
      const [
        hRes,
        smRes,
        rRes,
        pRes,
        posRes,
        tRes,
        cRes,
        regRes,
        propRes,
      ] = await Promise.allSettled([
        TradeITApi.getHealth(),
        TradeITApi.getSafeModeStatus(),
        TradeITApi.getRiskStatus(),
        TradeITApi.getPortfolio(),
        TradeITApi.getPositions(),
        TradeITApi.getTrades(),
        TradeITApi.getCandles(symbol),
        TradeITApi.getRegime(symbol),
        TradeITApi.getStrategyProposal(symbol),
      ]);

      if (hRes.status === "fulfilled") setHealth(hRes.value);
      if (smRes.status === "fulfilled") setSafeMode(smRes.value);
      if (rRes.status === "fulfilled") setRisk(rRes.value);
      if (pRes.status === "fulfilled") setPortfolio(pRes.value);
      if (posRes.status === "fulfilled") setPositions(posRes.value);
      if (tRes.status === "fulfilled") setTrades(tRes.value);
      if (cRes.status === "fulfilled") setCandlesData(cRes.value);
      if (regRes.status === "fulfilled") setRegime(regRes.value);
      if (propRes.status === "fulfilled") setProposal(propRes.value);

      setLastRefreshed(new Date());
    } catch (err) {
      console.error("Error refreshing dashboard data:", err);
    }
  }, [symbol]);

  // Initial fetch and 2.5-second polling interval
  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 2500);
    return () => clearInterval(interval);
  }, [fetchAllData]);

  const proposalObj = proposal?.proposal;

  return (
    <div className="min-h-screen bg-[#0b0e14] text-slate-100 flex flex-col">
      {/* Header Bar */}
      <Header
        health={health}
        safeMode={safeMode}
        isEmergencyHalt={risk?.is_emergency_halt ?? false}
        onRefresh={fetchAllData}
        onPanicSuccess={fetchAllData}
      />

      {/* Main Container */}
      <main className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 flex-1 flex flex-col gap-6">
        {/* P&L & Circuit Breaker Strip */}
        <PnLStrip portfolio={portfolio} risk={risk} />

        {/* Symbol Selector & Quick Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-card border border-cardBorder rounded-xl px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Underlying Instrument:</span>
            <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-lg border border-slate-800">
              {["NIFTY", "BANKNIFTY"].map((sym) => (
                <button
                  key={sym}
                  onClick={() => setSymbol(sym)}
                  className={`px-3 py-1 rounded text-xs font-mono font-bold transition-all ${
                    symbol === sym
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsBacktestOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-sky-300 transition-all"
            >
              <BarChart3 className="w-4 h-4 text-sky-400" />
              <span>Backtest Engine</span>
            </button>

            <span suppressHydrationWarning className="text-[11px] text-slate-500 font-mono hidden md:inline">
              Synced: {lastRefreshed.toLocaleTimeString()}
            </span>
          </div>
        </div>

        {/* Main Workstation Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Columns: Chart & Table */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            {/* Interactive TradingView Chart */}
            <TradingViewChart
              symbol={symbol}
              candles={candlesData?.candles || []}
              indicators={candlesData?.indicators}
              entryPrice={proposalObj?.entry_price}
              stopLossPrice={proposalObj?.stop_loss}
              targetPrice={proposalObj?.target}
            />

            {/* Position & Journal Tabs */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 border-b border-cardBorder pb-2">
                <button
                  onClick={() => setActiveTab("positions")}
                  className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                    activeTab === "positions"
                      ? "bg-blue-950/80 text-blue-300 border border-blue-700/60"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Active Positions ({positions.length})
                </button>
                <button
                  onClick={() => setActiveTab("journal")}
                  className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                    activeTab === "journal"
                      ? "bg-blue-950/80 text-blue-300 border border-blue-700/60"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Session Journal ({trades.length})
                </button>
              </div>

              {activeTab === "positions" ? (
                <PositionsTable positions={positions} onRefresh={fetchAllData} />
              ) : (
                <TradeHistoryTable trades={trades} />
              )}
            </div>
          </div>

          {/* Right Column: Setup Proposal & Regime Intelligence */}
          <div className="flex flex-col gap-6">
            {/* Active Setup & One-Click ARM Card */}
            <StrategyProposalCard
              symbol={symbol}
              proposalData={proposal}
              safeMode={safeMode}
              onActionSuccess={fetchAllData}
            />

            {/* Market Regime & Choppiness Gauge */}
            <RegimeIntelligenceCard regime={regime} />
          </div>
        </div>
      </main>

      {/* Backtest Modal */}
      <BacktestModal
        isOpen={isBacktestOpen}
        onClose={() => setIsBacktestOpen(false)}
        activeSymbol={symbol}
      />
    </div>
  );
}

