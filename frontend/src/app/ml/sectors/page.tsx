"use client"
import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';
import { Network, ArrowRight } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, Cell } from 'recharts';

// Dynamically import react-force-graph to avoid SSR 'window undefined' errors
const ForceGraph2D = dynamic(() => import('react-force-graph').then(mod => mod.ForceGraph2D), { ssr: false });

const mockSectorData = [
  { name: 'NIFTY IT', strength: 85, fill: '#10b981' },
  { name: 'PHARMA', strength: 72, fill: '#10b981' },
  { name: 'FMCG', strength: 65, fill: '#10b981' },
  { name: 'METALS', strength: -30, fill: '#f43f5e' },
  { name: 'AUTO', strength: -45, fill: '#f43f5e' },
  { name: 'FIN_SERV', strength: -60, fill: '#f43f5e' },
  { name: 'BANK_NIFTY', strength: -75, fill: '#f43f5e' },
];

export default function SectorsPage() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });

  useEffect(() => {
    // Generate nodes and links representing GNN sector flow
    const sectors = ['NIFTY', 'BANK', 'IT', 'AUTO', 'FMCG', 'PHARMA', 'ENERGY', 'METAL', 'REALTY'];
    
    const nodes = sectors.map((sector) => {
      // Create mock node strengths correlated to the bar chart data
      const sourceData = mockSectorData.find(s => s.name.includes(sector));
      const strength = sourceData ? sourceData.strength / 100 : (Math.random() * 2 - 1);
      
      return {
        id: sector,
        name: sector,
        value: Math.max(1, Math.abs(strength) * 10), // Node size multiplier
        color: strength > 0 ? '#10b981' : '#f43f5e',
        group: 'sector'
      };
    });

    const links = [];
    for (let i = 0; i < sectors.length; i++) {
      for (let j = i + 1; j < sectors.length; j++) {
        // Create correlation links
        const correlation = Math.random() * 2 - 1; 
        if (Math.abs(correlation) > 0.4) { // Only show strong edges
          links.push({
            source: sectors[i],
            target: sectors[j],
            value: Math.abs(correlation) * 5, // Edge thickness
            color: correlation > 0 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.4)'
          });
        }
      }
    }

    setGraphData({ nodes, links });
  }, []);

  return (
    <div className="space-y-6">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">Sector GNN Rotation Map</h1>
        <p className="text-sm text-neutral-400 mt-1">Interactive Graph Neural Network evaluating systemic flow across major NIFTY indices.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Force-Directed Graph */}
        <div className="lg:col-span-8 bg-neutral-900 border border-neutral-800 rounded-xl p-4 h-[650px] relative overflow-hidden flex flex-col">
           <div className="flex justify-between items-center z-10 relative mb-2">
             <div className="flex items-center gap-2">
                <Network className="text-indigo-400" size={20} />
                <h3 className="font-semibold text-white">Interactive Rotation Graph</h3>
             </div>
             <div className="text-xs font-semibold px-3 py-1.5 bg-neutral-950 border border-neutral-800 rounded text-neutral-400 shadow-inner">
               Drag nodes to inspect GNN clustering
             </div>
           </div>
           <div className="flex-1 w-full bg-neutral-950 rounded-lg border border-neutral-800 overflow-hidden shadow-inner flex items-center justify-center">
             {graphData.nodes.length > 0 && typeof window !== 'undefined' ? (
                <ForceGraph2D
                  graphData={graphData}
                  nodeLabel="name"
                  nodeVal="value"
                  nodeColor="color"
                  linkWidth="value"
                  linkColor="color"
                  linkOpacity={0.8}
                  backgroundColor="#0a0a0a" // neutral-950
                  cooldownTicks={100}
                  onNodeClick={(node) => console.log(`Clicked ${node.name}`)}
                  width={800}
                  height={550}
                />
             ) : (
                <div className="animate-pulse text-neutral-600 flex items-center gap-2">
                  <Network size={20} /> Loading GNN Structure...
                </div>
             )}
           </div>
        </div>

        {/* Right Sidebar Columns */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Recommendation Card */}
          <div className="bg-gradient-to-br from-emerald-900/30 to-neutral-900 border border-emerald-500/20 p-6 rounded-xl shadow-lg">
            <div className="inline-flex px-3 py-1 bg-emerald-500/20 text-emerald-400 text-xs font-bold uppercase tracking-wider rounded-full mb-4">
               Bearish Rotation Phase
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Favor Defensive (FMCG, Pharma)</h2>
            <p className="text-sm text-neutral-400 mb-5">
              GNN predicts a strong flow of liquidity out of high-beta sectors (Banking, Autos) and into defensive safe havens. High correlation seen with dropping NIFTY IV.
            </p>
            <div className="space-y-3">
              <div className="flex justify-between items-center bg-neutral-950 p-3 rounded border border-neutral-800">
                <span className="text-sm font-medium text-emerald-400">Long Proxy</span>
                <span className="text-white font-bold">NIFTY IT / PHARMA</span>
              </div>
              <div className="flex justify-center text-neutral-600">
                 <ArrowRight size={16} className="rotate-90" />
              </div>
              <div className="flex justify-between items-center bg-neutral-950 p-3 rounded border border-neutral-800">
                <span className="text-sm font-medium text-rose-400">Short Proxy</span>
                <span className="text-white font-bold">BANK NIFTY</span>
              </div>
            </div>
          </div>

          {/* Sector Strength Bar Chart */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 flex flex-col">
            <h3 className="font-semibold text-white mb-4">Node Momentum Hierarchy</h3>
            <div className="flex-1 min-h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={mockSectorData} margin={{top: 0, right: 10, left: 20, bottom: 0}}>
                  <XAxis type="number" domain={[-100, 100]} hide />
                  <YAxis dataKey="name" type="category" stroke="#525252" tick={{fill: '#d4d4d4', fontSize: 10, fontWeight: 500}} width={80} axisLine={false} tickLine={false} />
                  <RechartsTooltip cursor={{fill: '#262626'}} contentStyle={{backgroundColor: '#171717', borderColor: '#404040', color: '#fff'}} />
                  <Bar dataKey="strength" barSize={12} radius={[0, 4, 4, 0]}>
                    {mockSectorData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
