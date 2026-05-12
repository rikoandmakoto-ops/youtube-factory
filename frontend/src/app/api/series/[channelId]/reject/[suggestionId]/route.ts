import { NextRequest, NextResponse } from 'next/server';
import { ApiError, rejectSeriesSuggestion } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: NextRequest,
  ctx: { params: { channelId: string; suggestionId: string } }
) {
  try {
    return NextResponse.json(
      await rejectSeriesSuggestion(
        ctx.params.channelId,
        ctx.params.suggestionId
      )
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
