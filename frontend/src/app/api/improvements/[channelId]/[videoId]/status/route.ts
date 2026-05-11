import { NextRequest, NextResponse } from 'next/server';
import { ApiError, setImprovementStatus } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function PUT(
  req: NextRequest,
  ctx: { params: { channelId: string; videoId: string } }
) {
  try {
    let body: { status?: string } = {};
    try {
      const raw = await req.text();
      if (raw.trim()) body = JSON.parse(raw);
    } catch {
      body = {};
    }
    const status = body.status;
    if (
      status !== 'pending' &&
      status !== 'applied' &&
      status !== 'dismissed'
    ) {
      return NextResponse.json(
        { error: 'status must be pending | applied | dismissed' },
        { status: 400 }
      );
    }
    return NextResponse.json(
      await setImprovementStatus(
        ctx.params.channelId,
        ctx.params.videoId,
        status
      )
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
