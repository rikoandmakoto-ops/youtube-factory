import { NextRequest, NextResponse } from 'next/server';
import { ApiError, runScheduleNow } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    return NextResponse.json(await runScheduleNow(params.id));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
