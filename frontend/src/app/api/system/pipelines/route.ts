import { NextResponse } from 'next/server';
import { db } from '@/db';
import { marketAlerts, fiiDiiFlows, newsEvents, optionsFootprint, participantData, sectorFlows, tradewiseFlows, vectorSignals, activeTrades, screenedStocks, globalCues, intradayCandles } from '@/db/schema';
import { sql } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

interface PipelineStat {
    name: string;
    table: string;
    records: number;
    lastSync: string | null;
    status: 'healthy' | 'stale' | 'empty';
}

export async function GET() {
    try {
        const tableQueries = [
            { name: 'Market Alerts', table: 'market_alerts', ref: marketAlerts },
            { name: 'FII/DII Flows', table: 'fii_dii_flows', ref: fiiDiiFlows },
            { name: 'News Events', table: 'news_events', ref: newsEvents },
            { name: 'Options Footprint', table: 'options_footprint', ref: optionsFootprint },
            { name: 'Participant Data', table: 'participant_data', ref: participantData },
            { name: 'Sector Flows', table: 'sector_flows', ref: sectorFlows },
            { name: 'Tradewise Flows', table: 'tradewise_flows', ref: tradewiseFlows },
            { name: 'Vector Signals', table: 'vector_signals', ref: vectorSignals },
            { name: 'Active Trades', table: 'active_trades', ref: activeTrades },
            { name: 'Screened Stocks', table: 'screened_stocks', ref: screenedStocks },
            { name: 'Global Cues', table: 'global_cues', ref: globalCues },
            { name: 'Intraday Candles', table: 'intraday_candles', ref: intradayCandles },
        ];

        const pipelines: PipelineStat[] = [];

        for (const tq of tableQueries) {
            try {
                // Get count and latest timestamp in one query
                const result = await db.execute(
                    sql.raw(`SELECT COUNT(*) as count, MAX(created_at) as last_sync FROM ${tq.table}`)
                );

                const row = (result as any).rows?.[0] || (result as any)[0];
                const count = parseInt(row?.count || '0', 10);
                const lastSync = row?.last_sync ? new Date(row.last_sync).toISOString() : null;

                // Determine health status
                let status: 'healthy' | 'stale' | 'empty' = 'empty';
                if (count > 0 && lastSync) {
                    const hoursSinceSync = (Date.now() - new Date(lastSync).getTime()) / (1000 * 60 * 60);
                    status = hoursSinceSync < 24 ? 'healthy' : 'stale';
                }

                pipelines.push({
                    name: tq.name,
                    table: tq.table,
                    records: count,
                    lastSync,
                    status,
                });
            } catch (err: any) {
                // Table might not exist yet
                pipelines.push({
                    name: tq.name,
                    table: tq.table,
                    records: 0,
                    lastSync: null,
                    status: 'empty',
                });
            }
        }

        return NextResponse.json({ success: true, data: pipelines });
    } catch (error: any) {
        console.error('Pipeline stats error:', error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
