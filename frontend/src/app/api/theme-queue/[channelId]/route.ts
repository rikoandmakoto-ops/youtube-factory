import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getThemeQueue } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    return NextResponse.json(await getThemeQueue(ctx.params.channelId));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
