'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginForm({ next }: { next?: string }) {
  const router = useRouter();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password }),
    });

    if (res.ok) {
      startTransition(() => {
        router.push(next || '/');
        router.refresh();
      });
      return;
    }

    if (res.status === 429) {
      setError('試行回数が多すぎます。1分後に再度お試しください。');
    } else if (res.status === 401) {
      setError('パスワードが違います');
    } else {
      setError('ログインに失敗しました');
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div>
        <label htmlFor="password" className="label">
          パスワード
        </label>
        <input
          id="password"
          type="password"
          inputMode="text"
          autoComplete="current-password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="input"
          placeholder="••••••••"
        />
      </div>

      {error && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={pending || !password}
        className="btn-primary w-full"
      >
        {pending ? 'ログイン中…' : 'ログイン'}
      </button>
    </form>
  );
}
