import { NextRequest, NextResponse } from 'next/server';
import { ApiError, listSchedules, createSchedule, ScheduleInput } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json(await listSchedules());
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as ScheduleInput;
    return NextResponse.json(await createSchedule(body));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
