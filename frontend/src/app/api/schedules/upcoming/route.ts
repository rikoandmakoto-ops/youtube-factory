import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listUpcomingSchedules } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const limit = Number(req.nextUrl.searchParams.get('limit') || '10');
    return NextResponse.json(await listUpcomingSchedules(limit));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
