import { NextRequest, NextResponse } from 'next/server';
import { getChannelTiktokAuthUrl, ApiError } from '@/lib/api';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = await req.json();
    const r = await getChannelTiktokAuthUrl(
      ctx.params.id,
      String(body?.redirect_uri ?? '')
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
