import React from 'react';
import { Play, ShieldCheck, Activity, Flame, Bot } from 'lucide-react';

interface HeaderProps {
  onRunAgent: () => void;
  isExecuting: boolean;
  marketRegime?: string;
  fearAndGreed?: { value: string; value_classification: string };
}

export const Header: React.FC<HeaderProps> = ({
  onRunAgent,
  isExecuting,
  marketRegime = 'bullish_trend',
  fearAndGreed = { value: '63', value_classification: 'Greed' }
}) => {
  return (
    <header className="glass-panel p-4 mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-[#262C3A]">
      {/* Brand Identity */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#29b6f6] to-[#ab47bc] flex items-center justify-center shadow-lg shadow-[#29b6f6]/20">
          <Bot className="w-6 h-6 text-black font-bold" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-white tracking-wide m-0">ANTItrading</h1>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-[#00E676]/10 text-[#00E676] border border-[#00E676]/30 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00E676] animate-pulse"></span> Live System
            </span>
          </div>
          <p className="text-xs text-gray-400 m-0">Shariah-Compliant Crypto Paper-Trading Engine</p>
        </div>
      </div>

      {/* Center Macro Indicators */}
      <div className="flex items-center gap-3">
        {/* Shariah Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1E232F] border border-[#262C3A]">
          <ShieldCheck className="w-4 h-4 text-[#00E676]" />
          <div>
            <div className="text-[10px] text-gray-400 uppercase font-semibold">Universe</div>
            <div className="text-xs font-bold text-gray-200">Shariah Verified</div>
          </div>
        </div>

        {/* Market Regime */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1E232F] border border-[#262C3A]">
          <Activity className="w-4 h-4 text-[#29b6f6]" />
          <div>
            <div className="text-[10px] text-gray-400 uppercase font-semibold">Market Regime</div>
            <div className="text-xs font-bold text-[#29b6f6] capitalize">
              {marketRegime.replace('_', ' ')}
            </div>
          </div>
        </div>

        {/* Fear & Greed */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1E232F] border border-[#262C3A]">
          <Flame className="w-4 h-4 text-amber-400" />
          <div>
            <div className="text-[10px] text-gray-400 uppercase font-semibold">Fear & Greed</div>
            <div className="text-xs font-bold text-amber-400">
              {fearAndGreed.value} ({fearAndGreed.value_classification})
            </div>
          </div>
        </div>
      </div>

      {/* Action Button */}
      <div>
        <button
          onClick={onRunAgent}
          disabled={isExecuting}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm transition-all duration-200 shadow-lg cursor-pointer ${
            isExecuting
              ? 'bg-gray-700 text-gray-400 cursor-not-allowed opacity-75'
              : 'bg-gradient-to-r from-[#00E676] to-[#00B0FF] text-black hover:brightness-110 shadow-[#00E676]/20 active:scale-95'
          }`}
        >
          {isExecuting ? (
            <>
              <span className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></span>
              Executing Trading Pass...
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-black" />
              Trigger Daily Trading Pass
            </>
          )}
        </button>
      </div>
    </header>
  );
};
