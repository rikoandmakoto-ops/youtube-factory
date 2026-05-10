import { NextRequest, NextResponse } from 'next/server';
import { SESSION_COOKIE } from '@/lib/auth';

/**
 * Clears the session cookie and redirects to /login.
 *
 * Used when the backend rejects the current token (401). The middleware
 * only checks cookie presence, so a stale cookie can otherwise leave the
 * user stuck — visiting /login redirects back to / because the cookie
 * still exists. This route breaks the loop by clearing the cookie before
 * the redirect.
 */
export async function GET(req: NextRequest) {
  const next = req.nextUrl.searchParams.get('next') || '/';
  const url = req.nextUrl.clone();
  url.pathname = '/login';
  url.search = next && next !== '/' ? `?next=${encodeURIComponent(next)}` : '';

  const res = NextResponse.redirect(url);
  res.cookies.set(SESSION_COOKIE, '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  });
  return res;
}
