import { NextResponse } from 'next/server';
import { ApiError, getScenarioArchive } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  { params }: { params: { channel_id: string; file_name: string } }
) {
  try {
    return NextResponse.json(
      await getScenarioArchive(params.channel_id, params.file_name)
    );
  } catch (e) {
    if (e instanceof ApiError)
      return NextResponse.json({ error: e.message }, { status: e.status });
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
