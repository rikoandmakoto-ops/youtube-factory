'use client';

import { useEffect, useState } from 'react';
import { Field } from '@/components/Field';
import {
  CANONICAL_OAUTH_ORIGIN,
  redirectToCanonicalOAuthOrigin,
} from '@/lib/oauthOrigin';
import type { YoutubeStatus } from '@/lib/api';

// Google に登録済みの承認済みリダイレクト URI。
// canonical オリジン上のこのパスのみが GCP に登録されている。
// （旧 '/settings' は未登録で redirect_uri_mismatch になるため使わない）
const REDIRECT_PATH = '/oauth/youtube/callback';
const POPUP_FEATURES = 'width=520,height=720';

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text);
    if (j && typeof j === 'object' && 'error' in j) return String(j.error);
    if (j && typeof j === 'object' && 'detail' in j) return String(j.detail);
  } catch {
    /* not JSON — likely an HTML error page from Vercel/edge */
  }
  return `${res.status} ${res.statusText || 'リクエストに失敗しました'}`;
}

export default function YoutubeConnect() {
  const [status, setStatus] = useState<YoutubeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [savingClient, setSavingClient] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const refresh = async () => {
    try {
      const res = await fetch('/api/youtube/status', { cache: 'no-store' });
      if (res.ok) setStatus(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const saveClient = async () => {
    setSavingClient(true);
    setError(null);
    try {
      const res = await fetch('/api/youtube/client', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
      });
      if (!res.ok) throw new Error(await readErrorMessage(res));
      setClientId('');
      setClientSecret('');
      setInfo('✅ OAuth クライアント情報を保存しました');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setSavingClient(false);
    }
  };

  const startAuth = async () => {
    setError(null);
    setInfo(null);

    // canonical でない Vercel エイリアス/プレビューから始まると redirect_uri が
    // Google 未登録で redirect_uri_mismatch になる。canonical へ誘導してやり直す。
    if (redirectToCanonicalOAuthOrigin()) {
      setInfo(`YouTube 連携は ${CANONICAL_OAUTH_ORIGIN} で行います。移動中…`);
      return;
    }

    setAuthBusy(true);

    // ポップアップブロッカー対策: 必ずユーザーアクション直後に開く
    const popup = window.open('about:blank', 'yt-oauth', POPUP_FEATURES);
    if (!popup) {
      setError('ポップアップがブロックされました');
      setAuthBusy(false);
      return;
    }

    try {
      const redirectUri = `${window.location.origin}${REDIRECT_PATH}`;
      const res = await fetch('/api/youtube/auth-url', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ redirect_uri: redirectUri }),
      });
      if (!res.ok) {
        popup.close();
        throw new Error(await readErrorMessage(res));
      }
      const data: { auth_url: string; state: string } = await res.json();

      popup.location.href = data.auth_url;

      // コールバックページ(/oauth/youtube/callback)から code/state を受け取る
      const onMessage = async (ev: MessageEvent) => {
        if (ev.origin !== window.location.origin) return;
        if (ev.data?.type !== 'yt-oauth-callback') return;
        window.removeEventListener('message', onMessage);
        try {
          const cbRes = await fetch('/api/youtube/callback', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ state: ev.data.state, code: ev.data.code }),
          });
          if (!cbRes.ok) throw new Error(await readErrorMessage(cbRes));
          const result = await cbRes.json();
          setInfo(`✅ 連携完了: ${result.account_email || ''}`);
          await refresh();
        } catch (e) {
          setError(e instanceof Error ? e.message : 'OAuth に失敗しました');
        } finally {
          setAuthBusy(false);
        }
      };
      window.addEventListener('message', onMessage);

      // ポップアップが閉じられた場合のクリーンアップ
      const closedTimer = window.setInterval(() => {
        if (popup.closed) {
          window.clearInterval(closedTimer);
          window.removeEventListener('message', onMessage);
          setAuthBusy(false);
        }
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
      setAuthBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm('YouTube 連携を解除しますか？')) return;
    setError(null);
    const res = await fetch('/api/youtube/disconnect', { method: 'POST' });
    if (!res.ok) {
      setError('解除に失敗しました');
      return;
    }
    setInfo('連携を解除しました');
    await refresh();
  };

  if (loading) return <p className="text-sm text-slate-500">…</p>;
  if (!status) return <p className="text-sm text-red-400">取得失敗</p>;

  const redirectExample =
    typeof window !== 'undefined'
      ? `${window.location.origin}${REDIRECT_PATH}`
      : `${CANONICAL_OAUTH_ORIGIN}${REDIRECT_PATH}`;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            status.connected ? 'bg-emerald-400' : 'bg-slate-500'
          }`}
        />
        <span className="text-slate-300">
          {status.connected
            ? `接続済${status.account_email ? `: ${status.account_email}` : ''}`
            : '未接続'}
        </span>
      </div>

      {!status.google_libs_installed && (
        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          ⚠️ Google API ライブラリが未インストールです:
          <code className="ml-1">
            pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 cryptography
          </code>
        </p>
      )}
      {!status.crypto_installed && (
        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          ⚠️ cryptography 未インストール — トークンが平文相当で保存されます
        </p>
      )}

      {!status.client_configured && (
        <details className="rounded-lg bg-bg-elev/60 border border-border p-3" open>
          <summary className="cursor-pointer text-sm font-semibold">
            🔧 OAuth クライアント情報を登録
          </summary>
          <div className="mt-3 space-y-3">
            <p className="text-xs text-slate-400 leading-5">
              Google Cloud Console で OAuth 2.0 クライアントID（種類: <b>ウェブ</b>）を作成し、
              承認済みリダイレクト URI に下記を追加してください:
            </p>
            <pre className="text-[10px] bg-bg whitespace-pre-wrap break-all p-2 rounded border border-border text-slate-300">
              {redirectExample}
            </pre>
            <Field label="Client ID">
              <input
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                className="input"
                placeholder="xxxxx.apps.googleusercontent.com"
                autoComplete="off"
              />
            </Field>
            <Field label="Client Secret">
              <input
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                className="input"
                autoComplete="off"
              />
            </Field>
            <button
              type="button"
              onClick={saveClient}
              disabled={savingClient || !clientId || !clientSecret}
              className="btn-secondary w-full"
            >
              {savingClient ? '保存中…' : 'クライアント情報を保存'}
            </button>
          </div>
        </details>
      )}

      {status.client_configured && (
        <p className="text-xs text-slate-500">
          OAuth クライアント: <code>{status.client_id_preview}</code>
        </p>
      )}

      <div className="flex gap-2">
        {!status.connected ? (
          <button
            type="button"
            onClick={startAuth}
            disabled={!status.client_configured || authBusy || !status.google_libs_installed}
            className="btn-primary flex-1"
          >
            {authBusy ? '認証中…' : '🔗 YouTube アカウントを連携'}
          </button>
        ) : (
          <button
            type="button"
            onClick={disconnect}
            className="btn-secondary flex-1"
          >
            連携を解除
          </button>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {error}
        </p>
      )}
      {info && (
        <p className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {info}
        </p>
      )}
    </div>
  );
}
