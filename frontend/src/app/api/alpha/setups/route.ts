import { NextResponse } from 'next/server';

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:4500';

export async function GET() {
    try {
        const response = await fetch(`${PYTHON_API_URL}/graph/setups`, {
            cache: 'no-store',
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
