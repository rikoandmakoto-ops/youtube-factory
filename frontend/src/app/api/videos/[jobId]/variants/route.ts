import { NextRequest, NextResponse } from 'next/server';
import { ApiError, getVariants } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(_req: NextRequest, { params }: { params: { jobId: string } }) {
  try {
    return NextResponse.json(await getVariants(params.jobId));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
