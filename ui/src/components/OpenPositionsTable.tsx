import React from 'react';
import { Target, Eye } from 'lucide-react';

interface Position {
  symbol: string;
  qty: number;
  entry_price: number;
  current_price: number;
  cost_basis: number;
  current_value: number;
  pnl_usd: number;
  pnl_pct: number;
  highest_price: number;
  trailing_stop_price: number;
  opened_at: string;
}

interface OpenPositionsTableProps {
  positions: Position[];
  onSelectSymbol: (symbol: string) => void;
}

export const OpenPositionsTable: React.FC<OpenPositionsTableProps> = ({ positions, onSelectSymbol }) => {
  return (
    <div className="glass-panel p-5 rounded-xl mb-6">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#262C3A]">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[#00E676] animate-pulse"></div>
          <h2 className="text-base font-bold text-white m-0">Active Portfolio Holdings</h2>
        </div>
        <span className="text-xs text-gray-400 font-mono">Dynamic ATR Trailing Stops Active</span>
      </div>

      {positions.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          No open positions. All funds holding in cash reserve.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#262C3A] text-xs font-semibold text-gray-400 uppercase tracking-wider">
                <th className="pb-3 px-3">Asset</th>
                <th className="pb-3 px-3">Quantity</th>
                <th className="pb-3 px-3">Entry Price</th>
                <th className="pb-3 px-3">Live Spot</th>
                <th className="pb-3 px-3">Cost Basis</th>
                <th className="pb-3 px-3">Current Value</th>
                <th className="pb-3 px-3">Unrealized P&L</th>
                <th className="pb-3 px-3">Trailing Stop</th>
                <th className="pb-3 px-3 text-right">Chart</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#262C3A]/50 text-sm">
              {positions.map((pos) => {
                const isPos = pos.pnl_usd >= 0;
                return (
                  <tr key={pos.symbol} className="hover:bg-[#1E232F]/60 transition-colors group">
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-2 font-bold text-white">
                        <span className="w-7 h-7 rounded-lg bg-[#262C3A] flex items-center justify-center text-xs text-[#29b6f6]">
                          {pos.symbol.substring(0, 3)}
                        </span>
                        {pos.symbol}
                      </div>
                    </td>
                    <td className="py-3.5 px-3 font-mono text-gray-300">
                      {pos.qty < 1 ? pos.qty.toFixed(4) : pos.qty.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-3 font-mono text-gray-300">
                      ${pos.entry_price < 1 ? pos.entry_price.toFixed(4) : pos.entry_price.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-3 font-mono font-semibold text-white">
                      ${pos.current_price < 1 ? pos.current_price.toFixed(4) : pos.current_price.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-3 font-mono text-gray-300">
                      ${pos.cost_basis.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-3 font-mono font-semibold text-gray-200">
                      ${pos.current_value.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-1 font-mono font-bold">
                        <span className={isPos ? 'text-[#00E676]' : 'text-[#FF5252]'}>
                          {isPos ? '+' : ''}${pos.pnl_usd.toFixed(2)} ({isPos ? '+' : ''}{pos.pnl_pct.toFixed(2)}%)
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-1 text-xs font-mono text-amber-400 bg-amber-500/10 px-2 py-1 rounded w-fit border border-amber-500/20">
                        <Target className="w-3.0 h-3.0" />
                        ${pos.trailing_stop_price < 1 ? pos.trailing_stop_price.toFixed(4) : pos.trailing_stop_price.toFixed(2)}
                      </div>
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <button
                        onClick={() => onSelectSymbol(`${pos.symbol}USDT`)}
                        className="p-1.5 rounded-lg bg-[#262C3A] text-gray-300 hover:text-white hover:bg-[#29b6f6] hover:text-black transition-colors"
                        title={`View ${pos.symbol} Chart`}
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
