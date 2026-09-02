import { useEffect, useState } from 'react';
import { Header } from './components/Header';
import { PortfolioCards } from './components/PortfolioCards';
import { TradingViewChart } from './components/TradingViewChart';
import { OpenPositionsTable } from './components/OpenPositionsTable';
import { MarketWatchlist } from './components/MarketWatchlist';
import { DecisionLog } from './components/DecisionLog';
import { RefreshCw, CheckCircle } from 'lucide-react';

export function App() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('SOLUSDT');
  const [portfolio, setPortfolio] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [watchlist, setWatchlist] = useState<Record<string, any>>({});
  const [marketContext, setMarketContext] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      // 1. Fetch Portfolio
      const resPort = await fetch('http://localhost:5000/api/portfolio');
      if (resPort.ok) {
        const pData = await resPort.json();
        setPortfolio(pData);
      }

      // 2. Fetch Open Positions
      const resPos = await fetch('http://localhost:5000/api/open-positions');
      if (resPos.ok) {
        const posData = await resPos.json();
        setPositions(posData);
      }

      // 3. Fetch Decision Log
      const resDec = await fetch('http://localhost:5000/api/decision-log');
      if (resDec.ok) {
        const decData = await resDec.json();
        setDecisions(decData);
      }

      // 4. Fetch Market TA Research
      const resTA = await fetch('http://localhost:5000/api/market-research');
      if (resTA.ok) {
        const taData = await resTA.json();
        setWatchlist(taData.technical_analysis || {});
        setMarketContext(taData.market_context || {});
      }

      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchDashboardData, 60000);
    return () => clearInterval(interval);
  }, []);

  const handleRunAgent = async () => {
    setIsExecuting(true);
    try {
      const res = await fetch('http://localhost:5000/api/run-agent', { method: 'POST' });
      if (res.ok) {
        await fetchDashboardData();
      }
    } catch (err) {
      console.error('Error running agent pass:', err);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0E14] text-gray-100 p-4 sm:p-6 font-sans">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <Header
          onRunAgent={handleRunAgent}
          isExecuting={isExecuting}
          marketRegime={marketContext?.market_regime}
          fearAndGreed={marketContext?.fear_and_greed}
        />

        {/* Portfolio Stats Header */}
        <PortfolioCards portfolio={portfolio} openPositionsCount={positions.length} />

        {/* Main Grid Section: Chart & Open Positions (Left) vs Watchlist (Right) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
          {/* Left Column - 8 Cols */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <TradingViewChart symbol={selectedSymbol} onSymbolChange={setSelectedSymbol} />
            <OpenPositionsTable positions={positions} onSelectSymbol={setSelectedSymbol} />
          </div>

          {/* Right Column - 4 Cols */}
          <div className="lg:col-span-4 flex flex-col">
            <MarketWatchlist
              watchlist={watchlist}
              onSelectSymbol={setSelectedSymbol}
              selectedSymbol={selectedSymbol}
            />
          </div>
        </div>

        {/* Bottom Section: Decision History */}
        <div className="mb-6">
          <DecisionLog decisions={decisions} />
        </div>

        {/* Footer */}
        <footer className="glass-panel p-4 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs text-gray-400">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-[#00E676]" />
            <span>State synchronized with <code className="text-[#29b6f6]">state/portfolio.json</code> & <code className="text-[#29b6f6]">trade_log.csv</code></span>
          </div>
          <div className="flex items-center gap-4 font-mono">
            <span>Last Updated: {lastRefreshed || 'Just now'}</span>
            <button
              onClick={fetchDashboardData}
              className="hover:text-white flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin text-[#29b6f6]' : ''}`} /> Refresh
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

export default App;
