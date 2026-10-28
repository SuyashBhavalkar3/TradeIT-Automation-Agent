"use client";

import React, { useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, LineStyle } from "lightweight-charts";
import { CandleData } from "@/lib/api";

interface Props {
  symbol: string;
  candles: CandleData[];
  indicators?: {
    vwap: number;
    vwap_upper: number;
    vwap_lower: number;
    rsi?: number;
    atr?: number;
  } | null;
  targetPrice?: number;
  stopLossPrice?: number;
  entryPrice?: number;
}

export default function TradingViewChart({
  symbol,
  candles,
  indicators,
  targetPrice,
  stopLossPrice,
  entryPrice,
}: Props) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const vwapLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const upperBandRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lowerBandRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Create TradingView Chart instance
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 420,
      layout: {
        background: { color: "#0d1117" },
        textColor: "#9ca3af",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "#1e293b", style: LineStyle.SparseDotted },
        horzLines: { color: "#1e293b", style: LineStyle.SparseDotted },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: "#475569", width: 1, style: LineStyle.Dashed },
        horzLine: { color: "#475569", width: 1, style: LineStyle.Dashed },
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#334155",
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
    });

    // Candlestick Series
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    // VWAP & Bands Lines
    const vwapLine = chart.addLineSeries({
      color: "#3b82f6",
      lineWidth: 2,
      title: "VWAP",
    });

    const upperBand = chart.addLineSeries({
      color: "#60a5fa",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: "+2σ Band",
    });

    const lowerBand = chart.addLineSeries({
      color: "#60a5fa",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: "-2σ Band",
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    vwapLineRef.current = vwapLine;
    upperBandRef.current = upperBand;
    lowerBandRef.current = lowerBand;

    // Resize listener
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Update chart data whenever candles prop updates
  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return;

    // Format & sort data ascending
    const sorted = [...candles].sort((a, b) => a.time - b.time);
    // Deduplicate by time
    const deduped: CandleData[] = [];
    const seen = new Set<number>();
    for (const c of sorted) {
      if (!seen.has(c.time)) {
        seen.add(c.time);
        deduped.push(c);
      }
    }

    candleSeriesRef.current.setData(
      deduped.map((c) => ({
        time: c.time as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    // If VWAP indicator is available, draw horizontal reference lines or trailing series
    if (indicators && vwapLineRef.current && upperBandRef.current && lowerBandRef.current) {
      const vwapData = deduped.map((c) => ({
        time: c.time as any,
        value: indicators.vwap,
      }));
      const upData = deduped.map((c) => ({
        time: c.time as any,
        value: indicators.vwap_upper,
      }));
      const dnData = deduped.map((c) => ({
        time: c.time as any,
        value: indicators.vwap_lower,
      }));

      vwapLineRef.current.setData(vwapData);
      upperBandRef.current.setData(upData);
      lowerBandRef.current.setData(dnData);
    }
  }, [candles, indicators]);

  // Set visual overlay lines for Stop Loss, Target, and Entry
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    const series = candleSeriesRef.current;

    // Remove any previously added price lines if necessary or set new ones
    let entryLine: any = null;
    let slLine: any = null;
    let targetLine: any = null;

    if (entryPrice) {
      entryLine = series.createPriceLine({
        price: entryPrice,
        color: "#f59e0b",
        lineWidth: 2,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "ENTRY",
      });
    }

    if (stopLossPrice) {
      slLine = series.createPriceLine({
        price: stopLossPrice,
        color: "#ef4444",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "STOP LOSS",
      });
    }

    if (targetPrice) {
      targetLine = series.createPriceLine({
        price: targetPrice,
        color: "#10b981",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "TARGET",
      });
    }

    return () => {
      try {
        if (entryLine) series.removePriceLine(entryLine);
        if (slLine) series.removePriceLine(slLine);
        if (targetLine) series.removePriceLine(targetLine);
      } catch (e) {
        // Ignore if already disposed
      }
    };
  }, [entryPrice, stopLossPrice, targetPrice]);

  return (
    <div className="relative w-full rounded-xl bg-card border border-cardBorder overflow-hidden p-4 shadow-xl">
      <div className="flex items-center justify-between pb-3 border-b border-cardBorder mb-3">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg text-white tracking-wide">{symbol}</span>
          <span className="text-xs px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800 font-mono">
            1M Timeframe
          </span>
          <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
            Real Live NSE Feed
          </span>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          {indicators && (
            <>
              <span className="text-blue-400">VWAP: ₹{indicators.vwap}</span>
              <span className="text-slate-400">+2σ: ₹{indicators.vwap_upper}</span>
              <span className="text-slate-400">-2σ: ₹{indicators.vwap_lower}</span>
              <span className="text-purple-400">RSI: {indicators.rsi}</span>
            </>
          )}
        </div>
      </div>

      <div ref={chartContainerRef} className="w-full h-[420px]" />
    </div>
  );
}
