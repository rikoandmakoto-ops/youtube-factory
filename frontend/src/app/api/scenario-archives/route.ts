import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listScenarioArchives } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    const hc = sp.get('has_compete');
    return NextResponse.json(
      await listScenarioArchives({
        channel_id: sp.get('channel_id') || undefined,
        q: sp.get('q') || undefined,
        has_compete:
          hc === 'true' ? true : hc === 'false' ? false : undefined,
        limit: sp.get('limit') ? Number(sp.get('limit')) : undefined,
      })
    );
  } catch (e) {
    if (e instanceof ApiError)
      return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
