import { NextRequest, NextResponse } from 'next/server';
import { ApiError, selectVariant } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
  try {
    const { variant_id } = (await req.json()) as { variant_id: string };
    return NextResponse.json(await selectVariant(params.jobId, variant_id));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
