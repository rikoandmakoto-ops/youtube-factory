import { NextRequest, NextResponse } from 'next/server';
import { setYoutubeClient, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const r = await setYoutubeClient(
      String(body?.client_id ?? ''),
      String(body?.client_secret ?? '')
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
