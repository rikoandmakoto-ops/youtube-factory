import { NextRequest, NextResponse } from 'next/server';
import { setChannelTiktokClient, ApiError } from '@/lib/api';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = await req.json();
    const r = await setChannelTiktokClient(
      ctx.params.id,
      String(body?.client_key ?? ''),
      String(body?.client_secret ?? '')
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
