"use client"
import { Activity, Network, TrendingUp, Cpu, BarChart2 } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

const mockEquityCurve = [
  { step: 0, equity: 100000 },
  { step: 1000, equity: 101200 },
  { step: 2000, equity: 100800 },
  { step: 3000, equity: 103500 },
  { step: 4000, equity: 106000 },
  { step: 5000, equity: 105500 },
  { step: 6000, equity: 112000 },
  { step: 7000, equity: 115400 },
];

export default function EvolutionPage() {
  return (
    <div className="space-y-6">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">Neural & MARL Intelligence</h1>
        <p className="text-sm text-neutral-400 mt-1">Deep Learning models optimized via Neuroevolution and Proximal Policy Optimization.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        
        {/* Left Col: NEAT */}
        <div className="space-y-6">
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-sm">
            <div className="p-5 border-b border-neutral-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Network className="text-violet-400" size={20} />
                <h2 className="font-bold text-white">NEAT Network Architecture</h2>
              </div>
              <span className="px-2 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded">Gen 80 Winner</span>
            </div>
            <div className="p-6">
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3 text-center">
                  <div className="text-neutral-500 text-xs font-medium mb-1">Fitness</div>
                  <div className="text-xl font-bold text-white">845.2</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3 text-center">
                  <div className="text-neutral-500 text-xs font-medium mb-1">Nodes</div>
                  <div className="text-xl font-bold text-white">42</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3 text-center">
                  <div className="text-neutral-500 text-xs font-medium mb-1">Connections</div>
                  <div className="text-xl font-bold text-white">128</div>
                </div>
              </div>

              {/* Fake Network Graph Visualization Area */}
              <div className="h-64 bg-neutral-950 rounded-lg border border-neutral-800 flex flex-col items-center justify-center relative overflow-hidden">
                <div className="absolute inset-0 opacity-20 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-violet-900 via-neutral-900 to-transparent"></div>
                <Network size={48} className="text-neutral-700 mb-4" />
                <p className="text-sm text-neutral-500 font-medium">Network Visualization Graph</p>
                <p className="text-xs text-neutral-600 mt-1">(Install react-force-graph to render)</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Col: MARL */}
        <div className="space-y-6">
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-sm flex flex-col h-full">
            <div className="p-5 border-b border-neutral-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="text-amber-400" size={20} />
                <h2 className="font-bold text-white">MARL PPO Performance</h2>
              </div>
              <span className="px-2 py-1 bg-amber-500/10 text-amber-400 text-xs font-semibold rounded">100k Steps</span>
            </div>
            
            <div className="p-6 flex-1 flex flex-col">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-neutral-300">Training Equity Curve</h3>
                  <p className="text-xs text-neutral-500">Reward progression over episodes</p>
                </div>
                <div className="text-right">
                  <div className="text-emerald-400 font-bold text-lg">+15.4%</div>
                  <div className="text-xs text-neutral-500">Test Set ROI</div>
                </div>
              </div>
              
              <div className="h-64 w-full bg-neutral-950 rounded-lg p-4 border border-neutral-800">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={mockEquityCurve}>
                    <defs>
                      <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                    <XAxis dataKey="step" stroke="#666" tick={{fill: '#666', fontSize: 12}} />
                    <YAxis domain={['dataMin - 1000', 'dataMax + 1000']} stroke="#666" tick={{fill: '#666', fontSize: 12}} />
                    <Tooltip contentStyle={{backgroundColor: '#171717', borderColor: '#333'}} itemStyle={{color: '#f59e0b'}}/>
                    <Area type="monotone" dataKey="equity" stroke="#f59e0b" strokeWidth={2} fillOpacity={1} fill="url(#colorEquity)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="bg-neutral-950 p-4 rounded-lg border border-neutral-800 text-center flex-1">
                   <div className="text-neutral-500 text-xs font-semibold uppercase tracking-wider mb-2">Long Action Bias</div>
                   <div className="text-xl font-bold text-white text-emerald-400">42%</div>
                </div>
                <div className="bg-neutral-950 p-4 rounded-lg border border-neutral-800 text-center flex-1">
                   <div className="text-neutral-500 text-xs font-semibold uppercase tracking-wider mb-2">Short Action Bias</div>
                   <div className="text-xl font-bold text-white text-rose-400">28%</div>
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
