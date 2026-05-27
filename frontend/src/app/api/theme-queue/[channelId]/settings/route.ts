import { NextRequest, NextResponse } from 'next/server';
import { ApiError, updateThemeQueueSettings } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function PUT(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    const body = (await req.json()) as {
      target_size?: number;
      min_threshold?: number;
    };
    return NextResponse.json(
      await updateThemeQueueSettings(ctx.params.channelId, body)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
