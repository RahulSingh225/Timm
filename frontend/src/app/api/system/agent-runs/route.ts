import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { agentRuns } from '@/db/schema';
import { desc, eq, and, gte } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
    try {
        const url = new URL(request.url);
        const agent = url.searchParams.get('agent');
        const limitStr = url.searchParams.get('limit');
        const limit = limitStr ? parseInt(limitStr, 10) : 50;
        const hoursStr = url.searchParams.get('hours');
        const hours = hoursStr ? parseInt(hoursStr, 10) : 24;

        const cutoff = new Date(Date.now() - hours * 60 * 60 * 1000);

        let query = db.select()
            .from(agentRuns)
            .where(
                agent
                    ? and(eq(agentRuns.agentName, agent), gte(agentRuns.startedAt, cutoff))
                    : gte(agentRuns.startedAt, cutoff)
            )
            .orderBy(desc(agentRuns.startedAt))
            .limit(limit);

        const results = await query;

        // Summary stats
        const stats = {
            total: results.length,
            success: results.filter(r => r.runStatus === 'SUCCESS').length,
            failed: results.filter(r => r.runStatus === 'FAILED').length,
            running: results.filter(r => r.runStatus === 'RUNNING').length,
            avgDurationMs: results.length > 0
                ? Math.round(results.reduce((sum, r) => sum + (r.durationMs || 0), 0) / results.filter(r => r.durationMs).length)
                : 0,
            totalLlmTokens: results.reduce((sum, r) => sum + (r.llmPromptTokens || 0) + (r.llmCompletionTokens || 0), 0),
        };

        return NextResponse.json({ success: true, data: results, stats });
    } catch (error: any) {
        console.error('Agent runs error:', error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
