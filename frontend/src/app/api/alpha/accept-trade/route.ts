import { NextResponse, NextRequest } from 'next/server';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:4500';

export async function POST(req: NextRequest) {
    try {
        const payload = await req.json();
        const response = await fetch(`${PYTHON_API_URL}/graph/accept-trade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json(
            { success: false, error: error.message },
            { status: 502 }
        );
    }
}
