import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getAnalyticsOverview } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const days = Number(req.nextUrl.searchParams.get('days') || 30);
    return NextResponse.json(await getAnalyticsOverview(ctx.params.id, days));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
