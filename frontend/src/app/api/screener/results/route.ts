import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { screenedStocks } from '@/db/schema';
import { desc, eq, and } from 'drizzle-orm';

export async function GET(request: NextRequest) {
    try {
        const url = new URL(request.url);
        const type = url.searchParams.get('type') || 'INTRADAY';
        const limitStr = url.searchParams.get('limit');
        const limit = limitStr ? parseInt(limitStr, 10) : 50;

        const results = await db.select()
            .from(screenedStocks)
            .where(eq(screenedStocks.tradeType, type))
            .orderBy(desc(screenedStocks.screenedAt))
            .limit(limit);

        return NextResponse.json({ success: true, data: results });
    } catch (error) {
        console.error("Error fetching screened stocks:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
