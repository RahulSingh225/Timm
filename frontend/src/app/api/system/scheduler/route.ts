import { NextRequest, NextResponse } from 'next/server';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:4500';

export const dynamic = 'force-dynamic';

export async function GET() {
    try {
        const res = await fetch(`${PYTHON_API_URL}/scheduler`, {
            cache: 'no-store',
            signal: AbortSignal.timeout(5000),
        });
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json(
            { success: false, error: 'Scheduler unreachable', jobs: [] },
            { status: 502 }
        );
    }
}

export async function POST(req: NextRequest) {
    try {
        const { job_id } = await req.json();

        if (!job_id) {
            return NextResponse.json({ error: 'job_id is required' }, { status: 400 });
        }

        const res = await fetch(`${PYTHON_API_URL}/scheduler/trigger/${job_id}`, {
            method: 'POST',
            signal: AbortSignal.timeout(5000),
        });
        const data = await res.json();
        return NextResponse.json(data);
    } catch (error: any) {
        return NextResponse.json(
            { error: `Failed to trigger job: ${error.message}` },
            { status: 502 }
        );
    }
}
