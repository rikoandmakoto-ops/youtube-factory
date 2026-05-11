import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getAnalyticsVideos } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const limit = Number(req.nextUrl.searchParams.get('limit') || 100);
    return NextResponse.json(await getAnalyticsVideos(ctx.params.id, limit));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
