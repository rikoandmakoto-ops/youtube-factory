import { NextRequest, NextResponse } from 'next/server';
import { ApiError, runCompetitorScan } from '@/lib/api';

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
      await runCompetitorScan(ctx.params.channelId, body as {
        max_videos_per_competitor?: number;
        max_competitors?: number;
      })
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
