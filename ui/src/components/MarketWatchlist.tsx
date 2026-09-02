import React, { useState } from 'react';
import { Eye, ShieldCheck } from 'lucide-react';

interface WatchlistItem {
  name: string;
  symbol: string;
  ticker: string;
  price: number;
  rsi14: number;
  adx14: number;
  trend_bias: string;
  divergence: string;
  whale_alert: string;
  ob_imbalance_2pct: number;
  taker_ratio: number;
}

interface MarketWatchlistProps {
  watchlist: Record<string, WatchlistItem>;
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string;
}

export const MarketWatchlist: React.FC<MarketWatchlistProps> = ({ watchlist, onSelectSymbol, selectedSymbol }) => {
  const [search, setSearch] = useState('');

  const items = Object.values(watchlist).filter((item) => item.ticker && !('error' in item));

  const filteredItems = items.filter(
    (item) =>
      item.symbol.toLowerCase().includes(search.toLowerCase()) ||
      item.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="glass-panel p-5 rounded-xl flex flex-col h-full">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#262C3A]">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-[#00E676]" />
          <h2 className="text-base font-bold text-white m-0">Tracked Shariah Crypto Universe</h2>
        </div>
        <span className="text-xs text-gray-400 font-mono">{items.length} Assets Tracked</span>
      </div>

      {/* Search Input */}
      <div className="mb-3">
        <input
          type="text"
          placeholder="Search coin symbol (SOL, BTC, ETH...)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-[#1E232F] text-sm text-white px-3 py-2 rounded-lg border border-[#262C3A] focus:outline-none focus:border-[#29b6f6]"
        />
      </div>

      {/* Watchlist Table */}
      <div className="overflow-y-auto max-h-[440px] pr-1">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 bg-[#151921] z-10">
            <tr className="border-b border-[#262C3A] text-xs font-semibold text-gray-400 uppercase">
              <th className="pb-2 px-2">Asset</th>
              <th className="pb-2 px-2">Price</th>
              <th className="pb-2 px-2">RSI(14)</th>
              <th className="pb-2 px-2">1D Bias</th>
              <th className="pb-2 px-2">Whale Flow</th>
              <th className="pb-2 px-2 text-right">View</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#262C3A]/40 text-xs font-mono">
            {filteredItems.map((item) => {
              const isSelected = selectedSymbol === item.ticker;

              let whaleBadgeColor = 'bg-gray-800 text-gray-400';
              if (item.whale_alert === 'WHALE_ACCUMULATION' || item.whale_alert === 'BULLISH_WHALE_WALL') {
                whaleBadgeColor = 'bg-[#00E676]/15 text-[#00E676] border border-[#00E676]/30';
              } else if (item.whale_alert === 'WHALE_DISTRIBUTION' || item.whale_alert === 'BEARISH_WHALE_WALL') {
                whaleBadgeColor = 'bg-[#FF5252]/15 text-[#FF5252] border border-[#FF5252]/30';
              }

              let biasColor = 'text-gray-400';
              if (item.trend_bias === 'bullish') biasColor = 'text-[#00E676]';
              else if (item.trend_bias === 'bearish') biasColor = 'text-[#FF5252]';

              return (
                <tr
                  key={item.ticker}
                  onClick={() => onSelectSymbol(item.ticker)}
                  className={`hover:bg-[#1E232F] cursor-pointer transition-colors ${
                    isSelected ? 'bg-[#29b6f6]/10 border-l-2 border-[#29b6f6]' : ''
                  }`}
                >
                  <td className="py-2.5 px-2 font-sans font-bold text-white">
                    {item.symbol}
                  </td>
                  <td className="py-2.5 px-2 font-semibold text-gray-200">
                    ${item.price < 1 ? item.price.toFixed(4) : item.price.toLocaleString()}
                  </td>
                  <td className="py-2.5 px-2">
                    <span
                      className={
                        item.rsi14 > 65
                          ? 'text-amber-400 font-bold'
                          : item.rsi14 < 35
                          ? 'text-[#00E676] font-bold'
                          : 'text-gray-300'
                      }
                    >
                      {item.rsi14}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 font-semibold capitalize">
                    <span className={biasColor}>{item.trend_bias}</span>
                  </td>
                  <td className="py-2.5 px-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-sans font-bold ${whaleBadgeColor}`}>
                      {item.whale_alert.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-right">
                    <button
                      className={`p-1 rounded ${
                        isSelected ? 'bg-[#29b6f6] text-black' : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
