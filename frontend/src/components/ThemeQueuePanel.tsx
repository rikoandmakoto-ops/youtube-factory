'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ThemeQueueStatus,
  ThemeQueueItem,
  getThemeQueue,
  replenishThemeQueue,
  addThemeQueueItem,
  removeThemeQueueItem,
  updateThemeQueueSettings,
  ApiError,
} from '@/lib/api';

type Props = {
  channelId: string;
  channelName?: string;
};

function fmtRelative(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const sec = Math.round(diff / 1000);
    if (sec < 60) return `${sec}秒前`;
    const min = Math.round(sec / 60);
    if (min < 60) return `${min}分前`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}時間前`;
    const day = Math.round(hr / 24);
    return `${day}日前`;
  } catch {
    return iso;
  }
}

export default function ThemeQueuePanel({ channelId, channelName }: Props) {
  const [status, setStatus] = useState<ThemeQueueStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'replenish' | 'add' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [newAngle, setNewAngle] = useState('');
  const [editSettings, setEditSettings] = useState(false);
  const [targetSize, setTargetSize] = useState<number>(10);
  const [minThreshold, setMinThreshold] = useState<number>(5);

  const refresh = useCallback(async () => {
    try {
      const s = await getThemeQueue(channelId);
      setStatus(s);
      setTargetSize(s.target_size);
      setMinThreshold(s.min_threshold);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'キューの取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onReplenish = async () => {
    setBusy('replenish');
    setError(null);
    setInfo(null);
    try {
      const res = await replenishThemeQueue(channelId);
      const added = (res as { added?: ThemeQueueItem[] }).added?.length ?? 0;
      const skipped = (res as { skipped_reason?: string }).skipped_reason;
      if (added > 0) {
        setInfo(`${added}件補充しました`);
      } else if (skipped === 'already_full') {
        setInfo('既に在庫が充足しています');
      } else {
        setInfo('補充できる新規ネタが見つかりませんでした');
      }
      setStatus(res);
      setTargetSize(res.target_size);
      setMinThreshold(res.min_threshold);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '補充に失敗しました');
    } finally {
      setBusy(null);
    }
  };

  const onAdd = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setBusy('add');
    setError(null);
    setInfo(null);
    try {
      const res = await addThemeQueueItem(channelId, {
        title,
        angle: newAngle.trim(),
      });
      setStatus(res.queue);
      setNewTitle('');
      setNewAngle('');
      setInfo('追加しました');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '追加に失敗しました');
    } finally {
      setBusy(null);
    }
  };

  const onRemove = async (itemId: string) => {
    setError(null);
    try {
      const res = await removeThemeQueueItem(channelId, itemId);
      setStatus(res.queue);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '削除に失敗しました');
    }
  };

  const onSaveSettings = async () => {
    setError(null);
    try {
      const res = await updateThemeQueueSettings(channelId, {
        target_size: targetSize,
        min_threshold: minThreshold,
      });
      setStatus(res);
      setEditSettings(false);
      setInfo('設定を保存しました');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '設定保存に失敗しました');
    }
  };

  if (loading) {
    return (
      <section className="card mx-5 mt-3">
        <h2 className="text-sm font-bold text-slate-200">🧺 テーマキュー</h2>
        <p className="text-xs text-slate-400 mt-2">読み込み中…</p>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="card mx-5 mt-3">
        <h2 className="text-sm font-bold text-slate-200">🧺 テーマキュー</h2>
        <p className="text-xs text-red-300 mt-2">⚠️ {error ?? '取得できませんでした'}</p>
      </section>
    );
  }

  const stockPct = Math.min(100, Math.round((status.stock / Math.max(1, status.target_size)) * 100));
  const lowStock = status.below_threshold;

  return (
    <section className="card mx-5 mt-3">
      <header className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-slate-200">🧺 テーマキュー</h2>
          {channelName && (
            <span className="text-xs text-slate-500">{channelName}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-mono px-2 py-0.5 rounded-full border ${
              lowStock
                ? 'bg-red-500/10 text-red-300 border-red-500/40'
                : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/40'
            }`}
            title={`目標 ${status.target_size} / 閾値 ${status.min_threshold}`}
          >
            {status.stock} / {status.target_size}
          </span>
          <button
            type="button"
            className="btn-primary text-xs py-1 px-3"
            onClick={onReplenish}
            disabled={busy === 'replenish'}
          >
            {busy === 'replenish' ? '補充中…' : '＋ 手動補充'}
          </button>
        </div>
      </header>

      <div className="h-1.5 rounded-full bg-bg-elev overflow-hidden">
        <div
          className={`h-full ${lowStock ? 'bg-red-500' : 'bg-emerald-500'}`}
          style={{ width: `${stockPct}%` }}
        />
      </div>

      <p className="text-[11px] text-slate-500 mt-2">
        最終補充: {fmtRelative(status.last_replenished_at)} ／ 最終確認: {fmtRelative(status.last_checked_at)}
        {status.last_error && (
          <span className="text-amber-300 ml-2">⚠️ {status.last_error}</span>
        )}
      </p>

      {info && (
        <div className="mt-2 text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-md px-2 py-1.5">
          {info}
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-md px-2 py-1.5">
          ⚠️ {error}
        </div>
      )}

      <div className="mt-3">
        {status.items.length === 0 ? (
          <p className="text-xs text-slate-400 py-3 text-center">
            ストックが空です。「手動補充」を押すか、下のフォームから追加してください。
          </p>
        ) : (
          <ol className="space-y-1.5">
            {status.items.map((item, idx) => (
              <li
                key={item.id}
                className="flex items-start gap-2 py-1.5 px-2 rounded-md hover:bg-bg-elev/50 border-b border-border/40 last:border-0"
              >
                <span className="text-slate-500 w-5 text-center text-xs mt-0.5 shrink-0">
                  {idx + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-200 truncate" title={item.title}>
                    {item.title}
                  </div>
                  {item.angle && (
                    <div className="text-[11px] text-slate-400 truncate">
                      切り口: {item.angle}
                    </div>
                  )}
                  <div className="text-[10px] text-slate-500 mt-0.5 flex gap-2 flex-wrap">
                    <span>{item.source === 'manual' ? '✋ 手動' : '🤖 自動'}</span>
                    {item.is_trending && (
                      <span className="text-amber-400">📈 トレンド</span>
                    )}
                    {item.trend_match && (
                      <span className="text-amber-400/80">「{item.trend_match}」</span>
                    )}
                    {item.parent_title && (
                      <span title={`シリーズ元: ${item.parent_title}`}>
                        🔗 続編
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="text-xs text-slate-500 hover:text-red-400 px-1.5 py-0.5 shrink-0"
                  onClick={() => onRemove(item.id)}
                  title="削除"
                  aria-label={`${item.title}を削除`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      <details className="mt-3 group">
        <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-300 select-none">
          ＋ 手動でネタを追加
        </summary>
        <div className="mt-2 space-y-1.5">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="テーマ（例: なぜ夕焼けは赤いのか）"
            className="w-full text-sm rounded-md bg-bg-elev border border-border px-2 py-1.5"
          />
          <input
            type="text"
            value={newAngle}
            onChange={(e) => setNewAngle(e.target.value)}
            placeholder="切り口（任意）"
            className="w-full text-sm rounded-md bg-bg-elev border border-border px-2 py-1.5"
          />
          <button
            type="button"
            className="btn-secondary text-xs py-1 px-3"
            onClick={onAdd}
            disabled={busy === 'add' || !newTitle.trim()}
          >
            {busy === 'add' ? '追加中…' : '追加'}
          </button>
        </div>
      </details>

      <details
        className="mt-2"
        open={editSettings}
        onToggle={(e) => setEditSettings((e.target as HTMLDetailsElement).open)}
      >
        <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-300 select-none">
          ⚙️ ストック設定
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-300">
            目標ストック数
            <input
              type="number"
              min={1}
              max={50}
              value={targetSize}
              onChange={(e) => setTargetSize(parseInt(e.target.value || '10', 10))}
              className="w-full mt-1 text-sm rounded-md bg-bg-elev border border-border px-2 py-1.5"
            />
          </label>
          <label className="text-xs text-slate-300">
            補充閾値（これ未満で自動補充）
            <input
              type="number"
              min={0}
              max={50}
              value={minThreshold}
              onChange={(e) => setMinThreshold(parseInt(e.target.value || '5', 10))}
              className="w-full mt-1 text-sm rounded-md bg-bg-elev border border-border px-2 py-1.5"
            />
          </label>
          <button
            type="button"
            className="btn-secondary col-span-2 text-xs py-1 px-3"
            onClick={onSaveSettings}
          >
            設定を保存
          </button>
        </div>
      </details>
    </section>
  );
}
