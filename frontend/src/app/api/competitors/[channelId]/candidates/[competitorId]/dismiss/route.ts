import { NextRequest, NextResponse } from 'next/server';
import { ApiError, dismissCompetitorCandidate } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: NextRequest,
  ctx: { params: { channelId: string; competitorId: string } }
) {
  try {
    return NextResponse.json(
      await dismissCompetitorCandidate(
        ctx.params.channelId,
        ctx.params.competitorId
      )
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
