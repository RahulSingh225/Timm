'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Activity, TrendingUp, AlertTriangle, Zap,
  Database, RefreshCw, Clock, PlayCircle, Server,
  Wifi, WifiOff, Brain, Shield, ChevronDown, ChevronUp,
  MessageSquare, CheckCircle2, XCircle, Loader2, Gauge,
  Rabbit, HardDrive, Cpu, CalendarClock, Timer, Play, Pause,
  Plus, Trash2, Eye, EyeOff, Search, Target, ArrowUpRight, ArrowDownRight, ListFilter
} from 'lucide-react';

// ─── Types ──────────────────────────────────────────
interface TradeAlert {
  agent: string;
  symbol: string;
  close_price: number;
  signals: string[];
  timestamp?: string;
  summary?: string;
}

interface GlobalCues {
  overallBias: string;
  vixValue: number;
  spyChangePct: number;
  sgxNifty: number;
  giftNifty: number;
  vixChangePct: number;
}

interface PipelineStat {
  name: string;
  table: string;
  records: number;
  lastSync: string | null;
  status: 'healthy' | 'stale' | 'empty';
}

interface QueueInfo {
  name: string;
  messageCount: number;
  consumerCount: number;
}

interface SystemHealth {
  database: { status: string; latencyMs: number; error?: string };
  rabbitmq: { status: string; latencyMs: number; queues: QueueInfo[]; error?: string };
  llm: { status: string; latencyMs: number; model: string; baseUrl: string; error?: string };
  backend: { status: string; latencyMs: number; workersActive: number; error?: string };
}

interface AgentRun {
  id: number;
  agentName: string;
  runStatus: string;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  llmModel: string | null;
  llmPromptTokens: number | null;
  llmCompletionTokens: number | null;
  llmPromptPreview: string | null;
  llmResponsePreview: string | null;
  symbolProcessed: string | null;
  errorMessage: string | null;
}

interface AgentRunStats {
  total: number;
  success: number;
  failed: number;
  running: number;
  avgDurationMs: number;
  totalLlmTokens: number;
}

interface SchedulerJob {
  id: string;
  description: string;
  script: string;
  category: 'scraper' | 'producer';
  cron: Record<string, string>;
  cron_human: string;
  next_run_time: string | null;
  last_run: {
    status: string | null;
    finished_at: string | null;
    duration_ms: number | null;
    error: string | null;
  } | null;
  is_paused: boolean;
}

interface WatchlistItem {
  id: number;
  symbol: string;
  assetType: string;
  isActive: boolean;
  addedAt: string;
}

interface ScreenedStock {
  id: number;
  symbol: string;
  screenedAt: string;
  timeframe: string;
  tradeType: string;
  setupType: string;
  entryPrice: number | null;
  targetPrice: number | null;
  stoplossPrice: number | null;
  targetPct: number | null;
  riskPct: number | null;
  confidence: number | null;
  signals: string[];
  status: string;
}

