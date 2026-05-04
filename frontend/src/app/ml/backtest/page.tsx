'use client';

import { useEffect, useState } from 'react';
import { BarChart3, TrendingUp, TrendingDown, Activity, RefreshCw, Calendar, Target, AlertTriangle } from 'lucide-react';

interface BacktestRun {
  id: number;
  start_date: string;
  end_date: string;
  total_days: number;
  total_trades: number;
  total_return: number;
  annualized_return: number;
  sharpe: number;
  calmar: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  max_consecutive_losses: number;
  transaction_costs_total: number;
  regime_breakdown: Record<string, { trades: number; wins: number; win_rate: number; avg_pnl: number }>;
  monthly_returns: Record<string, number>;
  equity_curve: Array<{ idx: number; equity: number }>;
  created_at: string;
}

function MetricCard({ label, value, suffix, positive, icon: Icon }: {
  label: string; value: string | number; suffix?: string;
  positive?: boolean | null; icon?: any;
}) {
  const colorClass = positive === true ? 'text-emerald-400' : positive === false ? 'text-red-400' : 'text-white';
  return (
    <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
      <div className="flex items-center gap-2 text-xs text-neutral-500 mb-2">
        {Icon && <Icon size={14} />} {label}
      </div>
      <div className={`text-2xl font-bold ${colorClass}`}>
        {value}<span className="text-sm text-neutral-500 ml-1">{suffix}</span>
      </div>
    </div>
  );
}

