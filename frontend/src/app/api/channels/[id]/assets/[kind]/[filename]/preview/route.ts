import { NextResponse } from 'next/server';
import { getSessionToken } from '@/lib/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  ctx: { params: { id: string; kind: string; filename: string } }
) {
  const token = getSessionToken();
  if (!token) {
    return new NextResponse('Unauthorized', { status: 401 });
  }
  const upstream = `${BACKEND_URL}/api/channels/${encodeURIComponent(
    ctx.params.id
  )}/assets/${encodeURIComponent(ctx.params.kind)}/${encodeURIComponent(
    ctx.params.filename
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
  const cd = res.headers.get('content-disposition');
  if (cd) headers.set('content-disposition', cd);
  headers.set('cache-control', 'private, max-age=60');
  return new NextResponse(res.body, { status: 200, headers });
}
