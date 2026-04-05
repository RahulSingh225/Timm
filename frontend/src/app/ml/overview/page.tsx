"use client"
import { Activity, Zap, ShieldAlert, Cpu, Route, Trophy } from 'lucide-react';

export default function OverviewPage() {
  return (
    <div className="space-y-6">
      {/* Hero Header */}
      <div className="bg-gradient-to-br from-indigo-900/50 to-neutral-900 border border-indigo-500/20 rounded-xl p-8 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
          <Cpu size={120} />
        </div>
        
        <div className="mb-4 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold tracking-wide uppercase">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Live Advisor Recommendation
        </div>
        
        <h1 className="text-4xl font-extrabold text-white mb-2 tracking-tight">
          Strong Bullish bias into Close
        </h1>
        <p className="text-neutral-400 max-w-2xl text-base leading-relaxed">
          "FII Option footprint shows heavy put writing at 22,400. Candle Vector logic indicates aggressive volume expansion combined with a drop in local IV. MARL Agents recommend holding longs with a trailing stop-loss."
        </p>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        
        {/* Card 1 */}
        <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-5 hover:border-indigo-500/50 transition-colors">
          <div className="flex items-start justify-between mb-4">
            <div className="text-indigo-400 p-2 bg-indigo-500/10 rounded-lg">
              <Trophy size={20} />
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-neutral-800 rounded text-neutral-400">Genetic Prog.</span>
          </div>
          <h3 className="text-neutral-400 text-sm font-medium mb-1">Top GP Sharpe</h3>
          <div className="text-3xl font-bold text-white">2.84</div>
          <p className="text-xs text-emerald-400 mt-2 font-medium">+0.12 from last cycle</p>
        </div>

        {/* Card 2 */}
        <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-5 hover:border-indigo-500/50 transition-colors">
          <div className="flex items-start justify-between mb-4">
            <div className="text-amber-400 p-2 bg-amber-500/10 rounded-lg">
              <Activity size={20} />
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-neutral-800 rounded text-neutral-400">MARL PPO</span>
          </div>
          <h3 className="text-neutral-400 text-sm font-medium mb-1">MARL Avg Reward</h3>
          <div className="text-3xl font-bold text-white">+1,240 <span className="text-sm font-normal text-neutral-500">pts</span></div>
          <p className="text-xs text-emerald-400 mt-2 font-medium">Stable multi-agent policy</p>
        </div>

        {/* Card 3 */}
        <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-5 hover:border-indigo-500/50 transition-colors">
          <div className="flex items-start justify-between mb-4">
            <div className="text-violet-400 p-2 bg-violet-500/10 rounded-lg">
              <Route size={20} />
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-neutral-800 rounded text-neutral-400">NEAT</span>
          </div>
          <h3 className="text-neutral-400 text-sm font-medium mb-1">Best Topology Fitness</h3>
          <div className="text-3xl font-bold text-white">845.2</div>
          <p className="text-xs text-neutral-500 mt-2 font-medium">Generations: 80 / Nodes: 42</p>
        </div>

        {/* Card 4 */}
        <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-5 hover:border-indigo-500/50 transition-colors">
          <div className="flex items-start justify-between mb-4">
            <div className="text-sky-400 p-2 bg-sky-500/10 rounded-lg">
              <Zap size={20} />
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-neutral-800 rounded text-neutral-400">Candle Vector</span>
          </div>
          <h3 className="text-neutral-400 text-sm font-medium mb-1">IV-Adjusted Edge</h3>
          <div className="text-3xl font-bold text-white">0.92 <span className="text-sm font-normal text-neutral-500">Sigma</span></div>
          <p className="text-xs text-emerald-400 mt-2 font-medium">Highly actionable vector</p>
        </div>

        {/* Card 5 */}
        <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-5 hover:border-indigo-500/50 transition-colors">
          <div className="flex items-start justify-between mb-4">
            <div className="text-red-400 p-2 bg-red-500/10 rounded-lg">
              <ShieldAlert size={20} />
            </div>
            <span className="text-xs font-semibold px-2 py-1 bg-neutral-800 rounded text-neutral-400">Risk Manager</span>
          </div>
          <h3 className="text-neutral-400 text-sm font-medium mb-1">Drawdown Risk</h3>
          <div className="text-3xl font-bold text-white">Low</div>
          <p className="text-xs text-neutral-500 mt-2 font-medium">No aggressive defense triggered</p>
        </div>

      </div>

      {/* Two Column Bottom Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-neutral-900 border border-neutral-800 rounded-xl p-6">
          <h3 className="font-semibold text-lg mb-4 text-white">Intelligence Pipeline Status</h3>
          <div className="space-y-4">
            {/* Status Item */}
            <div className="flex items-center gap-4 p-3 bg-neutral-950 rounded-lg border border-neutral-800/50">
              <div className="w-10 h-10 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Cpu size={18} />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-neutral-200">Qwen LLM Hypothesis Generator</h4>
                <p className="text-xs text-neutral-500">Last run: 14 hours ago. Generated 8 hypotheses.</p>
              </div>
              <div className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded">Ready</div>
            </div>
            {/* Status Item */}
            <div className="flex items-center gap-4 p-3 bg-neutral-950 rounded-lg border border-neutral-800/50">
              <div className="w-10 h-10 rounded-full bg-violet-500/20 flex items-center justify-center text-violet-400">
                <Route size={18} />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-neutral-200">Evolutionary Optimizer & NEAT</h4>
                <p className="text-xs text-neutral-500">Last run: 2 hours ago. Mutated 150 genomes.</p>
              </div>
              <div className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded">Ready</div>
            </div>
          </div>
        </div>

        {/* Live Stream Panel */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl flex flex-col h-full">
          <div className="p-4 border-b border-neutral-800 h-14 flex items-center">
            <h3 className="font-semibold text-white">Live Signal Feed</h3>
          </div>
          <div className="p-4 flex-1 overflow-y-auto space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="flex gap-3 items-start opacity-70 hover:opacity-100 transition-opacity">
                <div className="w-1.5 h-1.5 mt-2 rounded-full bg-emerald-500 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-neutral-300">Intraday Builder [{i}m ago]</p>
                  <p className="text-xs text-neutral-500 mt-0.5">Found Bullish Scalp matching GP Strategy HYP_{8+i}. R:R 1:3.</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
