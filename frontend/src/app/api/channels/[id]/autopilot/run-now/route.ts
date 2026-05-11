import { NextResponse } from 'next/server';
import { ApiError, runAutopilotNow } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    return NextResponse.json(await runAutopilotNow(ctx.params.id));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
