'use client';

import { useEffect, useState } from 'react';
import {
  Activity, TrendingUp, AlertTriangle, Zap,
  Database, RefreshCw, Clock, PlayCircle, Server
} from 'lucide-react';

interface TradeAlert {
  agent: string;
  symbol: string;
  close_price: number;
  signals: string[];
  timestamp?: string;
}

interface GlobalCues {
  overallBias: string;
  vixValue: number;
  spyChangePct: number;
  sgxNifty: number;
}

interface PipelineStatus {
  name: string;
  lastSync: string;
  status: 'healthy' | 'syncing' | 'error';
  records: number;
}

export default function CommandCenter() {
  const [alerts, setAlerts] = useState<TradeAlert[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState<string | null>(null);
  const [workers, setWorkers] = useState<Record<string, { name: string, status: string, pid: number | null }>>({});
  const [globalCues, setGlobalCues] = useState<GlobalCues | null>(null);

  // Mock initial pipeline state - in a real app, fetch this from a Next.js API route reading Postgres MAX(created_at)
  const [pipelines, setPipelines] = useState<PipelineStatus[]>([
    { name: 'FII/DII Flows', lastSync: '10 mins ago', status: 'healthy', records: 1204 },
    { name: 'NSDL Sectors', lastSync: '1 hour ago', status: 'healthy', records: 48 },
    { name: 'Options Footprint', lastSync: 'Pending', status: 'error', records: 0 },
    { name: 'Macro News', lastSync: '2 mins ago', status: 'healthy', records: 843 },
  ]);

  const fetchWorkers = async () => {
    try {
      const res = await fetch('/api/system/workers');
      const data = await res.json();
      if (!data.error) setWorkers(data);
    } catch (err) {
      console.error('Failed to fetch workers', err);
    }
  };

  const fetchGlobalCues = async () => {
    try {
      const res = await fetch('/api/global');
      const { data } = await res.json();
      if (data) setGlobalCues(data);
    } catch (err) {
      console.error('Failed to fetch global cues', err);
    }
  };

  useEffect(() => {
    const eventSource = new EventSource('/api/alerts');
    eventSource.onopen = () => setIsConnected(true);
    eventSource.onmessage = (event) => {
      const newAlert: TradeAlert = JSON.parse(event.data);
      newAlert.timestamp = new Date().toLocaleTimeString();
      setAlerts((prev) => [newAlert, ...prev].slice(0, 50));
    };
    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
    };

    // Initial fetch and poll workers
    fetchWorkers();
    fetchGlobalCues();
    const interval = setInterval(fetchWorkers, 5000);

    return () => {
      eventSource.close();
      clearInterval(interval);
    };
  }, []);

  const toggleWorker = async (workerId: string, currentStatus: string) => {
    const action = currentStatus === 'RUNNING' ? 'stop' : 'start';
    setIsProcessing(workerId);
    try {
      const res = await fetch('/api/system/workers', {
        method: 'POST',
        body: JSON.stringify({ worker_id: workerId, action })
      });
      await res.json();
      await fetchWorkers();
    } catch (err) {
      alert('Failed to toggle worker');
    } finally {
      setIsProcessing(null);
    }
  };

  const triggerAction = async (actionId: string) => {
    setIsProcessing(actionId);

    try {
      const response = await fetch('/api/system/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ task: actionId }),
      });

      if (!response.ok) {
        throw new Error('Failed to trigger task');
      }

      // Briefly wait to simulate running pipeline then unlock processing state
      setTimeout(() => {
        setIsProcessing(null);
        if (actionId === 'sync_fii') {
          setPipelines(p => p.map(pipe => pipe.name === 'FII/DII Flows' ? { ...pipe, lastSync: 'Just now', records: pipe.records + 1 } : pipe));
        } else if (actionId === 'sync_nsdl') {
          setPipelines(p => p.map(pipe => pipe.name === 'NSDL Sectors' ? { ...pipe, lastSync: 'Just now', records: pipe.records + 1 } : pipe));
        }
      }, 500);

    } catch (err) {
      console.error(err);
      setIsProcessing(null);
      alert('Failed to execute command: Broker might be offline or task invalid.');
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6 font-mono">
      {/* Header */}
      <header className="flex justify-between items-center border-b border-neutral-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <Activity className="text-purple-500" size={28} />
          <h1 className="text-2xl font-bold tracking-tight text-white">QUANT DESK <span className="text-neutral-500 text-sm">v2.0</span></h1>
        </div>
        <div className="flex items-center gap-4 text-sm">
          {globalCues && (
            <div className={`flex items-center gap-3 px-3 py-1.5 rounded border 
              ${globalCues.overallBias === 'RISK_ON' ? 'bg-emerald-900/20 border-emerald-900/50 text-emerald-400' 
              : globalCues.overallBias === 'RISK_OFF' ? 'bg-red-900/20 border-red-900/50 text-red-400' 
              : 'bg-neutral-900 border-neutral-800 text-neutral-300'}`}>
              <div className="font-bold border-r border-inherit pr-3">{globalCues.overallBias.replace('_', ' ')}</div>
              <div className="flex items-center gap-3 text-xs opacity-90">
                <span>VIX {globalCues.vixValue}</span>
                <span>SPY {globalCues.spyChangePct > 0 ? '+' : ''}{globalCues.spyChangePct}%</span>
                <span>GIFT {globalCues.sgxNifty}</span>
              </div>
            </div>
          )}
          <div className="flex items-center gap-2 bg-neutral-900 px-3 py-1.5 rounded border border-neutral-800">
            <Server size={14} className="text-neutral-400" />
            <span className="text-neutral-300">Vault: PostgreSQL</span>
          </div>
          {isConnected ? (
            <span className="flex items-center gap-2 text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-3 py-1.5 rounded">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              RabbitMQ Live
            </span>
          ) : (
            <span className="text-red-400 bg-red-400/10 border border-red-400/20 px-3 py-1.5 rounded">Queue Disconnected</span>
          )}
        </div>
      </header>

      {/* Telemetry Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {pipelines.map((pipe, idx) => (
          <div key={idx} className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 flex flex-col justify-between">
            <div className="flex justify-between items-start mb-2">
              <span className="text-sm font-semibold text-neutral-300">{pipe.name}</span>
              {pipe.status === 'healthy' ? (
                <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              ) : (
                <AlertTriangle size={14} className="text-yellow-500" />
              )}
            </div>
            <div>
              <div className="text-2xl font-bold text-white mb-1">{pipe.records.toLocaleString()} <span className="text-xs text-neutral-500 font-normal">rows</span></div>
              <div className="flex items-center gap-1 text-xs text-neutral-500">
                <Clock size={12} /> Last sync: {pipe.lastSync}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

        {/* Active Alerts Feed */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Zap size={16} /> Live Setup Stream
          </h2>

          {alerts.length === 0 ? (
            <div className="border border-dashed border-neutral-800 rounded-lg p-12 flex flex-col items-center justify-center text-neutral-500">
              <Database size={32} className="mb-3 opacity-50" />
              <p>Awaiting quantitative setups...</p>
            </div>
          ) : (
            alerts.map((alert, idx) => (
              <div key={idx} className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 shadow-lg hover:border-neutral-700 transition-colors animate-in fade-in slide-in-from-top-4">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex items-center gap-3">
                    <span className="bg-blue-500/10 text-blue-400 text-xs px-2 py-1 rounded border border-blue-500/20">
                      {alert.agent} Agent
                    </span>
                    <h3 className="text-xl font-bold text-white">{alert.symbol}</h3>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold tracking-wide">₹{alert.close_price.toFixed(2)}</div>
                    <div className="text-xs text-neutral-500">{alert.timestamp}</div>
                  </div>
                </div>

                <div className="space-y-2 mt-4 pl-2 border-l-2 border-neutral-700">
                  {alert.signals.map((signal, sIdx) => (
                    <p key={sIdx} className="text-sm flex items-start gap-2">
                      {signal.includes('BEARISH') || signal.includes('DEATH') ? (
                        <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
                      ) : (
                        <TrendingUp size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      )}
                      <span className={signal.includes('BEARISH') ? 'text-neutral-300' : 'text-neutral-200'}>
                        {signal}
                      </span>
                    </p>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* System Controls Sidebar */}
        <div className="space-y-6">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-4 border-b border-neutral-800 pb-2 flex items-center gap-2">
              <Server size={16} /> System Overrides
            </h2>

            <div className="space-y-3">
              <button
                onClick={() => triggerAction('sync_fii')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 bg-neutral-950 border border-neutral-800 hover:border-purple-500/50 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-neutral-300">
                  <PlayCircle size={14} className="text-purple-400" /> Force FII/DII Scrape
                </span>
                {isProcessing === 'sync_fii' && <RefreshCw size={14} className="animate-spin text-neutral-500" />}
              </button>

              <button
                onClick={() => triggerAction('sync_nsdl')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 bg-neutral-950 border border-neutral-800 hover:border-purple-500/50 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-neutral-300">
                  <PlayCircle size={14} className="text-purple-400" /> Force NSDL Sector Scrape
                </span>
                {isProcessing === 'sync_nsdl' && <RefreshCw size={14} className="animate-spin text-neutral-500" />}
              </button>

              <button
                onClick={() => triggerAction('seed_db')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 mt-4 bg-yellow-500/10 border border-yellow-500/30 hover:border-yellow-500 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-yellow-500 font-medium">
                  <Database size={14} /> Seed Historical JSONs
                </span>
                {isProcessing === 'seed_db' && <RefreshCw size={14} className="animate-spin text-yellow-500" />}
              </button>
            </div>
          </div>

          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-4 border-b border-neutral-800 pb-2 flex items-center gap-2">
              <Zap size={16} /> Python Fleet Status
            </h2>
            <div className="space-y-3">
              {Object.entries(workers).map(([id, info]) => (
                <div key={id} className="flex justify-between items-center text-sm p-2 hover:bg-neutral-800/50 rounded transition-colors group">
                  <div className="flex flex-col">
                    <span className="text-neutral-300 font-medium capitalize">{id}</span>
                    <span className="text-[10px] text-neutral-500 font-mono">{info.name}</span>
                  </div>
                  <button
                    onClick={() => toggleWorker(id, info.status)}
                    disabled={isProcessing === id}
                    className={`px-2 py-1 rounded text-[10px] font-bold transition-all ${info.status === 'RUNNING'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30'
                        : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-emerald-500/20 hover:text-emerald-400 hover:border-emerald-500/30'
                      }`}
                  >
                    {isProcessing === id ? '...' : (info.status === 'RUNNING' ? 'STOP' : 'START')}
                  </button>
                </div>
              ))}
              {Object.keys(workers).length === 0 && <p className="text-xs text-neutral-600 text-center py-4">No workers detected.</p>}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}