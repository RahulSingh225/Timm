import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { watchlist } from '@/db/schema';
import { eq, desc } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

// GET — Fetch all watchlist symbols
export async function GET() {
    try {
        const items = await db.select().from(watchlist).orderBy(desc(watchlist.addedAt));
        return NextResponse.json({ success: true, data: items });
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}

// POST — Add a symbol to watchlist
export async function POST(req: NextRequest) {
    try {
        const { symbol, asset_type } = await req.json();

        if (!symbol) {
            return NextResponse.json({ error: 'symbol is required' }, { status: 400 });
        }

        const result = await db.insert(watchlist).values({
            symbol: symbol.toUpperCase().trim(),
            assetType: asset_type || 'EQUITY',
            isActive: true,
        }).onConflictDoNothing().returning();

        if (result.length === 0) {
            return NextResponse.json({ success: true, message: 'Symbol already in watchlist' });
        }

        return NextResponse.json({ success: true, data: result[0] });
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}

// PUT — Toggle active/inactive
export async function PUT(req: NextRequest) {
    try {
        const { id, is_active } = await req.json();

        if (!id) {
            return NextResponse.json({ error: 'id is required' }, { status: 400 });
        }

        const result = await db.update(watchlist)
            .set({ isActive: is_active })
            .where(eq(watchlist.id, id))
            .returning();

        return NextResponse.json({ success: true, data: result[0] });
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}

// DELETE — Remove from watchlist
export async function DELETE(req: NextRequest) {
    try {
        const { id } = await req.json();

        if (!id) {
            return NextResponse.json({ error: 'id is required' }, { status: 400 });
        }

        await db.delete(watchlist).where(eq(watchlist.id, id));
        return NextResponse.json({ success: true });
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
