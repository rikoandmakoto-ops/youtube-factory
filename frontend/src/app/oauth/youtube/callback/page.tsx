'use client';

import { useEffect, useState } from 'react';

/**
 * Google OAuth リダイレクト先。
 * クエリパラメータの code/state を opener に postMessage して閉じる。
 *
 * このページは認証専用で、親ウィンドウから popup として開かれる前提。
 */
export default function YoutubeOAuthCallback() {
  const [message, setMessage] = useState('処理中…');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    const error = url.searchParams.get('error');

    if (error) {
      setMessage(`認証エラー: ${error}`);
      return;
    }
    if (!code || !state) {
      setMessage('code または state が見つかりません');
      return;
    }

    if (window.opener) {
      window.opener.postMessage(
        { type: 'yt-oauth-callback', code, state },
        window.location.origin
      );
      setMessage('✅ 認証完了。このウィンドウは自動的に閉じます…');
      setTimeout(() => window.close(), 600);
    } else {
      setMessage('opener が見つかりません。元のタブに戻ってください。');
    }
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg text-slate-200 p-6">
      <div className="max-w-md text-center space-y-3">
        <h1 className="text-lg font-semibold">YouTube 認証</h1>
        <p className="text-sm text-slate-400">{message}</p>
      </div>
    </div>
  );
}
