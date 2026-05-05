import { NextRequest, NextResponse } from 'next/server';
import { setVideoStatus, ApiError, VideoStatus } from '@/lib/api';

export async function PUT(
  req: NextRequest,
  ctx: { params: { jobId: string } }
) {
  try {
    const body = await req.json();
    const r = await setVideoStatus(
      ctx.params.jobId,
      body.status as VideoStatus,
      {
        video_id: body.video_id,
        url: body.url,
        scheduled_at: body.scheduled_at,
      }
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
