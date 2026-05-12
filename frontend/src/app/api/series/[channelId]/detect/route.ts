import { NextRequest, NextResponse } from 'next/server';
import { ApiError, runSeriesDetection } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    let body: Record<string, unknown> = {};
    try {
      const raw = await req.text();
      if (raw.trim()) body = JSON.parse(raw);
    } catch {
      body = {};
    }
    return NextResponse.json(
      await runSeriesDetection(ctx.params.channelId, body as {
        threshold?: number;
        max_viral?: number;
      })
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
