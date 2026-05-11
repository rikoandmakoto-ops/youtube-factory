import { NextRequest, NextResponse } from 'next/server';
import { ApiError, refillAutopilotQueue } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = (await req.json().catch(() => ({}))) as { count?: number };
    const count = typeof body.count === 'number' ? body.count : 5;
    return NextResponse.json(await refillAutopilotQueue(ctx.params.id, count));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
