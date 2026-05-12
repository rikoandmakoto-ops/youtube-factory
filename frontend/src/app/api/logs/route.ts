import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getServerLogs } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    const level = sp.get('level');
    return NextResponse.json(
      await getServerLogs({
        lines: sp.get('lines') ? Number(sp.get('lines')) : undefined,
        filter: sp.get('filter') || undefined,
        level:
          level === 'error' || level === 'warn' || level === 'info'
            ? level
            : undefined,
      })
    );
  } catch (e) {
    if (e instanceof ApiError)
      return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
