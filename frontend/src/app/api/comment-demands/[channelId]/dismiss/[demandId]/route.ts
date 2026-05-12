import { NextRequest, NextResponse } from 'next/server';
import { ApiError, dismissCommentDemand } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: NextRequest,
  ctx: { params: { channelId: string; demandId: string } }
) {
  try {
    return NextResponse.json(
      await dismissCommentDemand(ctx.params.channelId, ctx.params.demandId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
