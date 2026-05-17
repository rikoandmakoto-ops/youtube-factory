import { NextResponse } from 'next/server';
import { ApiError, getResearchJob } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  ctx: { params: { id: string; jobId: string } }
) {
  try {
    return NextResponse.json(
      await getResearchJob(ctx.params.id, ctx.params.jobId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
