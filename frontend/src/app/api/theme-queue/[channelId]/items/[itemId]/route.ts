import { NextRequest, NextResponse } from 'next/server';
import { ApiError, removeThemeQueueItem } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function DELETE(
  _req: NextRequest,
  ctx: { params: { channelId: string; itemId: string } }
) {
  try {
    return NextResponse.json(
      await removeThemeQueueItem(ctx.params.channelId, ctx.params.itemId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