// ─── SSE Hook with Auto-Reconnect ──────────────────
function useReconnectingSSE(
  url: string,
  onMessage: (data: TradeAlert) => void,
  maxRetries = 10
) {
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectCount, setReconnectCount] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      retryRef.current = 0;
      setReconnectCount(0);
    };

    es.onmessage = (event) => {
      try {
        const data: TradeAlert = JSON.parse(event.data);
        data.timestamp = new Date().toLocaleTimeString();
        onMessage(data);
      } catch (e) {
        console.error('[SSE] Failed to parse message:', e);
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      es.close();

      if (retryRef.current < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000);
        retryRef.current++;
        setReconnectCount(retryRef.current);
        console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${retryRef.current}/${maxRetries})`);
        timerRef.current = setTimeout(connect, delay);
      }
    };
  }, [url, onMessage, maxRetries]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [connect]);

  return { isConnected, reconnectCount };
}

// ─── Time Ago Helper ────────────────────────────────
function timeAgo(isoString: string | null): string {
  if (!isoString) return 'Never';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Status Dot Component ───────────────────────────
function StatusDot({ status, size = 'sm' }: { status: string; size?: 'sm' | 'md' }) {
  const sizeClass = size === 'md' ? 'h-2.5 w-2.5' : 'h-2 w-2';
  const colors: Record<string, string> = {
    connected: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
    healthy: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
    error: 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]',
    stale: 'bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.5)]',
    empty: 'bg-neutral-600',
    RUNNING: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
    STOPPED: 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]',
  };
  return <div className={`${sizeClass} rounded-full ${colors[status] || 'bg-neutral-600'}`} />;
}

// ─── Main Component ─────────────────────────────────
export default function CommandCenter() {
  const [alerts, setAlerts] = useState<TradeAlert[]>([]);
  const [isProcessing, setIsProcessing] = useState<string | null>(null);
  const [workers, setWorkers] = useState<Record<string, { name: string; status: string; pid: number | null }>>({});
  const [globalCues, setGlobalCues] = useState<GlobalCues | null>(null);
  const [pipelines, setPipelines] = useState<PipelineStat[]>([]);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentRunStats, setAgentRunStats] = useState<AgentRunStats | null>(null);
  const [expandedRun, setExpandedRun] = useState<number | null>(null);
  const [showAllPipelines, setShowAllPipelines] = useState(false);
  const [schedulerJobs, setSchedulerJobs] = useState<SchedulerJob[]>([]);
  const [triggeringJob, setTriggeringJob] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  // Watchlist & Screener state
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [screenedStocks, setScreenedStocks] = useState<ScreenedStock[]>([]);
  const [showScreener, setShowScreener] = useState(true);

  // SSE with auto-reconnect
  const handleAlert = useCallback((newAlert: TradeAlert) => {
    setAlerts((prev) => [newAlert, ...prev].slice(0, 50));
  }, []);

  const { isConnected, reconnectCount } = useReconnectingSSE('/api/alerts', handleAlert);

  // ─── Data Fetchers ──────────────────────────────
  const fetchWorkers = async () => {
    try {
      const res = await fetch('/api/system/workers');
      const data = await res.json();
      if (!data.error) setWorkers(data);
    } catch {}
  };

  const fetchGlobalCues = async () => {
    try {
      const res = await fetch('/api/global');
      const { data } = await res.json();
      if (data) setGlobalCues(data);
    } catch {}
  };

  const fetchPipelines = async () => {
    try {
      const res = await fetch('/api/system/pipelines');
      const json = await res.json();
      if (json.success) setPipelines(json.data);
    } catch {}
  };

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/system/health');
      const data = await res.json();
      setHealth(data);
    } catch {}
  };

  const fetchAgentRuns = async () => {
    try {
      const res = await fetch('/api/system/agent-runs?limit=20&hours=24');
      const json = await res.json();
      if (json.success) {
        setAgentRuns(json.data);
        setAgentRunStats(json.stats);
      }
    } catch {}
  };

  const fetchScheduler = async () => {
    try {
      const res = await fetch('/api/system/scheduler');
      const json = await res.json();
      if (json.jobs) setSchedulerJobs(json.jobs);
    } catch {}
  };

  const triggerSchedulerJob = async (jobId: string) => {
    setTriggeringJob(jobId);
    try {
      await fetch('/api/system/scheduler', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
      });
      // Refresh scheduler status after a brief delay
      setTimeout(fetchScheduler, 2000);
    } catch {
      alert('Failed to trigger job');
    } finally {
      setTimeout(() => setTriggeringJob(null), 3000);
    }
  };

  // ─── Watchlist Fetchers ──────────────────────────
  const fetchWatchlist = async () => {
    try {
      const res = await fetch('/api/watchlist');
      const json = await res.json();
      if (json.success) setWatchlistItems(json.data);
    } catch {}
  };

  const addToWatchlist = async () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    try {
      await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, asset_type: 'EQUITY' }),
      });
      setNewSymbol('');
      fetchWatchlist();
    } catch {}
  };

  const toggleWatchlistItem = async (id: number, currentActive: boolean) => {
    try {
      await fetch('/api/watchlist', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, is_active: !currentActive }),
      });
      fetchWatchlist();
    } catch {}
  };

  const removeFromWatchlist = async (id: number) => {
    try {
      await fetch('/api/watchlist', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
      fetchWatchlist();
    } catch {}
  };

  const fetchScreenedStocks = async () => {
    try {
      const res = await fetch('/api/screener/results?limit=20');
      const json = await res.json();
      if (json.success) setScreenedStocks(json.data);
    } catch {}
  };

  useEffect(() => {
    fetchWorkers();
    fetchGlobalCues();
    fetchPipelines();
    fetchHealth();
    fetchAgentRuns();
    fetchScheduler();
    fetchWatchlist();
    fetchScreenedStocks();

    const workerInterval = setInterval(fetchWorkers, 5000);
    const pipelineInterval = setInterval(fetchPipelines, 30000);
    const healthInterval = setInterval(fetchHealth, 15000);
    const agentInterval = setInterval(fetchAgentRuns, 10000);
    const schedulerInterval = setInterval(fetchScheduler, 10000);
    const screenerInterval = setInterval(fetchScreenedStocks, 30000);

    return () => {
      clearInterval(workerInterval);
      clearInterval(pipelineInterval);
      clearInterval(healthInterval);
      clearInterval(agentInterval);
      clearInterval(schedulerInterval);
      clearInterval(screenerInterval);
    };
  }, []);

  const toggleWorker = async (workerId: string, currentStatus: string) => {
    const action = currentStatus === 'RUNNING' ? 'stop' : 'start';
    setIsProcessing(workerId);
    try {
      await fetch('/api/system/workers', {
        method: 'POST',
        body: JSON.stringify({ worker_id: workerId, action }),
      });
      await fetchWorkers();
    } catch {
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: actionId }),
      });
      if (!response.ok) throw new Error('Failed to trigger task');
      setTimeout(() => setIsProcessing(null), 500);
    } catch {
      setIsProcessing(null);
      alert('Failed to execute command: Broker might be offline or task invalid.');
    }
  };

  // Pipeline display — show top 4 or all
  const displayPipelines = showAllPipelines ? pipelines : pipelines.slice(0, 4);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6 font-mono">
      {/* ═══════════ HEADER ═══════════ */}
      <header className="flex justify-between items-center border-b border-neutral-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <Activity className="text-purple-500" size={28} />
          <h1 className="text-2xl font-bold tracking-tight text-white">
            QUANT DESK <span className="text-neutral-500 text-sm">v3.0</span>
          </h1>
        </div>
        <div className="flex items-center gap-3 text-sm flex-wrap">
          {globalCues && (
            <div
              className={`flex items-center gap-3 px-3 py-1.5 rounded border ${
                globalCues.overallBias === 'RISK_ON'
                  ? 'bg-emerald-900/20 border-emerald-900/50 text-emerald-400'
                  : globalCues.overallBias === 'RISK_OFF'
                  ? 'bg-red-900/20 border-red-900/50 text-red-400'
                  : 'bg-neutral-900 border-neutral-800 text-neutral-300'
              }`}
            >
              <div className="font-bold border-r border-inherit pr-3">
                {globalCues.overallBias?.replace('_', ' ') || 'NEUTRAL'}
              </div>
              <div className="flex items-center gap-3 text-xs opacity-90">
                <span>VIX {globalCues.vixValue}</span>
                <span>
                  SPY {globalCues.spyChangePct > 0 ? '+' : ''}
                  {globalCues.spyChangePct}%
                </span>
                <span>GIFT {globalCues.giftNifty || globalCues.sgxNifty}</span>
              </div>
            </div>
          )}

          {/* Connection Status */}
          {isConnected ? (
            <span className="flex items-center gap-2 text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-3 py-1.5 rounded">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              RabbitMQ Live
            </span>
          ) : (
            <span className="flex items-center gap-2 text-red-400 bg-red-400/10 border border-red-400/20 px-3 py-1.5 rounded">
              <WifiOff size={14} />
              Queue Disconnected
              {reconnectCount > 0 && (
                <span className="text-[10px] text-neutral-500 ml-1">
                  retry {reconnectCount}
                </span>
              )}
            </span>
          )}
        </div>
      </header>

      {/* ═══════════ SYSTEM HEALTH BAR ═══════════ */}
      {health && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {/* Database */}
          <div className="bg-neutral-900/80 border border-neutral-800 rounded-lg p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <HardDrive size={16} className="text-blue-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-neutral-400 uppercase">PostgreSQL</span>
                <StatusDot status={health.database.status} />
              </div>
              <div className="text-xs text-neutral-500 mt-0.5">
                {health.database.status === 'connected'
                  ? `${health.database.latencyMs}ms`
                  : health.database.error?.substring(0, 30) || 'Offline'}
              </div>
            </div>
          </div>

          {/* RabbitMQ */}
          <div className="bg-neutral-900/80 border border-neutral-800 rounded-lg p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/10 border border-orange-500/20">
              <Rabbit size={16} className="text-orange-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-neutral-400 uppercase">RabbitMQ</span>
                <StatusDot status={health.rabbitmq.status} />
              </div>
              <div className="text-xs text-neutral-500 mt-0.5">
                {health.rabbitmq.status === 'connected'
                  ? `${health.rabbitmq.latencyMs}ms · ${health.rabbitmq.queues.reduce((s, q) => s + Math.max(0, q.messageCount), 0)} msgs queued`
                  : health.rabbitmq.error?.substring(0, 30) || 'Offline'}
              </div>
            </div>
          </div>

          {/* LLM */}
          <div className="bg-neutral-900/80 border border-neutral-800 rounded-lg p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20">
              <Brain size={16} className="text-purple-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-neutral-400 uppercase">Ollama LLM</span>
                <StatusDot status={health.llm.status} />
              </div>
              <div className="text-xs text-neutral-500 mt-0.5 truncate">
                {health.llm.status === 'connected'
                  ? `${health.llm.model} · ${health.llm.latencyMs}ms`
                  : health.llm.error?.substring(0, 30) || 'Offline'}
              </div>
            </div>
          </div>

          {/* Python Backend */}
          <div className="bg-neutral-900/80 border border-neutral-800 rounded-lg p-3 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <Cpu size={16} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-neutral-400 uppercase">FastAPI</span>
                <StatusDot status={health.backend.status} />
              </div>
              <div className="text-xs text-neutral-500 mt-0.5">
                {health.backend.status === 'connected'
                  ? `${health.backend.workersActive} workers · ${health.backend.latencyMs}ms`
                  : health.backend.error?.substring(0, 30) || 'Offline'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════ PIPELINE TELEMETRY (REAL) ═══════════ */}
      <div className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {displayPipelines.map((pipe, idx) => (
            <div
              key={idx}
              className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 flex flex-col justify-between hover:border-neutral-700 transition-colors"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-sm font-semibold text-neutral-300">{pipe.name}</span>
                <StatusDot status={pipe.status} size="md" />
              </div>
              <div>
                <div className="text-2xl font-bold text-white mb-1">
                  {pipe.records.toLocaleString()}{' '}
                  <span className="text-xs text-neutral-500 font-normal">rows</span>
                </div>
                <div className="flex items-center gap-1 text-xs text-neutral-500">
                  <Clock size={12} /> Last sync: {timeAgo(pipe.lastSync)}
                </div>
              </div>
            </div>
          ))}
        </div>
        {pipelines.length > 4 && (
          <button
            onClick={() => setShowAllPipelines(!showAllPipelines)}
            className="mt-3 flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors mx-auto"
          >
            {showAllPipelines ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showAllPipelines ? 'Show less' : `Show all ${pipelines.length} pipelines`}
          </button>
        )}
      </div>

      {/* ═══════════ SCHEDULER TIMELINE ═══════════ */}
      {schedulerJobs.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <CalendarClock size={16} className="text-cyan-400" /> Automated Scheduler
            <span className="bg-cyan-500/10 text-cyan-400 text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/20">
              {schedulerJobs.length} jobs
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {schedulerJobs.map((job) => {
              const isTriggering = triggeringJob === job.id;
              const lastStatus = job.last_run?.status;
              const isExpanded = expandedJob === job.id;

              // Calculate countdown
              let countdown = '';
              if (job.next_run_time) {
                const diff = new Date(job.next_run_time).getTime() - Date.now();
                if (diff > 0) {
                  const hrs = Math.floor(diff / 3600000);
                  const mins = Math.floor((diff % 3600000) / 60000);
                  countdown = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;
                } else {
                  countdown = 'due';
                }
              }

              const categoryColor = job.category === 'scraper'
                ? 'border-amber-500/20 bg-amber-500/5'
                : 'border-cyan-500/20 bg-cyan-500/5';
              const categoryBadge = job.category === 'scraper'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';

              return (
                <div
                  key={job.id}
                  className={`border rounded-lg overflow-hidden transition-all duration-200 hover:border-neutral-600 ${categoryColor}`}
                >
                  <div className="p-3">
                    {/* Header Row */}
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border ${categoryBadge}`}>
                            {job.category}
                          </span>
                          {job.is_paused && (
                            <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-500 border border-neutral-700">
                              paused
                            </span>
                          )}
                        </div>
                        <h3 className="text-sm font-medium text-neutral-200 truncate">{job.description}</h3>
                        <p className="text-[10px] text-neutral-500 font-mono mt-0.5">{job.cron_human}</p>
                      </div>

                      <button
                        onClick={() => triggerSchedulerJob(job.id)}
                        disabled={isTriggering || job.is_paused}
                        className="shrink-0 ml-2 px-2 py-1.5 rounded text-[10px] font-bold bg-neutral-800 border border-neutral-700 hover:border-purple-500/50 hover:bg-purple-500/10 text-neutral-300 hover:text-purple-300 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                        title="Run now"
                      >
                        {isTriggering ? (
                          <Loader2 size={10} className="animate-spin" />
                        ) : (
                          <Play size={10} />
                        )}
                        {isTriggering ? 'Running' : 'Run Now'}
                      </button>
                    </div>

                    {/* Status Row */}
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-neutral-800/50">
                      {/* Last Run */}
                      <div className="flex items-center gap-1.5">
                        {lastStatus === 'SUCCESS' ? (
                          <CheckCircle2 size={12} className="text-emerald-400" />
                        ) : lastStatus === 'FAILED' || lastStatus === 'TIMEOUT' ? (
                          <XCircle size={12} className="text-red-400" />
                        ) : (
                          <Clock size={12} className="text-neutral-600" />
                        )}
                        <span className="text-[11px] text-neutral-400">
                          {job.last_run?.finished_at
                            ? timeAgo(job.last_run.finished_at)
                            : 'Never run'}
                        </span>
                        {job.last_run?.duration_ms && (
                          <span className="text-[10px] text-neutral-600">
                            ({(job.last_run.duration_ms / 1000).toFixed(1)}s)
                          </span>
                        )}
                      </div>

                      {/* Next Run */}
                      {job.next_run_time && !job.is_paused && (
                        <div className="flex items-center gap-1.5">
                          <Timer size={11} className="text-cyan-500" />
                          <span className="text-[11px] text-cyan-400 font-mono">
                            {countdown === 'due' ? 'Due now' : `in ${countdown}`}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Error expand button */}
                    {job.last_run?.error && (
                      <button
                        onClick={() => setExpandedJob(isExpanded ? null : job.id)}
                        className="mt-2 text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1"
                      >
                        {isExpanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                        {isExpanded ? 'Hide error' : 'Show error'}
                      </button>
                    )}
                  </div>

                  {/* Expanded Error */}
                  {isExpanded && job.last_run?.error && (
                    <div className="border-t border-neutral-800/50 p-3 bg-red-950/10">
                      <pre className="text-[10px] text-red-400/80 whitespace-pre-wrap overflow-x-auto max-h-24">
                        {job.last_run.error}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ═══════════ RABBITMQ QUEUE DEPTH ═══════════ */}
      {health?.rabbitmq?.status === 'connected' && health.rabbitmq.queues.length > 0 && (
        <div className="mb-6 bg-neutral-900/50 border border-neutral-800 rounded-lg p-4">
          <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <Rabbit size={16} className="text-orange-400" /> Queue Depth Monitor
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {health.rabbitmq.queues.map((q) => (
              <div
                key={q.name}
                className="bg-neutral-950 border border-neutral-800 rounded-lg p-3"
              >
                <div className="text-xs text-neutral-500 truncate mb-1" title={q.name}>
                  {q.name.replace(/_/g, ' ')}
                </div>
                <div className="flex items-baseline gap-2">
                  <span
                    className={`text-xl font-bold ${
                      q.messageCount > 100
                        ? 'text-red-400'
                        : q.messageCount > 10
                        ? 'text-yellow-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {q.messageCount >= 0 ? q.messageCount : '—'}
                  </span>
                  <span className="text-[10px] text-neutral-600">msgs</span>
                </div>
                <div className="text-[10px] text-neutral-600 mt-1">
                  {q.consumerCount} consumer{q.consumerCount !== 1 ? 's' : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══════════ VISUAL SCREENER ═══════════ */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm text-neutral-400 uppercase tracking-wider flex items-center gap-2">
            <Target size={16} className="text-pink-400" /> Visual Screener
            {screenedStocks.length > 0 && (
              <span className="bg-pink-500/10 text-pink-400 text-[10px] px-1.5 py-0.5 rounded border border-pink-500/20">
                {screenedStocks.length} results
              </span>
            )}
          </h2>
          <button
            onClick={() => setShowScreener(!showScreener)}
            className="text-xs text-neutral-500 hover:text-neutral-300 flex items-center gap-1"
          >
            {showScreener ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showScreener ? 'Collapse' : 'Expand'}
          </button>
        </div>

        {showScreener && (
          screenedStocks.length === 0 ? (
            <div className="border border-dashed border-neutral-800 rounded-lg p-8 flex flex-col items-center justify-center text-neutral-500">
              <Search size={24} className="mb-2 opacity-50" />
              <p className="text-xs">No screened stocks yet. Run the data pipeline to generate results.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {screenedStocks.map((stock) => {
                const isBullish = !stock.setupType.includes('BEARISH') && !stock.setupType.includes('GAP_DOWN');
                const dirColor = isBullish ? 'text-emerald-400' : 'text-red-400';
                const dirBg = isBullish ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20';

                return (
                  <div
                    key={stock.id}
                    className={`border rounded-lg p-3 transition-all hover:border-neutral-600 ${dirBg}`}
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-bold text-white">{stock.symbol}</h3>
                          {isBullish ? (
                            <ArrowUpRight size={14} className="text-emerald-400" />
                          ) : (
                            <ArrowDownRight size={14} className="text-red-400" />
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
                            {stock.tradeType}
                          </span>
                          <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
                            {stock.setupType.replace(/_/g, ' ')}
                          </span>
                        </div>
                      </div>

                      {/* Confidence */}
                      <div className="text-right">
                        <div className={`text-lg font-bold ${stock.confidence && stock.confidence >= 70 ? 'text-emerald-400' : stock.confidence && stock.confidence >= 50 ? 'text-yellow-400' : 'text-neutral-400'}`}>
                          {stock.confidence || 0}%
                        </div>
                        <div className="text-[9px] text-neutral-500 uppercase">Confidence</div>
                      </div>
                    </div>

                    {/* Trade Levels */}
                    {stock.entryPrice && (
                      <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-neutral-800/50">
                        <div>
                          <div className="text-[9px] text-neutral-500 uppercase">Entry</div>
                          <div className="text-sm font-mono text-neutral-200">₹{stock.entryPrice?.toFixed(1)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-neutral-500 uppercase">Target</div>
                          <div className="text-sm font-mono text-emerald-400">₹{stock.targetPrice?.toFixed(1)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-neutral-500 uppercase">Stoploss</div>
                          <div className="text-sm font-mono text-red-400">₹{stock.stoplossPrice?.toFixed(1)}</div>
                        </div>
                      </div>
                    )}

                    {/* Signals */}
                    <div className="mt-2 pt-2 border-t border-neutral-800/50 space-y-1">
                      {(stock.signals || []).slice(0, 3).map((sig, i) => (
                        <p key={i} className="text-[10px] text-neutral-400 flex items-start gap-1">
                          <CheckCircle2 size={10} className={`shrink-0 mt-0.5 ${dirColor}`} />
                          {typeof sig === 'string' ? sig : (sig as any)?.signal || JSON.stringify(sig)}
                        </p>
                      ))}
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between mt-2 text-[9px] text-neutral-600">
                      <span>{stock.timeframe}</span>
                      <span>{timeAgo(stock.screenedAt)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )
        )}
      </div>

      {/* ═══════════ MAIN GRID ═══════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* ─── Left: Live Alerts + Agent Runs ─── */}
        <div className="lg:col-span-3 space-y-6">
          {/* Live Alerts */}
          <div>
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Zap size={16} /> Live Setup Stream
              {alerts.length > 0 && (
                <span className="bg-blue-500/10 text-blue-400 text-[10px] px-1.5 py-0.5 rounded border border-blue-500/20">
                  {alerts.length}
                </span>
              )}
            </h2>

            {alerts.length === 0 ? (
              <div className="border border-dashed border-neutral-800 rounded-lg p-12 flex flex-col items-center justify-center text-neutral-500">
                <Database size={32} className="mb-3 opacity-50" />
                <p>Awaiting quantitative setups...</p>
                {!isConnected && reconnectCount > 0 && (
                  <p className="text-xs text-neutral-600 mt-2">
                    SSE reconnecting... attempt {reconnectCount}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {alerts.map((alert, idx) => (
                  <div
                    key={idx}
                    className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 shadow-lg hover:border-neutral-700 transition-all duration-300"
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex items-center gap-3">
                        <span className="bg-blue-500/10 text-blue-400 text-xs px-2 py-1 rounded border border-blue-500/20">
                          {alert.agent} Agent
                        </span>
                        <h3 className="text-xl font-bold text-white">{alert.symbol}</h3>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold tracking-wide">
                          ₹{alert.close_price?.toFixed(2)}
                        </div>
                        <div className="text-xs text-neutral-500">{alert.timestamp}</div>
                      </div>
                    </div>

                    {alert.summary && (
                      <div className="bg-purple-500/5 border border-purple-500/20 rounded p-3 mb-3">
                        <div className="flex items-center gap-1.5 text-[10px] text-purple-400 uppercase mb-1">
                          <Brain size={10} /> LLM Brief
                        </div>
                        <p className="text-sm text-neutral-300">{alert.summary}</p>
                      </div>
                    )}

                    <div className="space-y-2 pl-2 border-l-2 border-neutral-700">
                      {alert.signals.map((signal, sIdx) => (
                        <p key={sIdx} className="text-sm flex items-start gap-2">
                          {signal.includes('BEARISH') || signal.includes('DEATH') ? (
                            <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
                          ) : (
                            <TrendingUp size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                          )}
                          <span className="text-neutral-200">{signal}</span>
                        </p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ─── Agent Runs / LLM Observability ─── */}
          <div>
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Brain size={16} className="text-purple-400" /> Agent Runs & LLM Activity
              {agentRunStats && (
                <span className="flex items-center gap-2 text-[10px] ml-2">
                  <span className="text-emerald-400">{agentRunStats.success} ok</span>
                  <span className="text-red-400">{agentRunStats.failed} fail</span>
                  <span className="text-yellow-400">{agentRunStats.running} running</span>
                  {agentRunStats.totalLlmTokens > 0 && (
                    <span className="text-neutral-500">
                      · {agentRunStats.totalLlmTokens.toLocaleString()} tokens
                    </span>
                  )}
                </span>
              )}
            </h2>

            {agentRuns.length === 0 ? (
              <div className="border border-dashed border-neutral-800 rounded-lg p-8 flex flex-col items-center justify-center text-neutral-500">
                <Loader2 size={24} className="mb-2 opacity-50" />
                <p className="text-xs">No agent runs in the last 24h</p>
              </div>
            ) : (
              <div className="space-y-2">
                {agentRuns.map((run) => (
                  <div
                    key={run.id}
                    className="bg-neutral-900/80 border border-neutral-800 rounded-lg overflow-hidden hover:border-neutral-700 transition-colors"
                  >
                    <button
                      onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                      className="w-full p-3 flex items-center gap-3 text-left"
                    >
                      {/* Status Icon */}
                      {run.runStatus === 'SUCCESS' ? (
                        <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                      ) : run.runStatus === 'FAILED' ? (
                        <XCircle size={16} className="text-red-400 shrink-0" />
                      ) : (
                        <Loader2 size={16} className="text-yellow-400 animate-spin shrink-0" />
                      )}

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-neutral-200 capitalize">
                            {run.agentName.replace(/_/g, ' ')}
                          </span>
                          {run.symbolProcessed && (
                            <span className="bg-neutral-800 text-neutral-400 text-[10px] px-1.5 py-0.5 rounded">
                              {run.symbolProcessed}
                            </span>
                          )}
                          {run.llmModel && (
                            <span className="bg-purple-500/10 text-purple-400 text-[10px] px-1.5 py-0.5 rounded border border-purple-500/20">
                              <Brain size={8} className="inline mr-0.5" />
                              {run.llmModel}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 text-xs text-neutral-500 shrink-0">
                        {run.durationMs && (
                          <span className="flex items-center gap-1">
                            <Gauge size={10} /> {run.durationMs}ms
                          </span>
                        )}
                        {(run.llmPromptTokens || run.llmCompletionTokens) && (
                          <span>
                            {(run.llmPromptTokens || 0) + (run.llmCompletionTokens || 0)} tok
                          </span>
                        )}
                        <span>{timeAgo(run.startedAt)}</span>
                        {expandedRun === run.id ? (
                          <ChevronUp size={14} />
                        ) : (
                          <ChevronDown size={14} />
                        )}
                      </div>
                    </button>

                    {/* Expanded Details */}
                    {expandedRun === run.id && (
                      <div className="border-t border-neutral-800 p-4 space-y-3 text-sm">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">Status</span>
                            <div className={`font-mono text-sm ${
                              run.runStatus === 'SUCCESS' ? 'text-emerald-400' :
                              run.runStatus === 'FAILED' ? 'text-red-400' : 'text-yellow-400'
                            }`}>
                              {run.runStatus}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">Duration</span>
                            <div className="font-mono text-sm text-neutral-300">
                              {run.durationMs ? `${run.durationMs}ms` : '—'}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">Prompt Tokens</span>
                            <div className="font-mono text-sm text-neutral-300">
                              {run.llmPromptTokens ?? '—'}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">Completion Tokens</span>
                            <div className="font-mono text-sm text-neutral-300">
                              {run.llmCompletionTokens ?? '—'}
                            </div>
                          </div>
                        </div>

                        {run.llmPromptPreview && (
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">Prompt Preview</span>
                            <pre className="mt-1 bg-neutral-950 border border-neutral-800 rounded p-2 text-xs text-neutral-400 overflow-x-auto max-h-32 whitespace-pre-wrap">
                              {run.llmPromptPreview}
                            </pre>
                          </div>
                        )}

                        {run.llmResponsePreview && (
                          <div>
                            <span className="text-[10px] text-neutral-500 uppercase">LLM Response</span>
                            <pre className="mt-1 bg-neutral-950 border border-neutral-800 rounded p-2 text-xs text-emerald-400/70 overflow-x-auto max-h-32 whitespace-pre-wrap">
                              {run.llmResponsePreview}
                            </pre>
                          </div>
                        )}

                        {run.errorMessage && (
                          <div>
                            <span className="text-[10px] text-red-500 uppercase">Error</span>
                            <pre className="mt-1 bg-red-950/30 border border-red-900/30 rounded p-2 text-xs text-red-400 overflow-x-auto">
                              {run.errorMessage}
                            </pre>
                          </div>
                        )}

                        <div className="text-[10px] text-neutral-600">
                          Started: {new Date(run.startedAt).toLocaleString()}
                          {run.finishedAt && ` · Finished: ${new Date(run.finishedAt).toLocaleString()}`}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ─── Right Sidebar ─── */}
        <div className="space-y-6">
          {/* System Overrides */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-4 border-b border-neutral-800 pb-2 flex items-center gap-2">
              <ListFilter size={16} className="text-teal-400" /> Watchlist
              <span className="text-[10px] text-neutral-500 ml-auto">
                {watchlistItems.filter(w => w.isActive).length}/{watchlistItems.length} active
              </span>
            </h2>

            {/* Add symbol */}
            <div className="flex gap-1 mb-3">
              <input
                type="text"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && addToWatchlist()}
                placeholder="Add symbol..."
                className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-2 py-1.5 text-xs text-neutral-200 placeholder:text-neutral-600 focus:outline-none focus:border-purple-500/50"
              />
              <button
                onClick={addToWatchlist}
                className="px-2 py-1.5 bg-purple-500/10 border border-purple-500/30 rounded text-purple-400 hover:bg-purple-500/20 transition-colors"
              >
                <Plus size={14} />
              </button>
            </div>

            {/* Watchlist items */}
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {watchlistItems.map((item) => (
                <div
                  key={item.id}
                  className={`flex items-center justify-between text-xs p-1.5 rounded transition-colors ${
                    item.isActive ? 'hover:bg-neutral-800/50' : 'opacity-40'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot status={item.isActive ? 'healthy' : 'empty'} />
                    <span className="text-neutral-300 font-medium truncate">{item.symbol}</span>
                    <span className="text-[9px] text-neutral-600">{item.assetType}</span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => toggleWatchlistItem(item.id, item.isActive)}
                      className="p-1 hover:bg-neutral-700 rounded transition-colors text-neutral-500 hover:text-neutral-300"
                      title={item.isActive ? 'Deactivate' : 'Activate'}
                    >
                      {item.isActive ? <Eye size={12} /> : <EyeOff size={12} />}
                    </button>
                    <button
                      onClick={() => removeFromWatchlist(item.id)}
                      className="p-1 hover:bg-red-900/30 rounded transition-colors text-neutral-600 hover:text-red-400"
                      title="Remove"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
              {watchlistItems.length === 0 && (
                <p className="text-[10px] text-neutral-600 text-center py-3">
                  No symbols in watchlist. Add one above.
                </p>
              )}
            </div>
          </div>

          {/* System Overrides */}
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
                {isProcessing === 'sync_fii' && (
                  <RefreshCw size={14} className="animate-spin text-neutral-500" />
                )}
              </button>

              <button
                onClick={() => triggerAction('sync_nsdl')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 bg-neutral-950 border border-neutral-800 hover:border-purple-500/50 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-neutral-300">
                  <PlayCircle size={14} className="text-purple-400" /> Force NSDL Sector Scrape
                </span>
                {isProcessing === 'sync_nsdl' && (
                  <RefreshCw size={14} className="animate-spin text-neutral-500" />
                )}
              </button>

              <button
                onClick={() => triggerAction('sync_yfinance')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 bg-neutral-950 border border-neutral-800 hover:border-purple-500/50 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-neutral-300">
                  <PlayCircle size={14} className="text-purple-400" /> Force yFinance Ingest
                </span>
                {isProcessing === 'sync_yfinance' && (
                  <RefreshCw size={14} className="animate-spin text-neutral-500" />
                )}
              </button>

              <button
                onClick={() => triggerAction('seed_db')}
                disabled={isProcessing !== null}
                className="w-full flex items-center justify-between p-3 mt-3 bg-yellow-500/10 border border-yellow-500/30 hover:border-yellow-500 rounded transition-colors disabled:opacity-50 text-sm"
              >
                <span className="flex items-center gap-2 text-yellow-500 font-medium">
                  <Database size={14} /> Seed Historical JSONs
                </span>
                {isProcessing === 'seed_db' && (
                  <RefreshCw size={14} className="animate-spin text-yellow-500" />
                )}
              </button>
            </div>
          </div>

          {/* Python Fleet Status */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
            <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-4 border-b border-neutral-800 pb-2 flex items-center gap-2">
              <Zap size={16} /> Python Fleet Status
            </h2>
            <div className="space-y-2">
              {Object.entries(workers).map(([id, info]) => (
                <div
                  key={id}
                  className="flex justify-between items-center text-sm p-2 hover:bg-neutral-800/50 rounded transition-colors group"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot status={info.status} />
                    <div className="flex flex-col min-w-0">
                      <span className="text-neutral-300 font-medium capitalize truncate">
                        {id}
                      </span>
                      <span className="text-[10px] text-neutral-600 font-mono truncate">
                        {info.name}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => toggleWorker(id, info.status)}
                    disabled={isProcessing === id}
                    className={`px-2 py-1 rounded text-[10px] font-bold transition-all shrink-0 ${
                      info.status === 'RUNNING'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-red-500/20 hover:text-red-400 hover:border-red-500/30'
                        : 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-emerald-500/20 hover:text-emerald-400 hover:border-emerald-500/30'
                    }`}
                  >
                    {isProcessing === id
                      ? '...'
                      : info.status === 'RUNNING'
                      ? 'STOP'
                      : 'START'}
                  </button>
                </div>
              ))}
              {Object.keys(workers).length === 0 && (
                <p className="text-xs text-neutral-600 text-center py-4">
                  No workers detected.{' '}
                  {health?.backend?.status !== 'connected' && (
                    <span className="text-red-500">FastAPI backend is offline.</span>
                  )}
                </p>
              )}
            </div>
          </div>

          {/* LLM Connection Info */}
          {health?.llm && (
            <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
              <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-4 border-b border-neutral-800 pb-2 flex items-center gap-2">
                <Brain size={16} className="text-purple-400" /> LLM Connection
              </h2>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-neutral-500">Status</span>
                  <span
                    className={
                      health.llm.status === 'connected' ? 'text-emerald-400' : 'text-red-400'
                    }
                  >
                    {health.llm.status === 'connected' ? 'Connected' : 'Offline'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Model</span>
                  <span className="text-neutral-300 font-mono">{health.llm.model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Endpoint</span>
                  <span className="text-neutral-400 text-xs font-mono truncate max-w-[160px]">
                    {health.llm.baseUrl}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Latency</span>
                  <span className="text-neutral-300">{health.llm.latencyMs}ms</span>
                </div>
                {health.llm.error && (
                  <div className="bg-red-950/20 border border-red-900/30 rounded p-2 text-xs text-red-400">
                    {health.llm.error}
                  </div>
                )}
                {agentRunStats && agentRunStats.totalLlmTokens > 0 && (
                  <div className="border-t border-neutral-800 pt-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-neutral-500">24h Token Usage</span>
                      <span className="text-purple-400 font-mono">
                        {agentRunStats.totalLlmTokens.toLocaleString()}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs mt-1">
                      <span className="text-neutral-500">Avg Response</span>
                      <span className="text-neutral-400 font-mono">
                        {agentRunStats.avgDurationMs}ms
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}