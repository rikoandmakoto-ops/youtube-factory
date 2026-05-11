'use client';

import { useEffect, useState } from 'react';
import { Field } from '@/components/Field';
import type { YoutubeStatus } from '@/lib/api';

const POPUP_FEATURES = 'width=520,height=720';

/**
 * チャンネル別 YouTube OAuth 連携 UI
 *
 * 認証コールバックは新しいウィンドウから親へ postMessage で受け取り、
 * このコンポーネントが /api/channels/{id}/youtube/callback を叩いて完了する。
 */
export default function ChannelYoutubeConnect({
  channelId,
}: {
  channelId: string;
}) {
  const [status, setStatus] = useState<YoutubeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [savingClient, setSavingClient] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [showClientForm, setShowClientForm] = useState(false);

  const refresh = async () => {
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/youtube/status`,
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
        `/api/channels/${encodeURIComponent(channelId)}/youtube/client`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            client_id: clientId,
            client_secret: clientSecret,
          }),
        }
      );
      if (!res.ok) throw new Error(await res.text());
      setClientId('');
      setClientSecret('');
      setInfo('✅ OAuth クライアント情報を保存しました');
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
    setAuthBusy(true);

    // ポップアップブロッカー対策: 必ずユーザーアクション直後に開く
    const popup = window.open('about:blank', 'yt-oauth', POPUP_FEATURES);
    if (!popup) {
      setError('ポップアップがブロックされました');
      setAuthBusy(false);
      return;
    }

    try {
      const redirectUri = `${window.location.origin}/oauth/youtube/callback`;
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/youtube/auth`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ redirect_uri: redirectUri }),
        }
      );
      if (!res.ok) {
        popup.close();
        throw new Error(await res.text());
      }
      const data: { auth_url: string; state: string } = await res.json();

      popup.location.href = data.auth_url;

      // ポップアップから state/code を受け取る
      const onMessage = async (ev: MessageEvent) => {
        if (ev.origin !== window.location.origin) return;
        if (ev.data?.type !== 'yt-oauth-callback') return;
        window.removeEventListener('message', onMessage);
        try {
          const cbRes = await fetch(
            `/api/channels/${encodeURIComponent(
              channelId
            )}/youtube/callback`,
            {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              body: JSON.stringify({
                state: ev.data.state,
                code: ev.data.code,
              }),
            }
          );
          if (!cbRes.ok) throw new Error(await cbRes.text());
          const result = await cbRes.json();
          setInfo(
            `✅ 連携完了: ${
              result.youtube_channel_name || result.account_email || ''
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
    if (
      !confirm(
        'このチャンネルの YouTube 連携を解除しますか？\nClient ID/Secret も削除されます。'
      )
    )
      return;
    setError(null);
    const res = await fetch(
      `/api/channels/${encodeURIComponent(channelId)}/youtube`,
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
      ? `${window.location.origin}/oauth/youtube/callback`
      : 'http://localhost:3000/oauth/youtube/callback';

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
                status.youtube_channel_name
                  ? `: ${status.youtube_channel_name}`
                  : status.account_email
                  ? `: ${status.account_email}`
                  : ''
              }`
            : '未連携'}
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

      <details className="rounded-lg bg-bg-elev/60 border border-border">
        <summary className="cursor-pointer text-sm font-semibold px-3 py-2 select-none">
          📖 YouTube連携の設定方法
        </summary>
        <div className="px-3 pb-3 pt-1 space-y-3 border-t border-border/50 mt-1">
          <ol className="list-decimal list-outside pl-5 space-y-1.5 text-xs text-slate-300 leading-relaxed">
            <li>
              <a
                href="https://console.cloud.google.com"
                target="_blank"
                rel="noreferrer"
                className="text-accent underline hover:no-underline"
              >
                Google Cloud Console
              </a>
              でプロジェクトを作成
            </li>
            <li>
              「APIとサービス」→「ライブラリ」→「YouTube Data API v3」を有効化
            </li>
            <li>
              「OAuth同意画面」→「外部」で作成、アプリ名とメールを入力
            </li>
            <li>テストユーザーに自分のGmailを追加</li>
            <li>
              「認証情報」→「OAuthクライアントID」→「ウェブアプリケーション」で作成
              <span className="block text-[10px] text-slate-500 mt-0.5">
                ※ 承認済みリダイレクトURIには下のフォームに表示されるURLを追加
              </span>
            </li>
            <li>
              表示される「クライアントID」と「クライアントシークレット」を下の入力欄に貼り付け
            </li>
            <li>
              「YouTubeと連携する」ボタンを押してGoogleアカウントで認証
            </li>
          </ol>
          <p className="text-xs text-slate-300 bg-accent/10 border border-accent/30 rounded px-3 py-2 leading-relaxed">
            💡 OAuth連携すれば動画アップロード・アナリティクス取得・いいね率分析が全てできます。別途APIキーの設定は不要です。
          </p>
        </div>
      </details>

      {(showClientForm || !status.client_configured) && (
        <details
          className="rounded-lg bg-bg-elev/60 border border-border p-3"
          open
        >
          <summary className="cursor-pointer text-sm font-semibold">
            🔧 OAuth クライアント情報
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

      {status.client_configured && !showClientForm && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            OAuth クライアント: <code>{status.client_id_preview}</code>
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
              !status.google_libs_installed
            }
            className="btn-primary flex-1"
          >
            {authBusy ? '認証中…' : '🔗 YouTube と連携する'}
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
