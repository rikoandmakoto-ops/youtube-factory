// Google Cloud の OAuth クライアントには canonical な Vercel オリジンの
// redirect URI のみ登録されている。別の Vercel エイリアス
// (youtube-factory-zaki21016s-projects.vercel.app 等) やプレビュー URL から
// 連携を開始すると redirect_uri = window.location.origin + path が未登録となり
// Google 側で redirect_uri_mismatch になる。そのため canonical でない Vercel
// ホストから連携が始まった場合は canonical オリジンへ誘導してやり直してもらう。
export const CANONICAL_OAUTH_ORIGIN =
  'https://youtube-factory-eight.vercel.app';

/**
 * 現在のオリジンが OAuth に使える canonical オリジンかを確認する。
 *
 * canonical でない `*.vercel.app` ホストから呼ばれた場合は、同じパスの
 * canonical オリジンへブラウザを遷移させ true（= 呼び出し側は処理を中断すべき）
 * を返す。canonical オリジン自身・localhost・将来のカスタムドメインなど
 * vercel.app 以外のホストは対象外で false を返す。
 */
export function redirectToCanonicalOAuthOrigin(): boolean {
  if (typeof window === 'undefined') return false;
  const { origin, hostname, pathname, search } = window.location;
  if (origin === CANONICAL_OAUTH_ORIGIN) return false;
  if (!hostname.endsWith('.vercel.app')) return false;
  window.location.href = `${CANONICAL_OAUTH_ORIGIN}${pathname}${search}`;
  return true;
}
