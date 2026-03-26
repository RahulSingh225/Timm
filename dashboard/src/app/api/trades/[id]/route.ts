import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db';
import { activeTrades } from '@/db/schema';
import { eq } from 'drizzle-orm';

// Update a trade (e.g., hit SL manually, target manually, or just update notes)
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
    try {
        const resolvedParams = await params;
        const id = parseInt(resolvedParams.id, 10);
        if (isNaN(id)) {
            return NextResponse.json({ success: false, error: "Invalid ID" }, { status: 400 });
        }

        const body = await request.json();
        
        // Only allow updating specific fields from the client
        const updateData: any = {};
        if (body.status !== undefined) updateData.status = body.status;
        if (body.notes !== undefined) updateData.notes = body.notes;
        if (body.stoploss !== undefined) updateData.stoploss = body.stoploss;
        if (body.target !== undefined) updateData.target = body.target;
        
        // If they manually close it
        if (body.status && body.status !== 'OPEN') {
            updateData.exitTime = new Date();
        }

        if (Object.keys(updateData).length === 0) {
             return NextResponse.json({ success: false, error: "No update provided" }, { status: 400 });
        }

        const updatedTrade = await db.update(activeTrades)
            .set(updateData)
            .where(eq(activeTrades.id, id))
            .returning();

        if (updatedTrade.length === 0) {
             return NextResponse.json({ success: false, error: "Trade not found" }, { status: 404 });
        }

        return NextResponse.json({ success: true, data: updatedTrade[0] });
    } catch (error) {
        console.error("Error updating trade:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}

// Delete a trade from tracking
export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
    try {
        const resolvedParams = await params;
        const id = parseInt(resolvedParams.id, 10);
        if (isNaN(id)) {
             return NextResponse.json({ success: false, error: "Invalid ID" }, { status: 400 });
        }

        const deletedTrade = await db.delete(activeTrades)
            .where(eq(activeTrades.id, id))
            .returning();

        if (deletedTrade.length === 0) {
             return NextResponse.json({ success: false, error: "Trade not found" }, { status: 404 });
        }

        return NextResponse.json({ success: true, data: deletedTrade[0] });
    } catch (error) {
        console.error("Error deleting trade:", error);
        return NextResponse.json({ success: false, error: "Internal Server Error" }, { status: 500 });
    }
}
