import { NextResponse } from 'next/server';
import { channelYoutubeDisconnect, ApiError } from '@/lib/api';

export async function DELETE(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    return NextResponse.json(await channelYoutubeDisconnect(ctx.params.id));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
