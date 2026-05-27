import { NextRequest, NextResponse } from 'next/server';
import { ApiError, replenishThemeQueue } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { channelId: string } }
) {
  try {
    let count: number | undefined;
    try {
      const body = (await req.json()) as { count?: number | null };
      count = body?.count ?? undefined;
    } catch {
      count = undefined;
    }
    return NextResponse.json(
      await replenishThemeQueue(ctx.params.channelId, count)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
