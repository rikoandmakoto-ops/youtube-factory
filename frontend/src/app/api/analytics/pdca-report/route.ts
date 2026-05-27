import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getPdcaReport } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const channelId = req.nextUrl.searchParams.get('channel_id');
    const days = Number(req.nextUrl.searchParams.get('days') || 30);
    if (!channelId) {
      return NextResponse.json(
        { error: 'channel_id required' },
        { status: 400 }
      );
    }
    return NextResponse.json(await getPdcaReport(channelId, days));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
