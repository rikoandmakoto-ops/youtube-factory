import { NextRequest, NextResponse } from 'next/server';
import { ApiError, updateTemplate, deleteTemplate, TemplateInput } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
  try {
    const body = (await req.json()) as TemplateInput;
    return NextResponse.json(await updateTemplate(params.id, body));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}

export async function DELETE(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    return NextResponse.json(await deleteTemplate(params.id));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
