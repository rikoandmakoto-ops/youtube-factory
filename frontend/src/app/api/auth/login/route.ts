import { NextRequest, NextResponse } from 'next/server';
import { SESSION_COOKIE, SESSION_MAX_AGE } from '@/lib/auth';
import { login, ApiError } from '@/lib/api';

export async function POST(req: NextRequest) {
  let password: string;
  try {
    const body = await req.json();
    password = String(body?.password ?? '');
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  if (!password) {
    return NextResponse.json({ error: 'password_required' }, { status: 400 });
  }

  try {
    const { token, expires_in } = await login(password);
    const res = NextResponse.json({ ok: true });
    res.cookies.set(SESSION_COOKIE, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: expires_in || SESSION_MAX_AGE,
    });
    return res;
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json(
        { error: e.message },
        { status: e.status === 401 ? 401 : e.status === 429 ? 429 : 500 }
      );
    }
    return NextResponse.json({ error: 'login_failed' }, { status: 500 });
  }
}
