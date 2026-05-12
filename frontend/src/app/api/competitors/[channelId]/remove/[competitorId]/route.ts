import { NextRequest, NextResponse } from 'next/server';
import { ApiError, removeCompetitor } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function DELETE(
  _req: NextRequest,
  ctx: { params: { channelId: string; competitorId: string } }
) {
  try {
    return NextResponse.json(
      await removeCompetitor(ctx.params.channelId, ctx.params.competitorId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
