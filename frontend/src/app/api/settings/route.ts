import { NextRequest, NextResponse } from 'next/server';
import { getSettings, updateSettings, ApiError } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return NextResponse.json(await getSettings());
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    return NextResponse.json(await updateSettings(body));
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
