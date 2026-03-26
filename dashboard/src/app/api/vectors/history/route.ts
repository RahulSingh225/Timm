import { NextResponse } from 'next/server';
import { db } from '@/db';
import { vectorSignals } from '@/db/schema';
import { desc } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

export async function GET() {
    try {
        const history = await db.select()
            .from(vectorSignals)
            .orderBy(desc(vectorSignals.timestamp))
            .limit(100);

        return NextResponse.json(history);
    } catch (error: any) {
        console.error('[Vector History API] Error:', error);
        return NextResponse.json({ error: 'Failed to fetch vector history' }, { status: 500 });
    }
}
