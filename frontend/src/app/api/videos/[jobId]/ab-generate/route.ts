import { NextRequest, NextResponse } from 'next/server';
import { ApiError, generateVariants } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      title_count?: number;
      thumbnail_count?: number;
    };
    return NextResponse.json(await generateVariants(params.jobId, body));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
