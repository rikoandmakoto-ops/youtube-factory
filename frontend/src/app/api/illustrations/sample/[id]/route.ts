import { NextResponse } from 'next/server';
import { getSessionToken } from '@/lib/auth';
import { ApiError, deleteSampleIllustration } from '@/lib/api';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  ctx: { params: { id: string } }
) {
  const token = getSessionToken();
  if (!token) {
    return new NextResponse('Unauthorized', { status: 401 });
  }
  const upstream = `${BACKEND_URL}/api/illustrations/sample/${encodeURIComponent(
    ctx.params.id
  )}`;
  const res = await fetch(upstream, {
    headers: { authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) {
    return new NextResponse(`Upstream ${res.status}`, { status: res.status });
  }
  const headers = new Headers();
  const ct = res.headers.get('content-type');
  if (ct) headers.set('content-type', ct);
  headers.set('cache-control', 'private, max-age=60');
  return new NextResponse(res.body, { status: 200, headers });
}

export async function DELETE(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    const r = await deleteSampleIllustration(ctx.params.id);
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
