import { NextRequest, NextResponse } from 'next/server';
import { getYoutubeAuthUrl, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const r = await getYoutubeAuthUrl(String(body?.redirect_uri ?? ''));
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
