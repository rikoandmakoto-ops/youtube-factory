import { NextRequest, NextResponse } from 'next/server';
import { uploadAsset, ApiError, AssetKind, ASSET_KINDS } from '@/lib/api';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string } }
) {
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json({ error: 'invalid_form' }, { status: 400 });
  }

  const kind = String(form.get('kind') ?? '');
  const file = form.get('file');

  if (!ASSET_KINDS.includes(kind as AssetKind)) {
    return NextResponse.json({ error: `invalid_kind: ${kind}` }, { status: 400 });
  }
  if (!(file instanceof File)) {
    return NextResponse.json({ error: 'file required' }, { status: 400 });
  }

  try {
    const result = await uploadAsset(
      ctx.params.id,
      kind as AssetKind,
      file,
      file.name
    );
    return NextResponse.json(result, { status: 201 });
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
