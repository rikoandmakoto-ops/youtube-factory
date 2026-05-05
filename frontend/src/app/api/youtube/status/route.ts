import { NextResponse } from 'next/server';
import { getYoutubeStatus, ApiError } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json(await getYoutubeStatus());
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
