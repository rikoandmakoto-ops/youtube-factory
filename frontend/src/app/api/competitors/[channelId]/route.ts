import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getCompetitorOverview } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const sp = req.nextUrl.searchParams;
    const limit = sp.get('limit') ? Number(sp.get('limit')) : undefined;
    return NextResponse.json(
      await getCompetitorOverview(ctx.params.channelId, limit)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
