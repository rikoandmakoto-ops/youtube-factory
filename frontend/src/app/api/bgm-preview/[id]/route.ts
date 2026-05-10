import { NextResponse } from 'next/server';
import { getSessionToken } from '@/lib/auth';

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
  const upstream = `${BACKEND_URL}/api/bgm-preview/${encodeURIComponent(
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
  const ct = res.headers.get('content-type') || 'audio/mpeg';
  headers.set('content-type', ct);
  headers.set('cache-control', 'private, max-age=60');
  return new NextResponse(res.body, { status: 200, headers });
}
