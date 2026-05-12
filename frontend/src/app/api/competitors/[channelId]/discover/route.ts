import { NextRequest, NextResponse } from 'next/server';
import { ApiError, runCompetitorDiscovery } from '@/lib/api';

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
      await runCompetitorDiscovery(ctx.params.channelId, body as {
        max_candidates?: number;
        min_subscribers?: number;
        relevance_threshold?: number;
      })
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
