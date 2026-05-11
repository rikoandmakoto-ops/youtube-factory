import { NextRequest, NextResponse } from 'next/server';
import { ApiError, updateAutopilotTheme, deleteAutopilotTheme } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function PATCH(
  req: NextRequest,
  ctx: { params: { id: string; themeId: string } }
) {
  try {
    const body = (await req.json()) as { title?: string; angle?: string };
    return NextResponse.json(
      await updateAutopilotTheme(ctx.params.id, ctx.params.themeId, body)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function DELETE(
  _req: NextRequest,
  ctx: { params: { id: string; themeId: string } }
) {
  try {
    return NextResponse.json(
      await deleteAutopilotTheme(ctx.params.id, ctx.params.themeId)
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
