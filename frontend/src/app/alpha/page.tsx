'use client';

import { useEffect, useState } from 'react';
import { 
  Zap, 
  Target, 
  Terminal, 
  TrendingUp, 
  TrendingDown, 
  ShieldCheck, 
  History, 
  Rocket, 
  AlertTriangle, 
  Lightbulb,
  Activity
} from 'lucide-react';
import { Navigation } from '@/components/Navigation';

interface Setup {
  symbol: string;
  trade_type: string;
  option_action?: string;
  strike_offset?: string;
  entry_price?: number;
  target_price?: number;
  stoploss_price?: number;
  confidence: number;
  evidence: string[];
  max_premium_per_lot?: number;
  expected_move_pct?: number;
}

export default function AlphaCenter() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);

  const fetchAlphaData = async () => {
    try {
      const res = await fetch('/api/system/daily-report');
      const json = await res.json();
      if (json.success) {
        setData(json.data);
      }
    } catch (err) {
      console.error('Failed to fetch alpha data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlphaData();
  }, []);

  const acceptTrade = async (setup: Setup) => {
    setProcessing(setup.symbol);
    try {
      const res = await fetch('/api/alpha/accept-trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: setup.symbol,
          trade_type: setup.trade_type,
          entry_price: setup.entry_price || 0,
          stoploss: setup.stoploss_price || 0,
          target: setup.target_price || 0,
          evidence: setup.evidence
        })
      });
      if (res.ok) {
        alert(`${setup.symbol} trade tracked in Journal!`);
      }
    } catch (err) {
      console.error('Failed to accept trade', err);
    } finally {
      setProcessing(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-950 flex flex-col items-center justify-center font-mono">
        <Zap className="text-blue-500 animate-pulse mb-4" size={48} />
        <p className="text-neutral-500">Initializing Alpha Streams...</p>
      </div>
    );
  }

  const reports = data || {};
  const intradaySetups = reports.intradaySetups || [];
  const optionsSetups = reports.optionsSetups || [];

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 font-mono pb-20">
      <Navigation />

      <main className="max-w-7xl mx-auto px-6 py-10 pt-24">
        {/* Header Section */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-2">
            <Rocket className="text-blue-500" size={32} />
            <h1 className="text-4xl font-black italic tracking-tighter text-white">ALPHA_CENTER</h1>
          </div>
          <div className="flex items-center gap-4 text-neutral-500 text-sm">
            <span className="flex items-center gap-1.5"><History size={14} /> NEXT_SESSION: 2026-04-06</span>
            <span className="h-1 w-1 rounded-full bg-neutral-700" />
            <span className="text-emerald-500 font-bold">MODE: PRE-MARKET_INTELLIGENCE</span>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column: Morning Brief & Market Regime */}
          <div className="lg:col-span-1 space-y-8">
            {/* Market Regime Card */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <Activity size={80} />
              </div>
              <h2 className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Target size={14} /> Market Status
              </h2>
              <div className="space-y-4">
                <div>
                  <div className="text-[10px] text-neutral-500 mb-1">REGIME</div>
                  <div className={`text-2xl font-black ${reports.marketRegime === 'RISK_ON' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {reports.marketRegime?.replace('_', ' ') || 'NEUTRAL'}
                  </div>
                </div>
                <div className="flex gap-8">
                  <div>
                    <div className="text-[10px] text-neutral-500 mb-1">INDIA VIX</div>
                    <div className="text-xl font-bold text-white">{reports.vix?.toFixed(2) || '14.20'}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-neutral-500 mb-1">FII NET</div>
                    <div className="text-xl font-bold text-white">{reports.fiiNet || 'N/A'}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Morning Intel Card */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-2xl p-6">
              <h2 className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Terminal size={14} text-blue-500 /> Morning Intel
              </h2>
              <div className="text-neutral-300 text-sm leading-relaxed whitespace-pre-wrap font-sans italic bg-neutral-950 p-4 rounded-xl border border-neutral-800/50">
                {reports.headAnalystBrief || "No briefing available for the next session yet. Graph run pending."}
              </div>
              
              {reports.avoidList?.length > 0 && (
                <div className="mt-6">
                  <div className="text-xs font-bold text-red-500 uppercase tracking-widest mb-2 flex items-center gap-2">
                    <AlertTriangle size={14} /> Restricted (Side-track)
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {reports.avoidList.map((s: string) => (
                      <span key={s} className="bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-0.5 rounded text-[10px] font-bold tracking-tight">{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Middle/Right Column: Trade Setups */}
          <div className="lg:col-span-2 space-y-8">
            {/* Intraday Setups */}
            <div>
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-black text-white flex items-center gap-3 tracking-tighter">
                  <Zap className="text-yellow-500" size={24} /> INTRADAY_EQUITY
                </h2>
                <span className="text-neutral-500 text-xs">{intradaySetups.length} POTENTIAL SETUPS</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {intradaySetups.length === 0 && (
                  <div className="col-span-2 bg-neutral-900/30 border border-neutral-800 border-dashed rounded-2xl p-12 text-center text-neutral-600">
                    No high-conviction equity setups detected.
                  </div>
                )}
                {intradaySetups.map((setup: Setup) => (
                  <SetupCard 
                    key={setup.symbol} 
                    setup={setup} 
                    onAccept={() => acceptTrade(setup)} 
                    isProcessing={processing === setup.symbol}
                  />
                ))}
              </div>
            </div>

            {/* Options Setups */}
            <div className="pt-4">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-black text-white flex items-center gap-3 tracking-tighter">
                  <Target className="text-blue-500" size={24} /> OPTIONS_SCALPING
                </h2>
                <span className="text-neutral-500 text-xs">{optionsSetups.length} VOLATILITY PLAYS</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {optionsSetups.length === 0 && (
                  <div className="col-span-2 bg-neutral-900/30 border border-neutral-800 border-dashed rounded-2xl p-12 text-center text-neutral-600">
                    No options setups found with &lt;₹50 premium risk.
                  </div>
                )}
                {optionsSetups.map((setup: Setup) => (
                  <SetupCard 
                    key={setup.symbol} 
                    setup={setup} 
                    onAccept={() => acceptTrade(setup)} 
                    isProcessing={processing === setup.symbol}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function SetupCard({ setup, onAccept, isProcessing }: { setup: Setup, onAccept: () => void, isProcessing: boolean }) {
  const isBullish = setup.trade_type?.includes('LONG') || setup.option_action?.includes('CALL');
  
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 hover:border-neutral-600 transition-all group">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-neutral-800 flex items-center justify-center font-black text-lg text-white border border-neutral-700">
            {setup.symbol[0]}
          </div>
          <div>
            <div className="font-black text-xl text-white tracking-tighter">{setup.symbol}</div>
            <div className="text-[10px] text-neutral-500 flex items-center gap-1 font-bold">
              {setup.trade_type === 'OPTIONS_SCALP' ? (
                <span className="text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded border border-blue-400/20 uppercase tracking-widest whitespace-nowrap overflow-hidden text-ellipsis max-w-[120px]">
                  {setup.option_action} @ {setup.strike_offset}
                </span>
              ) : (
                <span className={`${isBullish ? 'text-emerald-400' : 'text-red-400'} uppercase tracking-widest`}>
                  {setup.trade_type.replace('_', ' ')}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-black ${setup.confidence > 70 ? 'text-emerald-400' : 'text-yellow-400'}`}>
            {setup.confidence}%
          </div>
          <div className="text-[8px] text-neutral-500 font-black uppercase tracking-widest">CONFIDENCE</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-neutral-950 p-2 rounded border border-neutral-800/50">
          <div className="text-[8px] text-neutral-500 font-bold mb-0.5">ENTRY</div>
          <div className="text-xs font-bold text-white">₹{setup.entry_price || 'CMP'}</div>
        </div>
        <div className="bg-neutral-950 p-2 rounded border border-neutral-800/50">
          <div className="text-[8px] text-neutral-500 font-bold mb-0.5">TARGET</div>
          <div className="text-xs font-bold text-emerald-400">₹{setup.target_price || 'OPEN'}</div>
        </div>
        <div className="bg-neutral-950 p-2 rounded border border-neutral-800/50">
          <div className="text-[8px] text-neutral-500 font-bold mb-0.5">STOPLOW</div>
          <div className="text-xs font-bold text-red-400">₹{setup.stoploss_price || 'EXIT'}</div>
        </div>
      </div>

      <div className="space-y-1.5 mb-6 max-h-32 overflow-y-auto pr-1">
        {setup.evidence.map((e, i) => (
          <div key={i} className="flex items-start gap-2 text-[10px] text-neutral-400 font-sans leading-tight">
            <ShieldCheck size={12} className="text-blue-500 mt-0.5 shrink-0" />
            <span>{e}</span>
          </div>
        ))}
      </div>

      <button 
        onClick={onAccept}
        disabled={isProcessing}
        className="w-full bg-white hover:bg-neutral-200 text-black py-2 rounded-lg font-black text-xs tracking-widest transition-all flex items-center justify-center gap-2"
      >
        {isProcessing ? <ActivityIcon className="animate-spin" size={14} /> : <Zap size={14} />}
        ACCEPT_SIGNAL
      </button>
    </div>
  );
}

function ActivityIcon({ className, size }: { className?: string, size?: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  );
}
