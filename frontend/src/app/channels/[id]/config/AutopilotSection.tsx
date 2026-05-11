'use client';

import { useEffect, useMemo, useState } from 'react';
import { Field, NumberField, Row, Section, Toggle } from '@/components/Field';
import type { AutopilotConfig, AutopilotResponse, AutopilotTheme } from '@/lib/api';

const DOW_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

function defaultConfig(): AutopilotConfig {
  return {
    enabled: false,
    schedule: { days_of_week: [], hour: 18, minute: 0 },
    duration_minutes: 12,
    theme_queue: [],
  };
}

function fmtNext(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ja-JP', {
      month: 'short',
      day: 'numeric',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function AutopilotSection({ channelId }: { channelId: string }) {
  const [cfg, setCfg] = useState<AutopilotConfig>(defaultConfig());
  const [nextRunAt, setNextRunAt] = useState<string | null>(null);
  const [schedulerAvailable, setSchedulerAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [newTitle, setNewTitle] = useState('');
  const [newAngle, setNewAngle] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editAngle, setEditAngle] = useState('');

  const apply = (data: AutopilotResponse) => {
    setCfg(data.config);
    setNextRunAt(data.next_run_at);
    setSchedulerAvailable(data.scheduler_available);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetch(`/api/channels/${encodeURIComponent(channelId)}/autopilot`, {
      cache: 'no-store',
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as AutopilotResponse;
      })
      .then((d) => mounted && apply(d))
      .catch((e) =>
        mounted && setError(e instanceof Error ? e.message : '取得失敗')
      )
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [channelId]);

  const flash = (msg: string) => {
    setInfo(msg);
    setTimeout(() => setInfo((m) => (m === msg ? null : m)), 2500);
  };

  const saveSettings = async (next: Partial<AutopilotConfig>) => {
    setSaving(true);
    setError(null);
    try {
      const patch: Record<string, unknown> = {};
      if (next.enabled !== undefined) patch.enabled = next.enabled;
      if (next.schedule !== undefined) patch.schedule = next.schedule;
      if (next.duration_minutes !== undefined)
        patch.duration_minutes = next.duration_minutes;

      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot`,
        {
          method: 'PUT',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(patch),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || (await res.text()) || '保存失敗');
      }
      apply((await res.json()) as AutopilotResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失敗');
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = (enabled: boolean) => {
    if (enabled && cfg.schedule.days_of_week.length === 0) {
      setError('曜日を1つ以上選んでからフルオートを有効化してください');
      return;
    }
    saveSettings({ enabled });
  };

  const toggleDay = (d: number) => {
    const set = new Set(cfg.schedule.days_of_week);
    if (set.has(d)) set.delete(d);
    else set.add(d);
    const days = Array.from(set).sort((a, b) => a - b);
    saveSettings({ schedule: { ...cfg.schedule, days_of_week: days } });
  };

  const setHour = (hour: number) =>
    saveSettings({
      schedule: { ...cfg.schedule, hour: Math.max(0, Math.min(23, hour)) },
    });
  const setMinute = (minute: number) =>
    saveSettings({
      schedule: { ...cfg.schedule, minute: Math.max(0, Math.min(59, minute)) },
    });
  const setDuration = (n: number) =>
    saveSettings({ duration_minutes: Math.max(1, Math.min(60, n)) });

  // ── Queue operations ──

  const addTheme = async () => {
    if (!newTitle.trim()) return;
    setBusy('add');
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ title: newTitle, angle: newAngle }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || '追加失敗');
      }
      const data = await res.json();
      setCfg((prev) => ({ ...prev, theme_queue: data.queue }));
      setNewTitle('');
      setNewAngle('');
    } catch (e) {
      setError(e instanceof Error ? e.message : '追加失敗');
    } finally {
      setBusy(null);
    }
  };

  const reorder = async (queue: AutopilotTheme[]) => {
    const prev = cfg.theme_queue;
    setCfg((c) => ({ ...c, theme_queue: queue }));
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue`,
        {
          method: 'PUT',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ queue }),
        }
      );
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCfg((c) => ({ ...c, theme_queue: data.queue }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '並び替え失敗');
      setCfg((c) => ({ ...c, theme_queue: prev }));
    }
  };

  const moveUp = (i: number) => {
    if (i === 0) return;
    const q = [...cfg.theme_queue];
    [q[i - 1], q[i]] = [q[i], q[i - 1]];
    reorder(q);
  };
  const moveDown = (i: number) => {
    if (i >= cfg.theme_queue.length - 1) return;
    const q = [...cfg.theme_queue];
    [q[i], q[i + 1]] = [q[i + 1], q[i]];
    reorder(q);
  };

  const startEdit = (t: AutopilotTheme) => {
    setEditingId(t.id);
    setEditTitle(t.title);
    setEditAngle(t.angle ?? '');
  };
  const cancelEdit = () => {
    setEditingId(null);
    setEditTitle('');
    setEditAngle('');
  };
  const saveEdit = async (themeId: string) => {
    setBusy(`edit:${themeId}`);
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/${encodeURIComponent(themeId)}`,
        {
          method: 'PATCH',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ title: editTitle, angle: editAngle }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || '編集失敗');
      }
      const data = await res.json();
      setCfg((c) => ({ ...c, theme_queue: data.queue }));
      cancelEdit();
    } catch (e) {
      setError(e instanceof Error ? e.message : '編集失敗');
    } finally {
      setBusy(null);
    }
  };

  const removeTheme = async (themeId: string) => {
    if (!confirm('このテーマを削除しますか？')) return;
    setBusy(`del:${themeId}`);
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/${encodeURIComponent(themeId)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || '削除失敗');
      }
      const data = await res.json();
      setCfg((c) => ({ ...c, theme_queue: data.queue }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '削除失敗');
    } finally {
      setBusy(null);
    }
  };

  const refill = async () => {
    setBusy('refill');
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/queue/refill`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ count: 5 }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || 'AI 補充失敗');
      }
      const data = await res.json();
      setCfg((c) => ({ ...c, theme_queue: data.queue }));
      flash(`✨ ${data.added?.length || 0} 件のテーマを追加しました`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI 補充失敗');
    } finally {
      setBusy(null);
    }
  };

  const runNow = async () => {
    if (!confirm('今すぐ1本生成 → 自動投稿します。よろしいですか？')) return;
    setBusy('run');
    setError(null);
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(channelId)}/autopilot/run-now`,
        { method: 'POST' }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || '実行失敗');
      }
      flash('🚀 即時実行をキックしました（履歴で進捗を確認）');
    } catch (e) {
      setError(e instanceof Error ? e.message : '実行失敗');
    } finally {
      setBusy(null);
    }
  };

  const summary = useMemo(() => {
    if (!cfg.enabled) return 'OFF';
    const days =
      cfg.schedule.days_of_week.length === 7
        ? '毎日'
        : cfg.schedule.days_of_week.length === 0
          ? '曜日未設定'
          : cfg.schedule.days_of_week.map((d) => DOW_LABELS[d]).join('・');
    const time = `${String(cfg.schedule.hour).padStart(2, '0')}:${String(cfg.schedule.minute).padStart(2, '0')}`;
    return `${days} ${time}`;
  }, [cfg]);

  return (
    <Section
      title="🤖 フルオート自動投稿"
      description={`設定中: ${summary} ／ 次回: ${fmtNext(nextRunAt)}`}
      defaultOpen
    >
      {!schedulerAvailable && (
        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          ⚠️ APScheduler がバックエンドにインストールされていません。設定は保存できますが自動発火しません。
        </p>
      )}

      {loading ? (
        <p className="text-xs text-slate-500">読み込み中…</p>
      ) : (
        <>
          <Toggle
            checked={cfg.enabled}
            onChange={toggleEnabled}
            label="フルオートを有効化"
            description="設定した曜日・時間に自動でシナリオ生成→動画生成→YouTube投稿まで行います"
          />

          <div className="rounded-xl bg-bg-elev/60 border border-border p-3 space-y-3">
            <div>
              <p className="label">投稿曜日</p>
              <div className="flex gap-1.5 flex-wrap">
                {DOW_LABELS.map((label, i) => {
                  const active = cfg.schedule.days_of_week.includes(i);
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => toggleDay(i)}
                      disabled={saving}
                      className={`w-10 h-10 rounded-full text-sm border transition ${
                        active
                          ? 'bg-accent text-white border-accent'
                          : 'bg-bg-elev text-slate-300 border-border hover:bg-slate-700'
                      } disabled:opacity-50`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <Row>
              <Field label="時 (0-23)">
                <NumberField
                  value={cfg.schedule.hour}
                  onChange={setHour}
                  min={0}
                  max={23}
                />
              </Field>
              <Field label="分 (0-59)">
                <NumberField
                  value={cfg.schedule.minute}
                  onChange={setMinute}
                  min={0}
                  max={59}
                />
              </Field>
            </Row>

            <Field label="動画尺 (分)" hint="自動生成する動画の目安尺">
              <NumberField
                value={cfg.duration_minutes}
                onChange={setDuration}
                min={1}
                max={60}
                unit="分"
              />
            </Field>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-200 text-sm">
                🗒️ テーマキュー ({cfg.theme_queue.length} 件)
              </h3>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={refill}
                  disabled={busy === 'refill'}
                  className="btn-secondary text-xs py-1 px-2"
                >
                  {busy === 'refill' ? '補充中…' : '✨ AIで補充'}
                </button>
                <button
                  type="button"
                  onClick={runNow}
                  disabled={busy === 'run'}
                  className="btn-ghost text-xs py-1 px-2"
                >
                  {busy === 'run' ? '実行中…' : '▶ 今すぐ実行'}
                </button>
              </div>
            </div>

            <p className="text-xs text-slate-500">
              キューは上から順に消費されます。空になると AI が自動でテーマを提案して補充します。
            </p>

            {cfg.theme_queue.length === 0 ? (
              <div className="text-xs text-slate-500 py-3 text-center border border-dashed border-border rounded-lg">
                テーマがまだありません — 下のフォームか「AIで補充」で追加してください
              </div>
            ) : (
              <ul className="space-y-2">
                {cfg.theme_queue.map((t, i) => {
                  const isEditing = editingId === t.id;
                  return (
                    <li
                      key={t.id}
                      className="rounded-lg bg-bg-elev border border-border p-2 space-y-2"
                    >
                      <div className="flex gap-2 items-start">
                        <div className="flex flex-col gap-0.5 shrink-0">
                          <button
                            type="button"
                            onClick={() => moveUp(i)}
                            disabled={i === 0}
                            className="text-xs px-1 text-slate-400 disabled:opacity-30 hover:text-slate-200"
                            aria-label="上へ"
                          >
                            ▲
                          </button>
                          <span className="text-[10px] text-slate-500 text-center">
                            {i + 1}
                          </span>
                          <button
                            type="button"
                            onClick={() => moveDown(i)}
                            disabled={i === cfg.theme_queue.length - 1}
                            className="text-xs px-1 text-slate-400 disabled:opacity-30 hover:text-slate-200"
                            aria-label="下へ"
                          >
                            ▼
                          </button>
                        </div>
                        <div className="flex-1 min-w-0">
                          {isEditing ? (
                            <div className="space-y-2">
                              <input
                                className="input"
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                placeholder="タイトル"
                              />
                              <input
                                className="input text-xs"
                                value={editAngle}
                                onChange={(e) => setEditAngle(e.target.value)}
                                placeholder="切り口（任意）"
                              />
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  onClick={() => saveEdit(t.id)}
                                  disabled={busy === `edit:${t.id}`}
                                  className="btn-primary text-xs py-1 px-3"
                                >
                                  保存
                                </button>
                                <button
                                  type="button"
                                  onClick={cancelEdit}
                                  className="btn-ghost text-xs py-1 px-3"
                                >
                                  キャンセル
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <p className="text-sm font-medium text-slate-100 truncate">
                                {t.title}
                              </p>
                              {t.angle && (
                                <p className="text-xs text-slate-500 truncate">
                                  {t.angle}
                                </p>
                              )}
                            </>
                          )}
                        </div>
                        {!isEditing && (
                          <div className="flex gap-1 shrink-0">
                            <button
                              type="button"
                              onClick={() => startEdit(t)}
                              className="text-xs text-slate-400 hover:text-slate-200 px-1"
                              aria-label="編集"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={() => removeTheme(t.id)}
                              disabled={busy === `del:${t.id}`}
                              className="text-xs text-red-400 hover:text-red-300 px-1"
                              aria-label="削除"
                            >
                              🗑️
                            </button>
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <div className="rounded-lg border border-border p-2 space-y-2 bg-bg/40">
              <p className="text-xs text-slate-400">＋ テーマを追加</p>
              <input
                className="input"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="例: なぜ猫は液体のように振る舞うのか"
              />
              <input
                className="input text-xs"
                value={newAngle}
                onChange={(e) => setNewAngle(e.target.value)}
                placeholder="切り口（任意）例: 粘弾性物性"
              />
              <button
                type="button"
                onClick={addTheme}
                disabled={busy === 'add' || !newTitle.trim()}
                className="btn-secondary w-full text-sm"
              >
                {busy === 'add' ? '追加中…' : 'キューに追加'}
              </button>
            </div>
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
        </>
      )}
    </Section>
  );
}
