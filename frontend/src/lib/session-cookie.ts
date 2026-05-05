/**
 * セッション Cookie 名・有効期限の定数だけを切り出したモジュール。
 *
 * `next/headers` を import する `auth.ts` を middleware から参照すると
 * Edge Runtime と衝突するため、定数はこちら側に置く。
 */

export const SESSION_COOKIE = 'ytf_session';
export const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 days
