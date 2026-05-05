import { NextRequest, NextResponse } from 'next/server';
import { youtubeCallback, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const r = await youtubeCallback(
      String(body?.state ?? ''),
      String(body?.code ?? '')
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
