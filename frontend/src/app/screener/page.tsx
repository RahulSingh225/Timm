'use client';

import { useEffect, useState } from 'react';
import { Radar, Target, Eye, Activity, ShieldAlert, ArrowUpRight, TrendingUp, TrendingDown } from 'lucide-react';

interface ScreenedStock {
  id: number;
  symbol: string;
  setupType: string;
  timeframe: string;
  tradeType: string;
  entryPrice: number;
  targetPrice: number | null;
  stoplossPrice: number | null;
  targetPct: number | null;
  riskPct: number | null;
  confidence: number;
  signals: string[];
  status: string;
  screenedAt: string;
}

export default function ScreenerPage() {
  const [stocks, setStocks] = useState<ScreenedStock[]>([]);
  const [loading, setLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState<number | null>(null);

  const fetchScreenedStocks = async () => {
    try {
      const res = await fetch('/api/screener/results?type=INTRADAY');
      const json = await res.json();
      if (json.success) {
        setStocks(json.data);
      }
    } catch (err) {
      console.error('Failed to fetch screener results', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScreenedStocks();
    const interval = setInterval(fetchScreenedStocks, 10000);
    return () => clearInterval(interval);
  }, []);

  const trackTrade = async (stock: ScreenedStock) => {
    setIsProcessing(stock.id);
    try {
      const res = await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: stock.symbol,
          tradeType: stock.tradeType,
          entryPrice: stock.entryPrice,
          stoploss: stock.stoplossPrice,
          target: stock.targetPrice,
          notes: `Auto-tracked from Screener. Setup: ${stock.setupType}`
        })
      });
      const data = await res.json();
      if (data.success) {
        // Optimistically update status to show it's tracked
        setStocks(stocks.map(s => s.id === stock.id ? { ...s, status: 'TRACKED' } : s));
      } else {
        alert("Failed to track trade.");
      }
    } catch (err) {
      console.error("Error tracking trade", err);
    } finally {
      setIsProcessing(null);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6 font-mono">
      {/* Header */}
      <header className="flex justify-between items-center border-b border-neutral-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <Radar className="text-blue-500" size={28} />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              Intraday Screener 
              <span className="bg-blue-500/10 text-blue-400 text-xs px-2 py-0.5 rounded border border-blue-500/20 font-normal">
                LIVE
              </span>
            </h1>
            <p className="text-neutral-500 text-sm mt-1">Autonomous setup detection for 2-3% momentum plays</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl overflow-hidden backdrop-blur-sm">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-neutral-900/80 border-b border-neutral-800 text-neutral-400 text-sm uppercase tracking-wider">
              <th className="p-4 font-medium">Symbol</th>
              <th className="p-4 font-medium">Setup</th>
              <th className="p-4 font-medium">Levels</th>
              <th className="p-4 font-medium text-center">R:R Profile</th>
              <th className="p-4 font-medium text-center">Confidence</th>
              <th className="p-4 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800/60">
            {loading && stocks.length === 0 && (
              <tr>
                <td colSpan={6} className="p-12 text-center text-neutral-500">
                  <Activity className="animate-pulse mx-auto mb-3" size={32} />
                  Scanning market for active setups...
                </td>
              </tr>
            )}
            {!loading && stocks.length === 0 && (
              <tr>
                <td colSpan={6} className="p-12 text-center text-neutral-500">
                  No intraday setups found. Waiting for market action.
                </td>
              </tr>
            )}
            {stocks.map((stock) => (
              <tr key={stock.id} className="hover:bg-neutral-800/30 transition-colors group">
                <td className="p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-neutral-800 border border-neutral-700 flex items-center justify-center font-bold text-neutral-300">
                      {stock.symbol.substring(0, 1)}
                    </div>
                    <div>
                      <div className="font-bold text-white text-lg">{stock.symbol}</div>
                      <div className="text-xs text-neutral-500 flex items-center gap-1 mt-0.5">
                        <ClockIcon size={10} /> {new Date(stock.screenedAt).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                </td>
                
                <td className="p-4">
                  <div className="inline-flex items-center gap-1.5 bg-neutral-800 px-2.5 py-1 rounded text-sm text-neutral-200 border border-neutral-700/50">
                    {stock.tradeType === 'INTRADAY' && stock.setupType.includes('BEAR') ? <TrendingDown size={14} className="text-red-400" /> : <TrendingUp size={14} className="text-emerald-400" />}
                    {stock.setupType.replace('_', ' ')}
                  </div>
                  <div className="text-xs text-neutral-500 mt-2 truncate w-48">
                    {stock.signals?.[0] || 'System identified pattern'}
                  </div>
                </td>

                <td className="p-4">
                  <div className="flex flex-col gap-1.5 text-sm">
                    <div className="flex items-center gap-2 text-neutral-300">
                      <span className="text-neutral-500 w-12">Entry</span> ₹{stock.entryPrice?.toFixed(2)}
                    </div>
                    <div className="flex items-center gap-2 text-emerald-400">
                      <span className="text-neutral-500 w-12">Target</span> ₹{stock.targetPrice?.toFixed(2)}
                    </div>
                    <div className="flex items-center gap-2 text-red-400">
                      <span className="text-neutral-500 w-12">SL</span> ₹{stock.stoplossPrice?.toFixed(2)}
                    </div>
                  </div>
                </td>

                <td className="p-4 text-center">
                  <div className="inline-flex flex-col items-center bg-neutral-950/50 p-2 rounded border border-neutral-800/80">
                    <div className="text-xs text-emerald-400 font-bold mb-0.5">+{stock.targetPct?.toFixed(1)}%</div>
                    <div className="h-px w-8 bg-neutral-700 my-0.5" />
                    <div className="text-xs text-red-400 font-bold mt-0.5">-{stock.riskPct?.toFixed(1)}%</div>
                  </div>
                </td>

                <td className="p-4 text-center">
                  <div className="flex flex-col items-center">
                    <div className={`text-xl font-bold ${
                      stock.confidence > 70 ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]' :
                      stock.confidence > 40 ? 'text-yellow-400' : 'text-neutral-400'
                    }`}>
                      {stock.confidence}
                    </div>
                    <div className="text-[10px] text-neutral-500 uppercase">Score</div>
                  </div>
                </td>

                <td className="p-4 text-right">
                  {stock.status === 'TRACKED' ? (
                    <button disabled className="bg-neutral-800 text-neutral-400 border border-neutral-700 px-4 py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 ml-auto cursor-not-allowed">
                      <Eye size={16} /> Tracked
                    </button>
                  ) : (
                    <button 
                      onClick={() => trackTrade(stock)}
                      disabled={isProcessing === stock.id}
                      className="bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.3)] hover:shadow-[0_0_20px_rgba(59,130,246,0.5)] px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ml-auto hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0"
                    >
                      {isProcessing === stock.id ? (
                        <Activity className="animate-spin" size={16} /> 
                      ) : (
                        <Target size={16} /> 
                      )}
                      Track Trade
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Helper icon component
function ClockIcon({ size }: { size: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}
