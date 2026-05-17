import { NextRequest, NextResponse } from 'next/server';
import {
  ApiError,
  listEffectsResearch,
  startEffectsResearch,
  type StartResearchRequest,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const limit = Number(req.nextUrl.searchParams.get('limit') ?? '20');
    return NextResponse.json(await listEffectsResearch(ctx.params.id, limit));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = (await req.json().catch(() => ({}))) as StartResearchRequest;
    return NextResponse.json(await startEffectsResearch(ctx.params.id, body));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
