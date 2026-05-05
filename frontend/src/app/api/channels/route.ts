import { NextRequest, NextResponse } from 'next/server';
import { createChannel, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const result = await createChannel(body);
    return NextResponse.json(result, { status: 201 });
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
