import { NextRequest, NextResponse } from 'next/server';
import { changePassword, ApiError } from '@/lib/api';

export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    const r = await changePassword(
      String(body?.current_password ?? ''),
      String(body?.new_password ?? '')
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
