import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getTrends } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const count = Number(req.nextUrl.searchParams.get('count') || 5);
    return NextResponse.json(await getTrends(ctx.params.id, count));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
