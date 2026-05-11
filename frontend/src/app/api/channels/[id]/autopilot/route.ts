import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getAutopilot, updateAutopilot, type AutopilotUpdate } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    return NextResponse.json(await getAutopilot(ctx.params.id));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function PUT(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = (await req.json()) as AutopilotUpdate;
    return NextResponse.json(await updateAutopilot(ctx.params.id, body));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
