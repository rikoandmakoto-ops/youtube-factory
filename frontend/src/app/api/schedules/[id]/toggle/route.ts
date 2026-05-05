import { NextRequest, NextResponse } from 'next/server';
import { ApiError, toggleSchedule } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const { enabled } = (await req.json()) as { enabled: boolean };
    return NextResponse.json(await toggleSchedule(params.id, !!enabled));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
