import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listAbReconciliation } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const limit = Number(req.nextUrl.searchParams.get('limit') || 200);
    return NextResponse.json(
      await listAbReconciliation(ctx.params.channelId, limit)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
