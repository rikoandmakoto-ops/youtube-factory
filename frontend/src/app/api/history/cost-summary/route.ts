import { NextResponse } from 'next/server';
import { ApiError, getCostSummary } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json(await getCostSummary());
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
