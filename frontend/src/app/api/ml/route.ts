import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:4500';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const endpoint = searchParams.get('endpoint') || 'regime';

  try {
    const endpointMap: Record<string, string> = {
      'regime': '/api/ml/regime',
      'backtest': '/api/ml/backtest',
      'training': '/api/ml/training',
      'strategies': '/api/ml/strategies',
      'models': '/api/ml/models',
    };

    const url = endpointMap[endpoint] || endpointMap['regime'];
    const res = await fetch(`${BACKEND_URL}${url}`, { cache: 'no-store' });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Backend unreachable', details: String(error) }, { status: 502 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const res = await fetch(`${BACKEND_URL}/api/ml/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Failed', details: String(error) }, { status: 500 });
  }
}
