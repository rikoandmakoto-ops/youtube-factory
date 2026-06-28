'use client';

import { useEffect, useState } from 'react';
import { Field } from '@/components/Field';
import {
  CANONICAL_OAUTH_ORIGIN,
  redirectToCanonicalOAuthOrigin,
} from '@/lib/oauthOrigin';
import type { TiktokStatus } from '@/lib/api';

const POPUP_FEATURES = 'width=520,height=720';

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text);
    if (j && typeof j === 'object' && 'error' in j) return String(j.error);
    if (j && typeof j === 'object' && 'detail' in j) return String(j.detail);
  } catch {
    /* not JSON */
  }
  return `${res.status} ${res.statusText || 'リクエストに失敗しました'}`;
}

/**
 * チャンネル別 TikTok OAuth 連携 UI
 *
 * 認証コールバックは新しいウィンドウから親へ postMessage で受け取り、
 * このコンポーネントが /api/channels/{id}/tiktok/callback を叩いて完了する。
 */
export default function ChannelTiktokConnect({
  channelId,
}: {
  channelId: string;
}) {
  const [status, setStatus] = useState<TiktokStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [clientKey, setClientKey] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [savingClient, setSavingClient] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [showClientForm, setShowClientForm] = useState(false);

  const refresh = async () => {
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/tiktok/status`,
        { cache: 'no-store' }
      );
      if (res.ok) setStatus(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId]);

  const saveClient = async () => {
    setSavingClient(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/tiktok/client`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            client_key: clientKey,
            client_secret: clientSecret,
          }),
        }
      );
      if (!res.ok) throw new Error(await readErrorMessage(res));
      setClientKey('');
      setClientSecret('');
      setInfo('✅ TikTok クライアント情報を保存しました');
      setShowClientForm(false);
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

    if (redirectToCanonicalOAuthOrigin()) {
      setInfo(`TikTok 連携は ${CANONICAL_OAUTH_ORIGIN} で行います。移動中…`);
      return;
    }

    setAuthBusy(true);

    const popup = window.open('about:blank', 'tt-oauth', POPUP_FEATURES);
    if (!popup) {
      setError('ポップアップがブロックされました');
      setAuthBusy(false);
      return;
    }

    try {
      const redirectUri = `${window.location.origin}/oauth/tiktok/callback`;
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/tiktok/auth`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ redirect_uri: redirectUri }),
        }
      );
      if (!res.ok) {
        popup.close();
        throw new Error(await readErrorMessage(res));
      }
      const data: { auth_url: string; state: string } = await res.json();

      popup.location.href = data.auth_url;

      const onMessage = async (ev: MessageEvent) => {
        if (ev.origin !== window.location.origin) return;
        if (ev.data?.type !== 'tt-oauth-callback') return;
        window.removeEventListener('message', onMessage);
        try {
          const cbRes = await fetch(
            `/api/channels/${encodeURIComponent(channelId)}/tiktok/callback`,
            {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({
                state: ev.data.state,
                code: ev.data.code,
              }),
            }
          );
          if (!cbRes.ok) throw new Error(await readErrorMessage(cbRes));
          const result = await cbRes.json();
          setInfo(
            `✅ 連携完了: ${
              result.display_name ||
              (result.username ? `@${result.username}` : '') ||
              ''
            }`
          );
          await refresh();
        } catch (e) {
          setError(e instanceof Error ? e.message : 'OAuth に失敗しました');
        } finally {
          setAuthBusy(false);
        }
      };
      window.addEventListener('message', onMessage);

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
    if (
      !confirm(
        'このチャンネルの TikTok 連携を解除しますか？\nClient Key/Secret も削除されます。'
      )
    )
      return;
    setError(null);
    const res = await fetch(
      `/api/channels/${encodeURIComponent(channelId)}/tiktok`,
      { method: 'DELETE' }
    );
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
      ? `${window.location.origin}/oauth/tiktok/callback`
      : 'http://localhost:3000/oauth/tiktok/callback';

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
            ? `接続済${
                status.display_name
                  ? `: ${status.display_name}`
                  : status.username
                  ? `: @${status.username}`
                  : ''
              }`
            : '未連携'}
        </span>
      </div>

      {status.connected && !status.can_direct_post && (
        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          ⚠️ video.publish スコープが未付与です。Direct Post（自動公開）には
          TikTok 開発者ポータルで video.publish を有効化し、再連携してください。
        </p>
      )}
      {!status.requests_installed && (
        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          ⚠️ requests ライブラリが未インストールです:
          <code className="ml-1">pip install requests</code>
        </p>
      )}

      <details className="rounded-lg bg-bg-elev/60 border border-border">
        <summary className="cursor-pointer text-sm font-semibold px-3 py-2 select-none">
          📖 TikTok連携の設定方法
        </summary>
        <div className="px-3 pb-3 pt-1 space-y-3 border-t border-border/50 mt-1">
          <ol className="list-decimal list-outside pl-5 space-y-1.5 text-xs text-slate-300 leading-relaxed">
            <li>
              <a
                href="https://developers.tiktok.com"
                target="_blank"
                rel="noreferrer"
                className="text-accent underline hover:no-underline"
              >
                TikTok for Developers
              </a>
              でアカウント登録 → アプリを作成
            </li>
            <li>
              「Login Kit」と「Content Posting API」を Products に追加
            </li>
            <li>
              スコープに <code>user.info.basic</code> /{' '}
              <code>video.publish</code> / <code>video.upload</code> を追加
            </li>
            <li>
              Redirect URI に下のフォームに表示される URL を登録
            </li>
            <li>
              「Client key」と「Client secret」を下の入力欄に貼り付け
            </li>
            <li>「TikTok と連携する」ボタンを押して認証</li>
          </ol>
          <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2 leading-relaxed">
            ⚠️ <b>未審査(unaudited)アプリ</b>では、API 経由の投稿は全て
            <b>非公開(SELF_ONLY)</b> に強制されます。一般公開するには
            TikTok のアプリ審査(audit)通過が必要です（2〜4週間）。
          </p>
        </div>
      </details>

      {(showClientForm || !status.client_configured) && (
        <details
          className="rounded-lg bg-bg-elev/60 border border-border p-3"
          open
        >
          <summary className="cursor-pointer text-sm font-semibold">
            🔧 TikTok クライアント情報
          </summary>
          <div className="mt-3 space-y-3">
            <p className="text-xs text-slate-400 leading-5">
              TikTok for Developers でアプリを作成し、Redirect URI に下記を登録してください:
            </p>
            <pre className="text-[10px] bg-bg whitespace-pre-wrap break-all p-2 rounded border border-border text-slate-300">
              {redirectExample}
            </pre>
            <Field label="Client Key">
              <input
                type="text"
                value={clientKey}
                onChange={(e) => setClientKey(e.target.value)}
                className="input"
                placeholder="aw...."
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
              disabled={savingClient || !clientKey || !clientSecret}
              className="btn-secondary w-full"
            >
              {savingClient ? '保存中…' : 'クライアント情報を保存'}
            </button>
          </div>
        </details>
      )}

      {status.client_configured && !showClientForm && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            Client key: <code>{status.client_key_preview}</code>
          </span>
          <button
            type="button"
            onClick={() => setShowClientForm(true)}
            className="text-xs text-slate-400 hover:text-slate-200 underline"
          >
            変更
          </button>
        </div>
      )}

      <div className="flex gap-2">
        {!status.connected ? (
          <button
            type="button"
            onClick={startAuth}
            disabled={
              !status.client_configured ||
              authBusy ||
              !status.requests_installed
            }
            className="btn-primary flex-1"
          >
            {authBusy ? '認証中…' : '🔗 TikTok と連携する'}
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
