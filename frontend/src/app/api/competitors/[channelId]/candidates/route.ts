import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listCompetitorCandidates } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const sp = req.nextUrl.searchParams;
    const statusParam = sp.get('status') ?? 'pending';
    const status =
      statusParam === 'approved' || statusParam === 'dismissed' || statusParam === 'all'
        ? statusParam
        : 'pending';
    const limit = sp.get('limit') ? Number(sp.get('limit')) : 50;
    return NextResponse.json(
      await listCompetitorCandidates(ctx.params.channelId, status, limit)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
