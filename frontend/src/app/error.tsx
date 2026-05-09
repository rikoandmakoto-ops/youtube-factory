'use client';

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('App render error:', error);
  }, [error]);

  return (
    <main className="min-h-screen flex items-center justify-center px-5">
      <div className="w-full max-w-md card p-7 text-center space-y-3">
        <h1 className="text-lg font-semibold text-red-300">
          ⚠️ ページの読み込みに失敗しました
        </h1>
        <p className="text-sm text-slate-400">
          バックエンドに接続できないか、一時的なエラーが発生しています。
        </p>
        {error.digest && (
          <p className="text-[10px] text-slate-500">
            digest: <code>{error.digest}</code>
          </p>
        )}
        <div className="flex gap-2">
          <button onClick={reset} className="btn-primary flex-1">
            再試行
          </button>
          <a href="/" className="btn-secondary flex-1">
            ダッシュボードへ
          </a>
        </div>
      </div>
    </main>
  );
}
