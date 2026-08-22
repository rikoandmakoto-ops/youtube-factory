/**
 * セッション Cookie 名・有効期限の定数だけを切り出したモジュール。
 *
 * `next/headers` を import する `auth.ts` を middleware から参照すると
 * Edge Runtime と衝突するため、定数はこちら側に置く。
 */

export const SESSION_COOKIE = 'ytf_session';

// Cookie の寿命はバックエンドが返す expires_in を優先する。これはその
// フォールバック値で、JWT 側の既定（SESSION_TTL_DAYS、既定 90 日）に合わせてある。
export const SESSION_MAX_AGE = 60 * 60 * 24 * 90; // 90 days
