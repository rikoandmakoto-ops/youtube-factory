import { cookies } from 'next/headers';
import { SESSION_COOKIE, SESSION_MAX_AGE } from './session-cookie';

export { SESSION_COOKIE, SESSION_MAX_AGE };

export type SessionToken = string;

export function getSessionToken(): SessionToken | null {
  const c = cookies().get(SESSION_COOKIE);
  return c?.value ?? null;
}

export function isAuthenticated(): boolean {
  return getSessionToken() !== null;
}
