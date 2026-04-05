"use client"
import { Play, TrendingUp, TrendingDown, Activity, Clock } from 'lucide-react';

export default function Topbar() {
  return (
    <header className="h-16 px-6 border-b border-neutral-800 bg-neutral-900/50 flex items-center justify-between sticky top-0 z-10 backdrop-blur-md">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-neutral-400">NIFTY</span>
          <span className="text-lg font-bold text-neutral-100">22,450.50</span>
          <div className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-sm font-medium">
            <TrendingUp size={14} />
            +0.45%
          </div>
        </div>

        <div className="h-6 w-px bg-neutral-800"></div>

        <div className="flex items-center gap-2">
          <Activity size={16} className="text-amber-400" />
          <span className="text-sm font-medium text-neutral-300">Regime:</span>
          <span className="text-sm font-bold text-amber-500">High IV Mean Reverting</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-xs font-medium text-neutral-500">
          <Clock size={14} />
          Last Synced: 10:15 AM
        </div>
        
        <button className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 transition-colors text-white px-4 py-2 rounded-lg text-sm font-semibold shadow-[0_0_15px_rgba(79,70,229,0.3)]">
          <Play size={16} className="fill-current" />
          Run Evolution Cycle
        </button>
      </div>
    </header>
  );
}
