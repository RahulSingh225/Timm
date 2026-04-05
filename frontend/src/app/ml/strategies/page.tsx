"use client"
import { Play, TrendingUp, Cpu, Workflow } from 'lucide-react';
import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip } from 'recharts';

const mockStrategies = [
  { id: "GP_20260405_001", name: "Volatility Squeeze Alpha", sharpe: 2.84, dd: 4.2, winRate: 64, source: "Genetic Prog" },
  { id: "HYP_092", name: "Options IV Mean Revert", sharpe: 2.12, dd: 6.8, winRate: 58, source: "Qwen LLM" },
  { id: "GP_20260405_002", name: "Sector Rotation Proxy", sharpe: 1.95, dd: 3.1, winRate: 61, source: "Genetic Prog" },
  { id: "HYP_088", name: "Volume Breakout Z-Score", sharpe: 1.88, dd: 8.4, winRate: 52, source: "Qwen LLM" },
];

const mockRadarData1 = [
  { subject: 'Sharpe', A: 90, fullMark: 100 },
  { subject: 'Risk', A: 85, fullMark: 100 },
  { subject: 'Win Rate', A: 64, fullMark: 100 },
  { subject: 'Robustness', A: 75, fullMark: 100 },
  { subject: 'Profit Fac', A: 82, fullMark: 100 },
];

export default function StrategiesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Evolved Strategies Panel</h1>
          <p className="text-sm text-neutral-400 mt-1">Review top Genetic Programming trees and LLM-generated hypotheses.</p>
        </div>
        <div className="flex gap-2">
          <button className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-sm font-medium text-white rounded-lg transition-colors border border-neutral-700">
            Export JSON
          </button>
        </div>
      </div>

      {/* Top 2 Radar Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 flex">
          <div className="flex-1 pr-4">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 mb-3 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-400 text-xs font-semibold">
              <Workflow size={14} /> GP Winner
            </div>
            <h3 className="text-lg font-bold text-white mb-1">Volatility Squeeze Alpha</h3>
            <p className="text-xs text-neutral-500 mb-4 font-mono">GP_20260405_001</p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Sharpe Ratio</span>
                <span className="text-white font-medium">2.84</span>
              </div>
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Max Drawdown</span>
                <span className="text-emerald-400 font-medium">-4.2%</span>
              </div>
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Win Rate</span>
                <span className="text-white font-medium">64%</span>
              </div>
            </div>
          </div>
          <div className="w-1/2 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart cx="50%" cy="50%" outerRadius="70%" data={mockRadarData1}>
                <PolarGrid stroke="#404040" />
                <PolarAngleAxis dataKey="subject" tick={{fill: '#9ca3af', fontSize: 10}} />
                <Radar name="Strategy" dataKey="A" stroke="#818cf8" fill="#818cf8" fillOpacity={0.4} />
                <Tooltip contentStyle={{backgroundColor: '#171717', border: '1px solid #404040', color: '#fff'}} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 flex opacity-80 hover:opacity-100 transition-opacity">
          <div className="flex-1 pr-4">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 mb-3 rounded border border-violet-500/30 bg-violet-500/10 text-violet-400 text-xs font-semibold">
              <Cpu size={14} /> LLM Hypothesis
            </div>
            <h3 className="text-lg font-bold text-white mb-1">Options IV Mean Revert</h3>
            <p className="text-xs text-neutral-500 mb-4 font-mono">HYP_092</p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Sharpe Ratio</span>
                <span className="text-white font-medium">2.12</span>
              </div>
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Max Drawdown</span>
                <span className="text-emerald-400 font-medium">-6.8%</span>
              </div>
              <div className="flex justify-between border-b border-neutral-800 pb-1">
                <span className="text-neutral-400">Win Rate</span>
                <span className="text-white font-medium">58%</span>
              </div>
            </div>
          </div>
          <div className="w-1/2 h-48 flex items-center justify-center text-neutral-600 text-sm">
             [Radar Chart]
          </div>
        </div>
      </div>

      {/* Strategies Table */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="font-semibold text-white">Full Population Registry</h2>
          <div className="flex gap-2 text-xs">
            <button className="px-3 py-1.5 bg-neutral-800 text-neutral-300 font-medium rounded hover:bg-neutral-700 hover:text-white">All Data</button>
            <button className="px-3 py-1.5 bg-neutral-950 text-neutral-500 font-medium rounded hover:text-white border border-neutral-800">Filtered</button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-neutral-950/50 text-neutral-400 text-xs uppercase font-medium border-b border-neutral-800">
              <tr>
                <th className="px-6 py-4 font-semibold">Strategy ID</th>
                <th className="px-6 py-4 font-semibold">Name / Logic</th>
                <th className="px-6 py-4 font-semibold">Sharpe</th>
                <th className="px-6 py-4 font-semibold">Max DD</th>
                <th className="px-6 py-4 font-semibold">Win Rate</th>
                <th className="px-6 py-4 font-semibold">Source</th>
                <th className="px-6 py-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800/50">
              {mockStrategies.map((item, i) => (
                <tr key={i} className="hover:bg-neutral-800/30 transition-colors group">
                  <td className="px-6 py-4 font-mono text-neutral-300">{item.id}</td>
                  <td className="px-6 py-4 font-medium text-white">{item.name}</td>
                  <td className="px-6 py-4 text-emerald-400 font-bold">{item.sharpe}</td>
                  <td className="px-6 py-4 text-neutral-400">- {item.dd}%</td>
                  <td className="px-6 py-4 text-neutral-400">{item.winRate}%</td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 bg-neutral-800 rounded text-xs text-neutral-300 font-medium">{item.source}</span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-indigo-400 hover:text-indigo-300 font-medium text-xs border border-indigo-500/30 px-3 py-1.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      Deploy
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