export default function BacktestDashboard() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/ml?endpoint=backtest');
      const json = await res.json();
      if (json.runs) {
        setRuns(json.runs);
        if (json.runs.length > 0 && !selected) setSelected(json.runs[0]);
      }
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin text-neutral-500" size={24} /></div>;
  }

  const run = selected;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtest Results</h1>
          <p className="text-sm text-neutral-500 mt-1">Historical simulation with transaction costs</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selected?.id || ''}
            onChange={(e) => setSelected(runs.find(r => r.id === Number(e.target.value)) || null)}
            className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-300"
          >
            {runs.map(r => (
              <option key={r.id} value={r.id}>
                Run #{r.id}: {r.start_date} → {r.end_date}
              </option>
            ))}
            {runs.length === 0 && <option>No runs available</option>}
          </select>
          <button onClick={fetchData} className="px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-neutral-400 hover:text-white transition-all text-sm flex items-center gap-2">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {!run ? (
        <div className="border border-dashed border-neutral-800 rounded-xl p-12 text-center text-neutral-500">
          <BarChart3 size={32} className="mx-auto mb-3 opacity-50" />
          <p>No backtest runs found. Run <code className="text-cyan-400">python simulate_graph.py --start-date 2024-01-01 --end-date 2025-12-31</code></p>
        </div>
      ) : (
        <>
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <MetricCard label="Total Return" value={(run.total_return * 100).toFixed(1)} suffix="%" positive={run.total_return > 0} icon={TrendingUp} />
            <MetricCard label="Sharpe Ratio" value={run.sharpe.toFixed(2)} positive={run.sharpe > 0.5 ? true : run.sharpe < 0 ? false : null} icon={Target} />
            <MetricCard label="Calmar Ratio" value={run.calmar.toFixed(2)} positive={run.calmar > 1} icon={Activity} />
            <MetricCard label="Max Drawdown" value={(run.max_drawdown * 100).toFixed(1)} suffix="%" positive={run.max_drawdown < 0.1 ? true : false} icon={TrendingDown} />
            <MetricCard label="Win Rate" value={(run.win_rate * 100).toFixed(0)} suffix="%" positive={run.win_rate > 0.55} icon={Target} />
            <MetricCard label="Profit Factor" value={run.profit_factor.toFixed(2)} positive={run.profit_factor > 1.5} icon={BarChart3} />
          </div>

          {/* Secondary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard label="Total Trades" value={run.total_trades} icon={Calendar} />
            <MetricCard label="Total Days" value={run.total_days} icon={Calendar} />
            <MetricCard label="Avg Win" value={(run.avg_win * 100).toFixed(2)} suffix="%" positive={true} />
            <MetricCard label="Avg Loss" value={(run.avg_loss * 100).toFixed(2)} suffix="%" positive={false} />
            <MetricCard label="Max Consec Losses" value={run.max_consecutive_losses} positive={run.max_consecutive_losses < 5 ? true : false} icon={AlertTriangle} />
          </div>

          {/* Equity Curve */}
          {run.equity_curve && run.equity_curve.length > 0 && (
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-neutral-300 mb-4 flex items-center gap-2">
                <TrendingUp size={16} className="text-cyan-400" /> Equity Curve
              </h3>
              <div className="h-48 flex items-end gap-px">
                {(() => {
                  const eq = run.equity_curve;
                  const minE = Math.min(...eq.map(e => e.equity));
                  const maxE = Math.max(...eq.map(e => e.equity));
                  const range = maxE - minE || 1;
                  // Sample to max 200 bars
                  const step = Math.max(1, Math.floor(eq.length / 200));
                  const sampled = eq.filter((_, i) => i % step === 0);

                  return sampled.map((point, i) => {
                    const height = ((point.equity - minE) / range) * 100;
                    const isGreen = point.equity >= (sampled[0]?.equity || 100000);
                    return (
                      <div
                        key={i}
                        className={`flex-1 rounded-t-sm transition-all ${isGreen ? 'bg-emerald-500/60' : 'bg-red-500/60'}`}
                        style={{ height: `${Math.max(height, 2)}%` }}
                        title={`₹${point.equity.toLocaleString()}`}
                      />
                    );
                  });
                })()}
              </div>
              <div className="flex justify-between text-xs text-neutral-600 mt-2">
                <span>₹{run.equity_curve[0]?.equity.toLocaleString()}</span>
                <span>₹{run.equity_curve[run.equity_curve.length - 1]?.equity.toLocaleString()}</span>
              </div>
            </div>
          )}

          {/* Two-column: Monthly Returns + Regime Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Monthly Returns Heatmap */}
            {run.monthly_returns && (
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-neutral-300 mb-4 flex items-center gap-2">
                  <Calendar size={16} className="text-amber-400" /> Monthly Returns
                </h3>
                <div className="grid grid-cols-4 gap-2">
                  {Object.entries(run.monthly_returns).map(([month, ret]) => (
                    <div
                      key={month}
                      className={`p-2 rounded-lg text-center text-xs border ${
                        ret > 2 ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-300' :
                        ret > 0 ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                        ret > -2 ? 'bg-red-500/10 border-red-500/20 text-red-400' :
                        'bg-red-500/20 border-red-500/30 text-red-300'
                      }`}
                    >
                      <div className="text-neutral-500 text-[10px]">{month}</div>
                      <div className="font-bold">{ret > 0 ? '+' : ''}{ret.toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Regime Performance */}
            {run.regime_breakdown && (
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-neutral-300 mb-4 flex items-center gap-2">
                  <Activity size={16} className="text-purple-400" /> Performance by Regime
                </h3>
                <div className="space-y-3">
                  {Object.entries(run.regime_breakdown).map(([regime, stats]) => (
                    <div key={regime} className="bg-neutral-800/50 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-neutral-300">{regime}</span>
                        <span className="text-xs text-neutral-500">{stats.trades} trades</span>
                      </div>
                      <div className="flex items-center gap-4 text-xs">
                        <span className={stats.win_rate > 0.55 ? 'text-emerald-400' : 'text-red-400'}>
                          WR: {(stats.win_rate * 100).toFixed(0)}%
                        </span>
                        <span className={stats.avg_pnl > 0 ? 'text-emerald-400' : 'text-red-400'}>
                          Avg: {stats.avg_pnl > 0 ? '+' : ''}{stats.avg_pnl.toFixed(2)}%
                        </span>
                        <div className="flex-1 bg-neutral-700 rounded-full h-1.5">
                          <div
                            className={`h-full rounded-full ${stats.win_rate > 0.55 ? 'bg-emerald-500' : 'bg-red-500'}`}
                            style={{ width: `${stats.win_rate * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
