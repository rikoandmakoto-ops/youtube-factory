import { NextRequest, NextResponse } from 'next/server';
import {
  getChannelPersona,
  updateChannelPersona,
  ApiError,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    const data = await getChannelPersona(ctx.params.id);
    return NextResponse.json(data);
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
    const body = await req.json();
    const result = await updateChannelPersona(ctx.params.id, body);
    return NextResponse.json(result);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
