import React from 'react';
import { DollarSign, TrendingUp, Wallet, Layers, ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface PortfolioCardsProps {
  portfolio: any;
  openPositionsCount: number;
}

export const PortfolioCards: React.FC<PortfolioCardsProps> = ({ portfolio, openPositionsCount }) => {
  const cash = portfolio?.cash ?? 7175.80;
  const startingCash = portfolio?.starting_cash ?? 10000.0;
  const metrics = portfolio?.metrics ?? {};
  
  // Calculate total portfolio value from equity history or cash + positions
  const latestEquity = portfolio?.equity_history?.[portfolio.equity_history.length - 1]?.portfolio_value ?? 10213.72;
  const totalPnl = latestEquity - startingCash;
  const totalPnlPct = (totalPnl / startingCash) * 100;
  const isPositive = totalPnl >= 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Portfolio Value */}
      <div className="glass-panel p-4 rounded-xl relative overflow-hidden group hover:border-[#29b6f6]/50 transition-all">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Total Portfolio Value</span>
          <div className="p-2 rounded-lg bg-[#29b6f6]/10 text-[#29b6f6]">
            <DollarSign className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-bold text-white tracking-tight">
          ${latestEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="flex items-center gap-1.5 mt-2 text-xs text-gray-400">
          <span>Starting:</span>
          <span className="font-semibold text-gray-300">${startingCash.toLocaleString()} USD</span>
        </div>
      </div>

      {/* Total Return P&L */}
      <div className="glass-panel p-4 rounded-xl relative overflow-hidden group hover:border-[#00E676]/50 transition-all">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Total Return (P&L)</span>
          <div className={`p-2 rounded-lg ${isPositive ? 'bg-[#00E676]/10 text-[#00E676]' : 'bg-[#FF5252]/10 text-[#FF5252]'}`}>
            <TrendingUp className="w-4 h-4" />
          </div>
        </div>
        <div className="flex items-baseline gap-2">
          <div className={`text-2xl font-bold tracking-tight ${isPositive ? 'text-[#00E676]' : 'text-[#FF5252]'}`}>
            {isPositive ? '+' : ''}${totalPnl.toFixed(2)}
          </div>
          <div className={`text-xs font-bold px-1.5 py-0.5 rounded flex items-center ${isPositive ? 'bg-[#00E676]/10 text-[#00E676]' : 'bg-[#FF5252]/10 text-[#FF5252]'}`}>
            {isPositive ? <ArrowUpRight className="w-3 h-3 mr-0.5" /> : <ArrowDownRight className="w-3 h-3 mr-0.5" />}
            {totalPnlPct.toFixed(2)}%
          </div>
        </div>
        <div className="text-xs text-gray-400 mt-2">
          Benchmark Return: <span className="text-gray-300 font-medium">+{metrics.benchmark_return_pct ?? 0.00}%</span>
        </div>
      </div>

      {/* Available Cash Balance */}
      <div className="glass-panel p-4 rounded-xl relative overflow-hidden group hover:border-[#ab47bc]/50 transition-all">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Cash Reserve</span>
          <div className="p-2 rounded-lg bg-[#ab47bc]/10 text-[#ab47bc]">
            <Wallet className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-bold text-white tracking-tight">
          ${cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="text-xs text-gray-400 mt-2">
          Cash Ratio: <span className="text-[#ab47bc] font-semibold">{((cash / latestEquity) * 100).toFixed(1)}%</span>
        </div>
      </div>

      {/* Active Positions & Risk Metrics */}
      <div className="glass-panel p-4 rounded-xl relative overflow-hidden group hover:border-amber-500/50 transition-all">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Active Positions</span>
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
            <Layers className="w-4 h-4" />
          </div>
        </div>
        <div className="flex items-baseline gap-2">
          <div className="text-2xl font-bold text-white tracking-tight">
            {openPositionsCount} <span className="text-sm font-normal text-gray-400">/ 6 Max</span>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
          <span>Max DD: <strong className="text-gray-300">{metrics.max_drawdown_pct ?? 0}%</strong></span>
          <span>•</span>
          <span>Sharpe: <strong className="text-gray-300">{metrics.sharpe_ratio ?? '0.00'}</strong></span>
        </div>
      </div>
    </div>
  );
};
