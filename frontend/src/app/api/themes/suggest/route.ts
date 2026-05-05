import { NextRequest, NextResponse } from 'next/server';
import { suggestTheme, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  let channelId = '';
  try {
    const body = await req.json();
    channelId = String(body?.channel_id ?? '');
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }
  if (!channelId) {
    return NextResponse.json({ error: 'channel_id required' }, { status: 400 });
  }
  try {
    const themes = await suggestTheme(channelId);
    return NextResponse.json({ themes });
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
