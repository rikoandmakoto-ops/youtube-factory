import { NextRequest, NextResponse } from 'next/server';
import { ApiError, applyEffectsResearch, type EffectsConfig } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  ctx: { params: { id: string; recordId: string } }
) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      effects?: EffectsConfig | null;
    };
    return NextResponse.json(
      await applyEffectsResearch(
        ctx.params.id,
        Number(ctx.params.recordId),
        body.effects ?? undefined
      )
    );
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json({ error: e.message }, { status: e.status });
    }
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
