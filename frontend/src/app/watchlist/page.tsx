'use client';

import { useState, useEffect } from 'react';
import { 
  List, 
  Plus, 
  Trash2, 
  Power, 
  PowerOff, 
  ExternalLink,
  Search,
  Activity,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { Navigation } from '@/components/Navigation';

interface WatchlistItem {
  id: number;
  symbol: string;
  assetType: string;
  isActive: boolean;
  addedAt: string;
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [assetType, setAssetType] = useState('EQUITY');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchWatchlist();
  }, []);

  const fetchWatchlist = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/watchlist');
      const json = await res.json();
      if (json.success) {
        setItems(json.data);
      } else {
        setError(json.error);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol) return;

    try {
      setSubmitting(true);
      setError(null);
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: newSymbol, asset_type: assetType }),
      });
      const json = await res.json();
      
      if (json.success) {
        setNewSymbol('');
        fetchWatchlist();
      } else {
        setError(json.error);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggle = async (id: number, currentStatus: boolean) => {
    try {
      const res = await fetch('/api/watchlist', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, is_active: !currentStatus }),
      });
      const json = await res.json();
      if (json.success) {
        setItems(items.map(item => item.id === id ? { ...item, isActive: !currentStatus } : item));
      }
    } catch (err: any) {
      console.error('Toggle failed:', err);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to remove this symbol?')) return;
    
    try {
      const res = await fetch('/api/watchlist', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
      const json = await res.json();
      if (json.success) {
        setItems(items.filter(item => item.id !== id));
      }
    } catch (err: any) {
      console.error('Delete failed:', err);
    }
  };

  const getTvUrl = (symbol: string) => {
    // Basic mapping for Indian markets
    const cleanSym = symbol.toUpperCase().replace('.NS', '').replace('.BO', '');
    if (['NIFTY', 'BANKNIFTY', 'CNXFINANCE'].includes(cleanSym)) {
      return `https://www.tradingview.com/chart/?symbol=NSE:${cleanSym}`;
    }
    if (cleanSym === 'SENSEX') {
      return `https://www.tradingview.com/chart/?symbol=BSE:SENSEX`;
    }
    return `https://www.tradingview.com/chart/?symbol=NSE:${cleanSym}`;
  };

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-200 font-sans selection:bg-purple-500/30">
      <Navigation />
      
      <div className="max-w-screen-xl mx-auto p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <List className="text-purple-500" /> Dynamic Watchlist
            </h1>
            <p className="text-neutral-500 mt-1">Manage symbols for the Agentic Brain to analyze.</p>
          </div>
          
          <div className="flex items-center gap-2 text-xs font-mono bg-neutral-900 border border-neutral-800 px-3 py-1.5 rounded-full text-neutral-400">
            <Activity size={12} className="text-emerald-500" />
            {items.filter(i => i.isActive).length} Active Bots
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-400 text-sm">
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Add Symbol Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6 sticky top-24">
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Plus size={18} className="text-purple-500" /> Add Symbol
              </h2>
              
              <form onSubmit={handleAdd} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-neutral-500 uppercase mb-1.5 ml-1">Symbol</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600" size={16} />
                    <input 
                      type="text"
                      placeholder="e.g. RELIANCE"
                      value={newSymbol}
                      onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-xl py-2.5 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500/50 transition-all text-white placeholder:text-neutral-700"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-500 uppercase mb-1.5 ml-1">Type</label>
                  <select 
                    value={assetType}
                    onChange={(e) => setAssetType(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500/50 transition-all text-white"
                  >
                    <option value="EQUITY">Equity (NSE)</option>
                    <option value="INDEX">Index</option>
                    <option value="COMMODITY">Commodity</option>
                  </select>
                </div>

                <button 
                  disabled={submitting}
                  className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl transition-all flex items-center justify-center gap-2 shadow-lg shadow-purple-900/20"
                >
                  {submitting ? <Loader2 className="animate-spin" size={18} /> : <Plus size={18} />}
                  Add to Queue
                </button>
              </form>

              <div className="mt-6 pt-6 border-t border-neutral-800 text-[10px] text-neutral-600 leading-relaxed italic">
                Note: Symbols added here will be automatically included in the next Pre-Market and EOD analysis cycles.
              </div>
            </div>
          </div>

          {/* List Main View */}
          <div className="lg:col-span-3">
            <div className="bg-neutral-900/30 border border-neutral-800 rounded-2xl overflow-hidden backdrop-blur-sm">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-neutral-800 bg-neutral-900/50 text-xs font-semibold text-neutral-500 uppercase tracking-wider">
                    <th className="px-6 py-4">Symbol</th>
                    <th className="px-6 py-4">Type</th>
                    <th className="px-6 py-4">Status</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {loading ? (
                    <tr>
                      <td colSpan={4} className="px-6 py-20 text-center">
                        <Loader2 className="animate-spin mx-auto text-purple-500" size={32} />
                        <p className="text-neutral-500 mt-4 text-sm font-mono tracking-widest">Compiling Watchlist...</p>
                      </td>
                    </tr>
                  ) : items.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-6 py-20 text-center">
                        <p className="text-neutral-500 text-sm italic">Watchlist is currently empty. Add a symbol to begin.</p>
                      </td>
                    </tr>
                  ) : (
                    items.map((item) => (
                      <tr key={item.id} className="hover:bg-neutral-800/20 transition-colors group">
                        <td className="px-6 py-4 font-bold text-white tracking-widest">
                          {item.symbol}
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-[10px] bg-neutral-800 text-neutral-400 px-2 py-0.5 rounded border border-neutral-700">
                            {item.assetType}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <button 
                            onClick={() => handleToggle(item.id, item.isActive)}
                            className={`flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full transition-all
                              ${item.isActive 
                                ? 'text-emerald-400 bg-emerald-400/10 hover:bg-emerald-400/20 border border-emerald-400/20' 
                                : 'text-neutral-500 bg-neutral-800/50 hover:bg-neutral-800 border border-neutral-700'
                              }`}
                          >
                            {item.isActive ? <Power size={14} /> : <PowerOff size={14} />}
                            {item.isActive ? 'Active' : 'Paused'}
                          </button>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-3 opacity-60 group-hover:opacity-100 transition-opacity">
                            <a 
                              href={getTvUrl(item.symbol)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-2 hover:bg-blue-500/10 hover:text-blue-400 rounded-lg transition-all text-neutral-500"
                              title="View TradingView Chart"
                            >
                              <ExternalLink size={18} />
                            </a>
                            <button 
                              onClick={() => handleDelete(item.id)}
                              className="p-2 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-all text-neutral-500"
                              title="Remove Symbol"
                            >
                              <Trash2 size={18} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            
            <div className="mt-4 flex items-center justify-end gap-2 text-[10px] text-neutral-600">
              <AlertCircle size={10} />
              Indices like NIFTY and BANKNIFTY are automatically mapped to TradingView's NSE symbols.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
