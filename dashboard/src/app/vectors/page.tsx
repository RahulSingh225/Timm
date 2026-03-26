'use client';

import { useEffect, useState } from 'react';
import { Activity, Target, Brain, TrendingUp, TrendingDown, Clock, Database } from 'lucide-react';

interface VectorSignal {
    symbol: string;
    timestamp: string;
    raw_scalar: number;
    iv_adjusted_scalar: number;
    current_atm_iv: number;
    signed_accumulation: number;
    predicted_next_move: number;
    linear_m: number;
    linear_b: number;
    confidence: number;
    signal: 'bullish' | 'bearish' | 'neutral';
}

export default function VectorLab() {
    const [liveSignal, setLiveSignal] = useState<VectorSignal | null>(null);
    const [history, setHistory] = useState<VectorSignal[]>([]);
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        // 1. Fetch historical signals
        const fetchHistory = async () => {
            try {
                const res = await fetch('/api/vectors/history');
                const data = await res.json();
                if (Array.isArray(data)) {
                    // Normalize the snake_case keys from DB if they came back in camelCase (Drizzle does this sometimes depending on queries, but we defined columns)
                    // Actually, our Drizzle schema maps camelCase in JS to snake_case in DB.
                    // The API returns the JS property names (camelCase). Let's handle both.
                    const mappedData = data.map((d: any) => ({
                        symbol: d.symbol,
                        timestamp: d.timestamp,
                        raw_scalar: d.rawScalar ?? d.raw_scalar,
                        iv_adjusted_scalar: d.ivAdjustedScalar ?? d.iv_adjusted_scalar,
                        current_atm_iv: d.currentAtmIv ?? d.current_atm_iv,
                        signed_accumulation: d.signedAccumulation ?? d.signed_accumulation,
                        predicted_next_move: d.predictedNextMove ?? d.predicted_next_move,
                        linear_m: d.linearM ?? d.linear_m,
                        linear_b: d.linearB ?? d.linear_b,
                        confidence: d.confidence,
                        signal: d.signal
                    })) as VectorSignal[];

                    setHistory(mappedData);
                    if (mappedData.length > 0) setLiveSignal(mappedData[0]);
                }
            } catch (err) {
                console.error("Failed to fetch vector history:", err);
            }
        };

        fetchHistory();

        // 2. Connect to SSE for live streaming
        const eventSource = new EventSource('/api/vectors');

        eventSource.onopen = () => setIsConnected(true);

        eventSource.onmessage = (event) => {
            const liveData: VectorSignal = JSON.parse(event.data);
            setLiveSignal(liveData);
            setHistory(prev => [liveData, ...prev].slice(0, 100)); // Keep last 100
        };

        eventSource.onerror = () => {
            setIsConnected(false);
            eventSource.close();
        };

        return () => {
            eventSource.close();
        };
    }, []);

    return (
        <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6 font-mono">
            {/* Header */}
            <header className="flex justify-between items-center border-b border-neutral-800 pb-4 mb-6">
                <div className="flex items-center gap-3">
                    <Activity className="text-blue-500" size={28} />
                    <h1 className="text-2xl font-bold tracking-tight text-white">VECTOR LAB</h1>
                </div>
                <div className="flex items-center gap-4 text-sm">
                    {isConnected ? (
                        <span className="flex items-center gap-2 text-blue-400 bg-blue-400/10 border border-blue-400/20 px-3 py-1.5 rounded">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                            </span>
                            Vectors Live
                        </span>
                    ) : (
                        <span className="text-red-400 bg-red-400/10 border border-red-400/20 px-3 py-1.5 rounded">Disconnected</span>
                    )}
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                {/* Main Live Signal Card */}
                <div className="lg:col-span-2 bg-neutral-900 border border-neutral-800 rounded-lg p-6 relative overflow-hidden shadow-2xl">
                    <div className="absolute top-0 right-0 p-32 opacity-5 pointer-events-none">
                        <Target size={200} />
                    </div>

                    <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-6 flex items-center gap-2">
                        <Brain size={16} /> Current Market Vector
                    </h2>

                    {liveSignal ? (
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
                            <div className="col-span-2 lg:col-span-1">
                                <div className="text-sm text-neutral-500 mb-1">Signal</div>
                                <div className={`text-4xl font-bold flex items-center gap-2 capitalize
                  ${liveSignal.signal === 'bullish' ? 'text-emerald-400' :
                                        liveSignal.signal === 'bearish' ? 'text-red-400' : 'text-yellow-400'}`}>
                                    {liveSignal.signal === 'bullish' && <TrendingUp size={32} />}
                                    {liveSignal.signal === 'bearish' && <TrendingDown size={32} />}
                                    {liveSignal.signal === 'neutral' && <Activity size={32} />}
                                    {liveSignal.signal}
                                </div>
                            </div>

                            <div>
                                <div className="text-sm text-neutral-500 mb-1">Predicted Move</div>
                                <div className="text-3xl font-bold text-white">
                                    {liveSignal.predicted_next_move > 0 ? '+' : ''}{liveSignal.predicted_next_move.toFixed(2)} pts
                                </div>
                            </div>

                            <div>
                                <div className="text-sm text-neutral-500 mb-1">Confidence</div>
                                <div className="text-3xl font-bold text-white">
                                    {liveSignal.confidence.toFixed(1)}%
                                </div>
                            </div>

                            <div>
                                <div className="text-sm text-neutral-500 mb-1">Current ATM IV</div>
                                <div className="text-3xl font-bold text-neutral-300">
                                    {liveSignal.current_atm_iv.toFixed(2)}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="h-24 flex items-center justify-center text-neutral-600">Awaiting vector data...</div>
                    )}
                </div>

                {/* Regression Internals */}
                <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
                    <h2 className="text-sm text-neutral-400 uppercase tracking-wider mb-6 border-b border-neutral-800 pb-2">
                        Math Engine Internals
                    </h2>

                    {liveSignal ? (
                        <div className="space-y-4 text-sm">
                            <div className="flex justify-between items-center py-2 border-b border-neutral-800/50">
                                <span className="text-neutral-500">Raw Scalar</span>
                                <span className="font-medium text-neutral-300">{liveSignal.raw_scalar?.toFixed(4)}</span>
                            </div>
                            <div className="flex justify-between items-center py-2 border-b border-neutral-800/50">
                                <span className="text-neutral-500">IV Adjusted X</span>
                                <span className="font-medium text-neutral-300">{liveSignal.iv_adjusted_scalar?.toFixed(6)}</span>
                            </div>
                            <div className="flex justify-between items-center py-2 border-b border-neutral-800/50">
                                <span className="text-neutral-500">Accumulated Score</span>
                                <span className={`font-medium ${liveSignal.signed_accumulation > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    {liveSignal.signed_accumulation?.toFixed(2)}
                                </span>
                            </div>
                            <div className="flex items-center gap-2 pt-2">
                                <span className="font-mono text-xs bg-neutral-950 px-2 py-1 rounded text-neutral-400 border border-neutral-800 w-full text-center">
                                    y = {liveSignal.linear_m?.toFixed(4)}x + {liveSignal.linear_b?.toFixed(4)}
                                </span>
                            </div>
                        </div>
                    ) : (
                        <div className="h-32 flex items-center justify-center text-neutral-600">No data</div>
                    )}
                </div>
            </div>

            {/* History Table */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-lg overflow-hidden">
                <div className="p-4 border-b border-neutral-800 bg-neutral-900/50 flex justify-between items-center">
                    <h2 className="text-sm text-neutral-400 uppercase tracking-wider flex items-center gap-2">
                        <Database size={16} /> Output History
                    </h2>
                    <span className="text-xs text-neutral-500">{history.length} records loaded</span>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-neutral-500 uppercase bg-neutral-950">
                            <tr>
                                <th className="px-6 py-3 font-medium">Time</th>
                                <th className="px-6 py-3 font-medium">Symbol</th>
                                <th className="px-6 py-3 font-medium">Signal</th>
                                <th className="px-6 py-3 font-medium text-right">Pred Move</th>
                                <th className="px-6 py-3 font-medium text-right">Conf %</th>
                                <th className="px-6 py-3 font-medium text-right">IV Adj</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-800">
                            {history.map((row, i) => {
                                // Formatting time safely
                                let timeStr = row.timestamp;
                                try {
                                    const d = new Date(row.timestamp);
                                    timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                                } catch (e) { }

                                return (
                                    <tr key={i} className="hover:bg-neutral-800/30 transition-colors">
                                        <td className="px-6 py-3 text-neutral-400 flex items-center gap-2">
                                            <Clock size={12} /> {timeStr}
                                        </td>
                                        <td className="px-6 py-3 font-medium text-white">{row.symbol}</td>
                                        <td className="px-6 py-3 capitalize">
                                            <span className={`px-2 py-0.5 rounded text-xs border ${row.signal === 'bullish' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                                    row.signal === 'bearish' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                                        'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                                                }`}>
                                                {row.signal}
                                            </span>
                                        </td>
                                        <td className={`px-6 py-3 text-right font-medium ${row.predicted_next_move > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                            {row.predicted_next_move?.toFixed(2)}
                                        </td>
                                        <td className="px-6 py-3 text-right text-neutral-300">{row.confidence?.toFixed(1)}%</td>
                                        <td className="px-6 py-3 text-right text-neutral-500 font-mono tracking-tighter">{row.iv_adjusted_scalar?.toFixed(4)}</td>
                                    </tr>
                                )
                            })}
                            {history.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-neutral-500">
                                        No historical vector calculations found in database.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
