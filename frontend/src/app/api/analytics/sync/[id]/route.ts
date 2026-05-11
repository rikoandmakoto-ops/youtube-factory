import { NextRequest, NextResponse } from 'next/server';
import { ApiError, syncChannelAnalytics } from '@/lib/api';
import type { AnalyticsSyncOptions } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    let body: AnalyticsSyncOptions = {};
    try {
      const raw = await req.text();
      if (raw.trim()) body = JSON.parse(raw);
    } catch {
      body = {};
    }
    return NextResponse.json(await syncChannelAnalytics(ctx.params.id, body));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
