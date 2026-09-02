import React from 'react';
import { History } from 'lucide-react';

interface DecisionRecord {
  timestamp: string;
  symbol: string;
  action: string;
  price: string;
  rsi14: string;
  trend_bias: string;
  divergence: string;
  news_sentiment: string;
  reasoning: string;
  confidence: string;
}

interface DecisionLogProps {
  decisions: DecisionRecord[];
}

export const DecisionLog: React.FC<DecisionLogProps> = ({ decisions }) => {
  return (
    <div className="glass-panel p-5 rounded-xl">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#262C3A]">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-[#ab47bc]" />
          <h2 className="text-base font-bold text-white m-0">Agent Execution Audit Log</h2>
        </div>
        <span className="text-xs text-gray-400 font-mono">Recent Decisions</span>
      </div>

      {decisions.length === 0 ? (
        <div className="text-center py-6 text-gray-500 text-sm">
          No decision history logged yet. Run a daily paper-trading pass to populate logs.
        </div>
      ) : (
        <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-[#151921] z-10">
              <tr className="border-b border-[#262C3A] text-xs font-semibold text-gray-400 uppercase">
                <th className="pb-2 px-3">Time</th>
                <th className="pb-2 px-3">Asset</th>
                <th className="pb-2 px-3">Action</th>
                <th className="pb-2 px-3">Price</th>
                <th className="pb-2 px-3">Conviction</th>
                <th className="pb-2 px-3">Audit Rationale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#262C3A]/50 text-xs">
              {decisions.map((item, idx) => {
                const act = item.action?.toUpperCase() || 'HOLD';
                let actColor = 'bg-gray-800 text-gray-300 border-gray-700';
                if (act === 'BUY') actColor = 'bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30';
                if (act === 'SELL') actColor = 'bg-[#FF5252]/15 text-[#FF5252] border-[#FF5252]/30';

                const timeStr = item.timestamp
                  ? new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : 'Recent';

                return (
                  <tr key={idx} className="hover:bg-[#1E232F]/50 transition-colors">
                    <td className="py-2.5 px-3 font-mono text-gray-400 whitespace-nowrap">
                      {timeStr}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-white">
                      {item.symbol}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded border text-[11px] font-bold ${actColor}`}>
                        {act}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-gray-200">
                      ${Number(item.price).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 font-mono font-bold text-[#29b6f6]">
                      {(Number(item.confidence) * 100).toFixed(0)}%
                    </td>
                    <td className="py-2.5 px-3 text-gray-300 max-w-md truncate" title={item.reasoning}>
                      {item.reasoning}
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
