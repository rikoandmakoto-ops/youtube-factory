import { NextRequest, NextResponse } from 'next/server';
import {
  ApiError,
  addAutopilotTheme,
  reorderAutopilotQueue,
  type AutopilotTheme,
} from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = (await req.json()) as { title: string; angle?: string };
    return NextResponse.json(
      await addAutopilotTheme(ctx.params.id, body),
      { status: 201 }
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function PUT(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  try {
    const body = (await req.json()) as { queue: AutopilotTheme[] };
    return NextResponse.json(
      await reorderAutopilotQueue(ctx.params.id, body.queue || [])
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
