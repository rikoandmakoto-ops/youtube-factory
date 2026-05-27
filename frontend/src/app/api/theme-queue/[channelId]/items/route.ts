import { NextRequest, NextResponse } from 'next/server';
import { ApiError, addThemeQueueItem } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const body = (await req.json()) as {
      title: string;
      angle?: string;
      parent_title?: string | null;
    };
    return NextResponse.json(
      await addThemeQueueItem(ctx.params.channelId, body)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
