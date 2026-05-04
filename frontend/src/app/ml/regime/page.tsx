'use client';

import { useEffect, useState } from 'react';
import { Activity, TrendingUp, TrendingDown, Zap, BarChart3, Shield, RefreshCw } from 'lucide-react';

interface RegimeData {
  current: {
    regime_label: string;
    confidence: number;
    transition_probs: number[][];
    detected_at: string;
  };
  history: Array<{
    date: string;
    regime_label: string;
    confidence: number;
  }>;
  volatility: {
    vol_1d: number;
    vol_5d: number;
    iv_signal: string;
    vol_regime: string;
    expected_move_1d_pct: number;
  };
}

const REGIME_CONFIG: Record<string, { color: string; bg: string; border: string; icon: any; label: string }> = {
  TRENDING_BULL: {
    color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30',
    icon: TrendingUp, label: 'Trending Bull'
  },
  TRENDING_BEAR: {
    color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30',
    icon: TrendingDown, label: 'Trending Bear'
  },
  MEAN_REVERTING: {
    color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30',
    icon: BarChart3, label: 'Mean Reverting'
  },
  HIGH_VOL_EXPANSION: {
    color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/30',
    icon: Zap, label: 'High Vol Expansion'
  },
  UNKNOWN: {
    color: 'text-neutral-400', bg: 'bg-neutral-500/10', border: 'border-neutral-500/30',
    icon: Activity, label: 'Unknown'
  },
};

const REGIME_NAMES = ['Trending Bull', 'Trending Bear', 'Mean Reverting', 'High Vol'];

export default function RegimeDashboard() {
  const [data, setData] = useState<RegimeData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/ml?endpoint=regime');
      const json = await res.json();
      if (!json.error) setData(json);
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 30000); return () => clearInterval(i); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-neutral-500" size={24} />
      </div>
    );
  }

  const current = data?.current || { regime_label: 'UNKNOWN', confidence: 0, transition_probs: [], detected_at: '' };
  const config = REGIME_CONFIG[current.regime_label] || REGIME_CONFIG.UNKNOWN;
  const Icon = config.icon;
  const vol = data?.volatility;
  const history = data?.history || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Market Regime</h1>
          <p className="text-sm text-neutral-500 mt-1">HMM-detected regime with transition probabilities</p>
        </div>
        <button onClick={fetchData} className="px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-neutral-400 hover:text-white hover:border-neutral-600 transition-all text-sm flex items-center gap-2">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Current Regime Card */}
      <div className={`${config.bg} ${config.border} border rounded-xl p-6`}>
        <div className="flex items-center gap-4">
          <div className={`p-4 rounded-xl ${config.bg} border ${config.border}`}>
            <Icon size={32} className={config.color} />
          </div>
          <div className="flex-1">
            <div className="text-xs text-neutral-500 uppercase tracking-wider mb-1">Current Regime</div>
            <div className={`text-3xl font-bold ${config.color}`}>{config.label}</div>
            <div className="text-sm text-neutral-400 mt-1">
              Confidence: <span className="text-white font-semibold">{(current.confidence * 100).toFixed(0)}%</span>
              {current.detected_at && <span className="ml-3 text-neutral-600">Detected: {new Date(current.detected_at).toLocaleString()}</span>}
            </div>
          </div>
          {vol && (
            <div className="text-right">
              <div className="text-xs text-neutral-500 uppercase tracking-wider mb-1">Volatility</div>
              <div className="text-xl font-bold text-white">{vol.vol_regime}</div>
              <div className="text-xs text-neutral-400 mt-1">
                1D: {(vol.vol_1d * 100).toFixed(1)}% · 5D: {(vol.vol_5d * 100).toFixed(1)}%
              </div>
              <div className={`text-xs mt-1 ${vol.iv_signal === 'IV_PREMIUM' ? 'text-red-400' : vol.iv_signal === 'IV_DISCOUNT' ? 'text-emerald-400' : 'text-neutral-500'}`}>
                {vol.iv_signal?.replace('_', ' ')} · Move: ±{vol.expected_move_1d_pct?.toFixed(1)}%
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Two-column: Transition Matrix + Defense Mode */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Transition Probability Heatmap */}
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-neutral-300 mb-4 flex items-center gap-2">
            <Shield size={16} className="text-cyan-400" /> Transition Probabilities
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="p-2 text-left text-neutral-500">From ↓ To →</th>
                  {REGIME_NAMES.map(n => <th key={n} className="p-2 text-center text-neutral-500 font-medium">{n}</th>)}
                </tr>
              </thead>
              <tbody>
                {current.transition_probs?.map((row, i) => (
                  <tr key={i}>
                    <td className="p-2 font-medium text-neutral-400">{REGIME_NAMES[i]}</td>
                    {row.map((prob, j) => {
                      const intensity = Math.min(prob * 2, 1);
                      const isHighest = prob === Math.max(...row);
                      return (
                        <td key={j} className="p-2 text-center">
                          <span
                            className={`inline-block w-full py-1 rounded ${isHighest ? 'bg-cyan-500/20 text-cyan-300 font-bold' : 'text-neutral-500'}`}
                            style={{ opacity: 0.3 + intensity * 0.7 }}
                          >
                            {(prob * 100).toFixed(0)}%
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                )) || (
                  <tr><td colSpan={5} className="p-4 text-center text-neutral-600">No transition data</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Regime History Timeline */}
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-neutral-300 mb-4 flex items-center gap-2">
            <Activity size={16} className="text-purple-400" /> Regime Timeline (Last 30 Days)
          </h3>
          <div className="space-y-1.5 max-h-80 overflow-y-auto">
            {history.slice(0, 30).map((entry, i) => {
              const cfg = REGIME_CONFIG[entry.regime_label] || REGIME_CONFIG.UNKNOWN;
              return (
                <div key={i} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-neutral-800/50 transition-colors">
                  <span className="text-xs text-neutral-600 w-20 shrink-0 font-mono">{entry.date}</span>
                  <div className={`w-3 h-3 rounded-full ${cfg.bg} border ${cfg.border}`} />
                  <span className={`text-xs ${cfg.color} flex-1`}>{cfg.label}</span>
                  <span className="text-xs text-neutral-600">{(entry.confidence * 100).toFixed(0)}%</span>
                </div>
              );
            })}
            {history.length === 0 && (
              <div className="py-8 text-center text-neutral-600 text-xs">
                No regime history. Run the pre-market graph to generate data.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
