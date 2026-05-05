import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listHistory } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    return NextResponse.json(
      await listHistory({
        channel_id: sp.get('channel_id') || undefined,
        status: sp.get('status') || undefined,
        since: sp.get('since') || undefined,
        until: sp.get('until') || undefined,
        limit: sp.get('limit') ? Number(sp.get('limit')) : undefined,
      })
    );
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
