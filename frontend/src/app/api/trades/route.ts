import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { activeTrades } from '@/db/schema';
import { desc, eq } from 'drizzle-orm';

export async function GET(request: NextRequest) {
    try {
        const url = new URL(request.url);
        const status = url.searchParams.get('status');

        const results = status 
            ? await db.select().from(activeTrades).where(eq(activeTrades.status, status)).orderBy(desc(activeTrades.createdAt))
            : await db.select().from(activeTrades).orderBy(desc(activeTrades.createdAt));

        return NextResponse.json({ success: true, data: results });
    } catch (error) {
        console.error("Error fetching trades:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { symbol, tradeType, entryPrice, stoploss, target, notes } = body;

        if (!symbol || !tradeType || entryPrice === undefined || stoploss === undefined || target === undefined) {
            return NextResponse.json({ success: false, error: "Missing required fields" }, { status: 400 });
        }

        const newTrade = await db.insert(activeTrades).values({
            symbol,
            tradeType,
            entryPrice,
            stoploss,
            target,
            currentPrice: entryPrice, // Default to entry on creation
            notes,
            status: 'OPEN'
        }).returning();

        return NextResponse.json({ success: true, data: newTrade[0] });
    } catch (error) {
        console.error("Error creating trade:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
