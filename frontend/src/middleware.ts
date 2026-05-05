import { NextRequest, NextResponse } from 'next/server';
import { SESSION_COOKIE } from './lib/session-cookie';

const PUBLIC_PATHS = ['/login', '/api/auth/login'];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'));
  const token = req.cookies.get(SESSION_COOKIE)?.value;

  if (!token && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('next', pathname);
    return NextResponse.redirect(url);
  }

  if (token && pathname === '/login') {
    const url = req.nextUrl.clone();
    url.pathname = '/';
    url.search = '';
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Apply to everything except Next internals + static files
    '/((?!_next/|favicon.ico|robots.txt|.*\\.(?:png|jpg|jpeg|gif|svg|ico|webp)$).*)',
  ],
};
