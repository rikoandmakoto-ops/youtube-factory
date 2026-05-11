import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getEvaluation } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  ctx: { params: { channelId: string; videoId: string } }
) {
  try {
    return NextResponse.json(
      await getEvaluation(ctx.params.channelId, ctx.params.videoId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
