import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';
import { RefreshCw, ShieldAlert, BarChart2 } from 'lucide-react';

interface TradingViewChartProps {
  symbol: string;
  onSymbolChange?: (symbol: string) => void;
}

export const TradingViewChart: React.FC<TradingViewChartProps> = ({ symbol, onSymbolChange }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  
  const [loading, setLoading] = useState<boolean>(true);
  const [interval, setInterval] = useState<string>('1d');
  const [error, setError] = useState<string | null>(null);
  const [lastCandle, setLastCandle] = useState<CandlestickData<Time> | null>(null);

  const availableSymbols = [
    { label: 'Solana (SOL)', ticker: 'SOLUSDT' },
    { label: 'Bitcoin (BTC)', ticker: 'BTCUSDT' },
    { label: 'Ethereum (ETH)', ticker: 'ETHUSDT' },
    { label: 'Near Protocol (NEAR)', ticker: 'NEARUSDT' },
    { label: 'Polkadot (DOT)', ticker: 'DOTUSDT' },
    { label: 'Uniswap (UNI)', ticker: 'UNIUSDT' },
    { label: 'Arbitrum (ARB)', ticker: 'ARBUSDT' },
    { label: 'Chainlink (LINK)', ticker: 'LINKUSDT' },
    { label: 'Avalanche (AVAX)', ticker: 'AVAXUSDT' },
    { label: 'Cardano (ADA)', ticker: 'ADAUSDT' },
  ];

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Create TradingView Lightweight Chart instance
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#151921' },
        textColor: '#9CA3AF',
      },
      grid: {
        vertLines: { color: 'rgba(38, 44, 58, 0.5)' },
        horzLines: { color: 'rgba(38, 44, 58, 0.5)' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 420,
      timeScale: {
        borderColor: '#262C3A',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#262C3A',
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00E676',
      downColor: '#FF5252',
      borderVisible: false,
      wickUpColor: '#00E676',
      wickDownColor: '#FF5252',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candlestickSeries;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // Fetch candle data when symbol or interval changes
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    fetch(`http://localhost:5000/api/klines?symbol=${symbol}&interval=${interval}&limit=120`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: CandlestickData<Time>[]) => {
        if (!isMounted || !candleSeriesRef.current) return;
        
        if (Array.isArray(data) && data.length > 0) {
          candleSeriesRef.current.setData(data);
          setLastCandle(data[data.length - 1]);
          if (chartRef.current) {
            chartRef.current.timeScale().fitContent();
          }
        }
        setLoading(false);
      })
      .catch((err) => {
        if (isMounted) {
          setError(`Failed to load chart for ${symbol}: ${err.message}`);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [symbol, interval]);

  return (
    <div className="glass-panel p-5 rounded-xl flex flex-col h-full">
      {/* Chart Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 border-b border-[#262C3A] pb-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#29b6f6]/10 rounded-lg text-[#29b6f6]">
            <BarChart2 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <select
                value={symbol}
                onChange={(e) => onSymbolChange && onSymbolChange(e.target.value)}
                className="bg-[#1E232F] text-white font-bold text-lg rounded-md px-3 py-1 border border-[#262C3A] focus:outline-none focus:border-[#29b6f6] cursor-pointer"
              >
                {availableSymbols.map((s) => (
                  <option key={s.ticker} value={s.ticker}>
                    {s.label}
                  </option>
                ))}
              </select>
              <span className="text-xs px-2 py-0.5 rounded bg-[#00E676]/10 text-[#00E676] font-semibold border border-[#00E676]/30">
                Binance Futures
              </span>
            </div>
          </div>
        </div>

        {/* Timeframe Controls & Prices */}
        <div className="flex items-center gap-4">
          {lastCandle && (
            <div className="text-right">
              <div className="text-sm font-semibold text-white">
                ${Number(lastCandle.close).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
              </div>
              <div className="text-xs text-gray-400">Latest Close</div>
            </div>
          )}

          <div className="flex bg-[#1E232F] p-1 rounded-lg border border-[#262C3A]">
            {['1d', '4h', '1h'].map((tf) => (
              <button
                key={tf}
                onClick={() => setInterval(tf)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  interval === tf
                    ? 'bg-[#29b6f6] text-black shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            onClick={() => setInterval((prev) => prev)}
            className="p-2 hover:bg-[#1E232F] rounded-lg text-gray-400 hover:text-white transition-colors"
            title="Refresh Chart"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#29b6f6]' : ''}`} />
          </button>
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div className="relative flex-1 min-h-[380px] w-full">
        {loading && (
          <div className="absolute inset-0 bg-[#151921]/80 backdrop-blur-sm z-10 flex items-center justify-center">
            <div className="flex items-center gap-2 text-[#29b6f6] font-medium text-sm">
              <RefreshCw className="w-5 h-5 animate-spin" /> Loading TradingView Engine...
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 bg-[#151921]/90 z-10 flex items-center justify-center p-4">
            <div className="text-center text-red-400 max-w-md">
              <ShieldAlert className="w-8 h-8 mx-auto mb-2 opacity-80" />
              <p className="text-sm font-medium">{error}</p>
            </div>
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full rounded-lg overflow-hidden" />
      </div>
    </div>
  );
};
