'use client';

import { useEffect, useState } from 'react';
import { Briefcase, Target, ShieldAlert, ArrowUpRight, TrendingUp, TrendingDown, Clock, Activity, CheckCircle, XCircle } from 'lucide-react';

interface ActiveTrade {
    id: number;
    symbol: string;
    tradeType: string;
    entryPrice: number;
    stoploss: number;
    target: number;
    currentPrice: number | null;
    entryTime: string;
    exitTime: string | null;
    status: string; // 'OPEN', 'SL_HIT', 'TARGET_HIT', 'MANUAL_EXIT'
    pnlPct: number | null;
    notes: string | null;
}

export default function ActiveTradesPage() {
    const [trades, setTrades] = useState<ActiveTrade[]>([]);
    const [loading, setLoading] = useState(true);
    const [processingId, setProcessingId] = useState<number | null>(null);

    const fetchTrades = async () => {
        try {
            const res = await fetch('/api/trades');
            const json = await res.json();
            if (json.success) {
                setTrades(json.data);
            }
        } catch (err) {
            console.error('Failed to fetch trades', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTrades();
        const interval = setInterval(fetchTrades, 15000);
        return () => clearInterval(interval);
    }, []);

    const closeTrade = async (id: number, finalStatus: string) => {
        if (!confirm(`Are you sure you want to mark this trade as ${finalStatus.replace('_', ' ')}?`)) return;
        
        setProcessingId(id);
        try {
            const res = await fetch(`/api/trades/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: finalStatus })
            });
            const data = await res.json();
            if (data.success) {
                await fetchTrades(); // reload
            } else {
                alert("Failed to close trade.");
            }
        } catch (err) {
            console.error("Error closing trade", err);
        } finally {
            setProcessingId(null);
        }
    };

    const deleteTrade = async (id: number) => {
        if (!confirm("Are you sure you want to delete this trade entirely from history?")) return;
        
        setProcessingId(id);
        try {
            const res = await fetch(`/api/trades/${id}`, { method: 'DELETE' });
            if (res.ok) {
                setTrades(trades.filter(t => t.id !== id));
            }
        } catch (err) {
            console.error("Error deleting trade", err);
        } finally {
            setProcessingId(null);
        }
    };

    return (
        <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6 font-mono">
            {/* Header */}
            <header className="flex justify-between items-center border-b border-neutral-800 pb-4 mb-6">
                <div className="flex items-center gap-3">
                    <Briefcase className="text-emerald-500" size={28} />
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                            Active Trades
                            <span className="bg-neutral-800 text-neutral-300 text-xs px-2 py-0.5 rounded border border-neutral-700 font-normal">
                                {trades.filter(t => t.status === 'OPEN').length} OPEN
                            </span>
                        </h1>
                        <p className="text-neutral-500 text-sm mt-1">Real-time execution tracking against SL/Target levels</p>
                    </div>
                </div>
            </header>

            {/* Trades Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                {loading && trades.length === 0 && (
                    <div className="col-span-full border border-dashed border-neutral-800 rounded-lg p-12 flex flex-col items-center justify-center text-neutral-500">
                        <Activity className="animate-pulse mx-auto mb-3" size={32} />
                        <p>Loading active portfolio...</p>
                    </div>
                )}
                
                {!loading && trades.length === 0 && (
                    <div className="col-span-full border border-dashed border-neutral-800 rounded-lg p-12 flex flex-col items-center justify-center text-neutral-500">
                        <Briefcase size={32} className="opacity-50 mb-3" />
                        <p>No trades tracked. Send setups from the Screener.</p>
                    </div>
                )}

                {trades.map((trade) => {
                    const isOpen = trade.status === 'OPEN';
                    const isWin = trade.status === 'TARGET_HIT';
                    const isLoss = trade.status === 'SL_HIT';
                    const currentPnl = trade.pnlPct || 0;
                    
                    return (
                        <div key={trade.id} className={`bg-neutral-900 border rounded-xl p-5 shadow-lg relative overflow-hidden transition-all ${
                            isOpen ? (currentPnl >= 0 ? 'border-emerald-500/30 shadow-[0_4px_24px_rgba(16,185,129,0.05)]' : 'border-red-500/30 shadow-[0_4px_24px_rgba(239,68,68,0.05)]')
                            : 'border-neutral-800 opacity-70 grayscale-[50%]'
                        }`}>
                            {/* Status Badge Top Right */}
                            <div className="absolute top-4 right-4 flex items-center gap-2">
                                {isOpen ? (
                                    <span className="flex items-center gap-1.5 text-xs font-bold text-blue-400 bg-blue-400/10 px-2 py-1 rounded">
                                        <span className="relative flex h-1.5 w-1.5">
                                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500"></span>
                                        </span>
                                        LIVE
                                    </span>
                                ) : (
                                    <span className={`flex items-center gap-1.5 text-xs font-bold px-2 py-1 rounded ${
                                        isWin ? 'text-emerald-400 bg-emerald-400/10' : 
                                        isLoss ? 'text-red-400 bg-red-400/10' : 
                                        'text-neutral-400 bg-neutral-800'
                                    }`}>
                                        {trade.status.replace('_', ' ')}
                                    </span>
                                )}
                            </div>

                            <div className="flex items-start gap-3 mb-6">
                                <div className={`h-12 w-12 rounded-lg flex flex-col items-center justify-center font-bold text-white shadow-inner ${
                                    isOpen ? (currentPnl >= 0 ? 'bg-gradient-to-br from-emerald-600 to-emerald-800' : 'bg-gradient-to-br from-red-600 to-red-800')
                                    : 'bg-neutral-800'
                                }`}>
                                    <span className="text-lg leading-none">{trade.symbol.substring(0, 1)}</span>
                                </div>
                                <div>
                                    <h2 className="text-2xl font-bold text-white tracking-tight">{trade.symbol}</h2>
                                    <p className="text-xs text-neutral-400 flex items-center gap-1 mt-1 font-medium">
                                        <Clock size={12} /> {new Date(trade.entryTime).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 mb-6">
                                <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800/50">
                                    <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-semibold mb-1">Entry Price</div>
                                    <div className="text-lg text-neutral-200">₹{trade.entryPrice.toFixed(2)}</div>
                                </div>
                                <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800/50">
                                    <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-semibold mb-1">Current/Exit</div>
                                    <div className={`text-lg font-bold ${isOpen ? (currentPnl >= 0 ? 'text-emerald-400' : 'text-red-400') : 'text-neutral-200'}`}>
                                        ₹{trade.currentPrice ? trade.currentPrice.toFixed(2) : '-.--'}
                                    </div>
                                </div>
                                <div className="bg-red-500/5 p-3 rounded-lg border border-red-500/10">
                                    <div className="text-[10px] text-red-400/70 uppercase tracking-widest font-semibold mb-1">Stop Loss</div>
                                    <div className="text-lg text-red-400">₹{trade.stoploss.toFixed(2)}</div>
                                </div>
                                <div className="bg-emerald-500/5 p-3 rounded-lg border border-emerald-500/10">
                                    <div className="text-[10px] text-emerald-400/70 uppercase tracking-widest font-semibold mb-1">Target</div>
                                    <div className="text-lg text-emerald-400">₹{trade.target.toFixed(2)}</div>
                                </div>
                            </div>

                            <div className="mb-6 flex items-center justify-between px-2">
                                <div className="text-sm font-medium text-neutral-400">Unrealized P&L</div>
                                <div className={`text-2xl font-black tracking-tighter ${
                                    currentPnl > 0 ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]' : 
                                    currentPnl < 0 ? 'text-red-400 drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]' : 
                                    'text-neutral-500'
                                }`}>
                                    {currentPnl > 0 ? '+' : ''}{currentPnl.toFixed(2)}%
                                </div>
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-2 pt-4 border-t border-neutral-800/80">
                                {isOpen ? (
                                    <>
                                        <button 
                                            onClick={() => closeTrade(trade.id, 'SL_HIT')}
                                            disabled={processingId === trade.id}
                                            className="flex-1 bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/20 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                                        >
                                            <ShieldAlert size={14} /> Hit SL
                                        </button>
                                        <button 
                                            onClick={() => closeTrade(trade.id, 'MANUAL_EXIT')}
                                            disabled={processingId === trade.id}
                                            className="flex-1 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-neutral-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                                        >
                                            <XCircle size={14} /> Close
                                        </button>
                                        <button 
                                            onClick={() => closeTrade(trade.id, 'TARGET_HIT')}
                                            disabled={processingId === trade.id}
                                            className="flex-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 border border-emerald-500/20 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                                        >
                                            <Target size={14} /> Target
                                        </button>
                                    </>
                                ) : (
                                    <button 
                                        onClick={() => deleteTrade(trade.id)}
                                        disabled={processingId === trade.id}
                                        className="w-full bg-neutral-900 hover:bg-neutral-800 text-neutral-500 border border-neutral-800 px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                                    >
                                        Delete Archival Record
                                    </button>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
