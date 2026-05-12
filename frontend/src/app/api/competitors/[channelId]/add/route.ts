import { NextRequest, NextResponse } from 'next/server';
import { ApiError, addCompetitor } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const body = (await req.json()) as { competitor_channel_id?: string };
    const competitorId = (body?.competitor_channel_id || '').trim();
    if (!competitorId) {
      return NextResponse.json(
        { error: 'competitor_channel_id required' },
        { status: 400 }
      );
    }
    return NextResponse.json(
      await addCompetitor(ctx.params.channelId, competitorId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
