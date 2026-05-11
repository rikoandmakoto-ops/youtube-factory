import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listABTests } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    const channelId = sp.get('channel_id') || undefined;
    const limit = sp.get('limit') ? Number(sp.get('limit')) : 50;
    return NextResponse.json(await listABTests(channelId, limit));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
