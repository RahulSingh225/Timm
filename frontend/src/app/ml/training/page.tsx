'use client';

import { useEffect, useState, useRef } from 'react';
import { Brain, Cpu, RefreshCw, Play, Activity, Zap, CheckCircle2, XCircle, Clock, Layers } from 'lucide-react';

interface TrainingStatus {
  models: Array<{
    model_name: string;
    version: number;
    type: string;
    is_production: boolean;
    metrics: Record<string, number>;
    created_at: string;
  }>;
  active_training: {
    is_running: boolean;
    current_phase: string;
    progress_pct: number;
    started_at: string;
  } | null;
  last_training: {
    completed_at: string;
    duration_sec: number;
    models_trained: number;
  } | null;
}

function ModelCard({ model }: { model: TrainingStatus['models'][0] }) {
  const metrics = model.metrics || {};
  const metricKeys = Object.keys(metrics).slice(0, 4);

  return (
    <div className={`bg-neutral-900/80 border rounded-xl p-4 transition-all hover:border-neutral-600 ${model.is_production ? 'border-emerald-500/40' : 'border-neutral-800'}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain size={16} className={model.is_production ? 'text-emerald-400' : 'text-neutral-500'} />
          <span className="text-sm font-semibold text-neutral-200">{model.model_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-neutral-600 font-mono">v{model.version}</span>
          {model.is_production && (
            <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-bold uppercase">
              PROD
            </span>
          )}
        </div>
      </div>

      <div className="text-[10px] text-neutral-600 mb-2">{model.type}</div>

      <div className="grid grid-cols-2 gap-2">
        {metricKeys.map(key => (
          <div key={key} className="bg-neutral-800/50 rounded-lg p-2">
            <div className="text-[10px] text-neutral-500 truncate">{key}</div>
            <div className="text-sm font-bold text-neutral-200">
              {typeof metrics[key] === 'number' ? metrics[key].toFixed(3) : String(metrics[key])}
            </div>
          </div>
        ))}
      </div>

      <div className="text-[10px] text-neutral-600 mt-3">
        Trained: {new Date(model.created_at).toLocaleDateString()}
      </div>
    </div>
  );
}

export default function TrainingDashboard() {
  const [data, setData] = useState<TrainingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const sseRef = useRef<EventSource | null>(null);
  const [liveLog, setLiveLog] = useState<string[]>([]);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/ml?endpoint=training');
      const json = await res.json();
      if (!json.error) setData(json);
    } catch {} finally { setLoading(false); }
  };

  const triggerTraining = async () => {
    setTriggering(true);
    try {
      await fetch('/api/ml', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'run_training' }),
      });
      setLiveLog(prev => [...prev, '🚀 Training pipeline triggered...']);
      setTimeout(fetchData, 5000);
    } catch {
      setLiveLog(prev => [...prev, '❌ Failed to trigger training']);
    } finally {
      setTimeout(() => setTriggering(false), 3000);
    }
  };

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 15000); return () => clearInterval(i); }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin text-neutral-500" size={24} /></div>;
  }

  const models = data?.models || [];
  const prodModels = models.filter(m => m.is_production);
  const allModels = models;
  const activeTraining = data?.active_training;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">ML Training Pipeline</h1>
          <p className="text-sm text-neutral-500 mt-1">Model registry, training progress, and deployment status</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={triggerTraining}
            disabled={triggering || activeTraining?.is_running}
            className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {triggering ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
            {triggering ? 'Starting...' : 'Run Evolution Cycle'}
          </button>
          <button onClick={fetchData} className="px-3 py-2 rounded-lg bg-neutral-800 border border-neutral-700 text-neutral-400 hover:text-white transition-all text-sm">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Training Status Banner */}
      {activeTraining?.is_running && (
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 flex items-center gap-4">
          <div className="animate-pulse">
            <Cpu size={24} className="text-purple-400" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold text-purple-300">Training in Progress</div>
            <div className="text-xs text-neutral-400 mt-1">
              Phase: {activeTraining.current_phase} · Started: {new Date(activeTraining.started_at).toLocaleTimeString()}
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-purple-300">{activeTraining.progress_pct}%</div>
            <div className="w-24 bg-neutral-700 rounded-full h-2 mt-1">
              <div className="bg-purple-500 h-full rounded-full transition-all" style={{ width: `${activeTraining.progress_pct}%` }} />
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
          <div className="text-xs text-neutral-500 flex items-center gap-2 mb-2"><Layers size={14} /> Total Models</div>
          <div className="text-2xl font-bold text-white">{allModels.length}</div>
        </div>
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
          <div className="text-xs text-neutral-500 flex items-center gap-2 mb-2"><CheckCircle2 size={14} className="text-emerald-400" /> In Production</div>
          <div className="text-2xl font-bold text-emerald-400">{prodModels.length}</div>
        </div>
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
          <div className="text-xs text-neutral-500 flex items-center gap-2 mb-2"><Clock size={14} /> Last Training</div>
          <div className="text-sm font-bold text-neutral-300">
            {data?.last_training ? new Date(data.last_training.completed_at).toLocaleDateString() : 'Never'}
          </div>
        </div>
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
          <div className="text-xs text-neutral-500 flex items-center gap-2 mb-2"><Zap size={14} className="text-amber-400" /> Duration</div>
          <div className="text-sm font-bold text-neutral-300">
            {data?.last_training ? `${(data.last_training.duration_sec / 60).toFixed(0)}m` : '—'}
          </div>
        </div>
      </div>

      {/* Model Registry */}
      <div>
        <h3 className="text-sm font-semibold text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Brain size={16} className="text-purple-400" /> Model Registry
        </h3>
        {allModels.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {allModels.map((m, i) => <ModelCard key={i} model={m} />)}
          </div>
        ) : (
          <div className="border border-dashed border-neutral-800 rounded-xl p-8 text-center text-neutral-500">
            <Brain size={32} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">No models registered. Run a training cycle to populate.</p>
          </div>
        )}
      </div>

      {/* Training Log */}
      {liveLog.length > 0 && (
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-neutral-400 mb-3 flex items-center gap-2">
            <Activity size={16} className="text-cyan-400" /> Training Log
          </h3>
          <div className="bg-black rounded-lg p-3 font-mono text-xs text-neutral-400 max-h-48 overflow-y-auto">
            {liveLog.map((line, i) => <div key={i}>{line}</div>)}
          </div>
        </div>
      )}
    </div>
  );
}
