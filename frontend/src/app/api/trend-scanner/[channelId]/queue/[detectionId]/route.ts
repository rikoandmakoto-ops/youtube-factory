import { NextRequest, NextResponse } from 'next/server';
import { ApiError, queueTrendDetection } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: NextRequest,
  ctx: { params: { channelId: string; detectionId: string } }
) {
  try {
    return NextResponse.json(
      await queueTrendDetection(ctx.params.channelId, ctx.params.detectionId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
