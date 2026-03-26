import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { globalCues } from '@/db/schema';
import { desc } from 'drizzle-orm';

export async function GET() {
    try {
        const results = await db.select()
            .from(globalCues)
            .orderBy(desc(globalCues.capturedAt))
            .limit(1);

        if (results.length === 0) {
             return NextResponse.json({ success: true, data: null });
        }

        return NextResponse.json({ success: true, data: results[0] });
    } catch (error) {
        console.error("Error fetching global cues:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
