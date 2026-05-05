import { NextRequest, NextResponse } from 'next/server';
import { ApiError, testNotification } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      channel?: 'line' | 'slack' | 'email';
      message?: string;
    };
    return NextResponse.json(await testNotification(body.channel, body.message));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
