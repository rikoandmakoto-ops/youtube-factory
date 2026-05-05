import { NextResponse } from 'next/server';
import { deleteAsset, ApiError, AssetKind, ASSET_KINDS } from '@/lib/api';

export async function DELETE(
  _req: Request,
  ctx: { params: { id: string; kind: string; filename: string } }
) {
  if (!ASSET_KINDS.includes(ctx.params.kind as AssetKind)) {
    return NextResponse.json({ error: 'invalid_kind' }, { status: 400 });
  }
  try {
    const r = await deleteAsset(
      ctx.params.id,
      ctx.params.kind as AssetKind,
      ctx.params.filename
    );
    return NextResponse.json(r);
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
