import { NextResponse } from 'next/server';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';

export async function GET() {
    try {
        const res = await fetch(`${PYTHON_API_URL}/workers`, { cache: 'no-store' });
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json({ error: 'Failed to reach Python backend' }, { status: 500 });
    }
}

export async function POST(req: Request) {
    try {
        const { worker_id, action } = await req.json();
        const endpoint = action === 'start' ? 'start' : 'stop';

        const res = await fetch(`${PYTHON_API_URL}/workers/${worker_id}/${endpoint}`, {
            method: 'POST'
        });
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json({ error: 'Failed to communicate with Python backend' }, { status: 500 });
    }
}
