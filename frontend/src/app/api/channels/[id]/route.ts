import { NextResponse } from 'next/server';
import { deleteChannel, ApiError } from '@/lib/api';

export async function DELETE(
  _req: Request,
  ctx: { params: { id: string } }
) {
  try {
    const result = await deleteChannel(ctx.params.id);
    return NextResponse.json(result);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
