import { NextResponse } from 'next/server';
import { db } from '@/db';
import { dailyReports } from '@/db/schema';
import { desc } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

export async function GET() {
    try {
        const reports = await db.select()
            .from(dailyReports)
            .orderBy(desc(dailyReports.createdAt))
            .limit(1);

        if (reports.length === 0) {
            return NextResponse.json({ success: true, data: null });
        }

        // The schema now includes intradaySetups, optionsSetups, and evidenceChain
        return NextResponse.json({ success: true, data: reports[0] });
    } catch (error: any) {
        return NextResponse.json(
            { success: false, error: error.message },
            { status: 500 }
        );
    }
}
