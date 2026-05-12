import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listCommentDemands } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const sp = req.nextUrl.searchParams;
    const status = sp.get('status') || undefined;
    const demand_type = sp.get('demand_type') || undefined;
    const limit = sp.get('limit') ? Number(sp.get('limit')) : undefined;
    return NextResponse.json(
      await listCommentDemands(ctx.params.channelId, { status, demand_type, limit })
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
