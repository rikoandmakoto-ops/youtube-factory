import { NextRequest, NextResponse } from 'next/server';
import { youtubePublish, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    return NextResponse.json(await youtubePublish(body));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
