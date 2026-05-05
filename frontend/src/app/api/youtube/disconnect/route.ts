import { NextResponse } from 'next/server';
import { youtubeDisconnect, ApiError } from '@/lib/api';

export async function POST() {
  try {
    return NextResponse.json(await youtubeDisconnect());
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
