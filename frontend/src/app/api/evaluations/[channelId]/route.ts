import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listEvaluations } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const limit = Number(req.nextUrl.searchParams.get('limit') || 100);
    return NextResponse.json(await listEvaluations(ctx.params.channelId, limit));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
