'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Channel, Schedule, ScheduleInput } from '@/lib/api';

const DOW = [
  { value: 0, label: '日' },
  { value: 1, label: '月' },
  { value: 2, label: '火' },
  { value: 3, label: '水' },
  { value: 4, label: '木' },
  { value: 5, label: '金' },
  { value: 6, label: '土' },
];

const emptyDraft = (channelId: string): ScheduleInput => ({
  name: '',
  channel_id: channelId,
  days_of_week: [1, 4],
  hour: 19,
  minute: 0,
  theme_mode: 'auto',
  theme: '',
  duration_minutes: 12,
  auto_publish: false,
  publish_offset_minutes: null,
  enabled: true,
});

export default function ScheduleManager({
  initialSchedules,
  channels,
}: {
  initialSchedules: Schedule[];
  channels: Channel[];
}) {
  const router = useRouter();
  const [schedules, setSchedules] = useState(initialSchedules);
  const [draft, setDraft] = useState<ScheduleInput>(emptyDraft(channels[0]?.id || ''));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    const r = await fetch('/api/schedules', { cache: 'no-store' });
    if (r.ok) {
      const d = (await r.json()) as { schedules: Schedule[] };
      setSchedules(d.schedules);
    }
    router.refresh();
  };

  const startCreate = () => {
    setEditingId(null);
    setDraft(emptyDraft(channels[0]?.id || ''));
    setShowForm(true);
    setError(null);
  };

  const startEdit = (s: Schedule) => {
    setEditingId(s.id);
    setDraft({
      name: s.name,
      channel_id: s.channel_id,
      days_of_week: s.days_of_week,
      hour: s.hour,
      minute: s.minute,
      theme_mode: s.theme_mode,
      theme: s.theme || '',
      duration_minutes: s.duration_minutes,
      auto_publish: s.auto_publish,
      publish_offset_minutes: s.publish_offset_minutes ?? null,
      enabled: s.enabled,
    });
    setShowForm(true);
    setError(null);
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.name.trim() || !draft.channel_id) {
      setError('名前とチャンネルは必須です');
      return;
    }
    if (draft.days_of_week.length === 0) {
      setError('曜日を1つ以上選んでください');
      return;
    }
    if (draft.theme_mode === 'manual' && !(draft.theme || '').trim()) {
      setError('手動テーマモードはテーマが必須です');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const url = editingId
        ? `/api/schedules/${encodeURIComponent(editingId)}`
        : '/api/schedules';
      const res = await fetch(url, {
        method: editingId ? 'PUT' : 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error || `保存失敗 (${res.status})`);
      }
      setShowForm(false);
      setEditingId(null);
      await refresh();
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : '保存失敗');
    } finally {
      setSaving(false);
    }
  };

  const onToggle = async (s: Schedule) => {
    await fetch(`/api/schedules/${encodeURIComponent(s.id)}/toggle`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ enabled: !s.enabled }),
    });
    refresh();
  };

  const onDelete = async (s: Schedule) => {
    if (!confirm(`「${s.name}」を削除しますか？`)) return;
    await fetch(`/api/schedules/${encodeURIComponent(s.id)}`, {
      method: 'DELETE',
    });
    refresh();
  };

  const onRunNow = async (s: Schedule) => {
    if (!confirm(`「${s.name}」を今すぐ実行しますか？`)) return;
    await fetch(`/api/schedules/${encodeURIComponent(s.id)}/run-now`, {
      method: 'POST',
    });
    setTimeout(refresh, 800);
  };

  const toggleDow = (d: number) => {
    setDraft((prev) => ({
      ...prev,
      days_of_week: prev.days_of_week.includes(d)
        ? prev.days_of_week.filter((x) => x !== d)
        : [...prev.days_of_week, d].sort(),
    }));
  };

  return (
    <section className="px-5 space-y-4">
      <button onClick={startCreate} className="btn-primary w-full">
        ＋ 新規スケジュール
      </button>

      {showForm && (
        <form onSubmit={onSave} className="card space-y-3">
          <h3 className="font-bold text-slate-100">
            {editingId ? '✏️ スケジュール編集' : '➕ 新規スケジュール'}
          </h3>

          <div>
            <label className="label">名前</label>
            <input
              className="input"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="例: 月木の夜 19時"
              required
            />
          </div>

          <div>
            <label className="label">チャンネル</label>
            <select
              className="input"
              value={draft.channel_id}
              onChange={(e) => setDraft({ ...draft, channel_id: e.target.value })}
              required
            >
              {channels.length === 0 && <option value="">なし</option>}
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <span className="label">曜日</span>
            <div className="grid grid-cols-7 gap-1">
              {DOW.map((d) => {
                const active = draft.days_of_week.includes(d.value);
                return (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => toggleDow(d.value)}
                    className={`py-2 rounded-lg text-sm font-bold ${
                      active
                        ? 'bg-accent text-white'
                        : 'bg-bg-elev text-slate-400 border border-border'
                    }`}
                  >
                    {d.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">時</label>
              <input
                type="number"
                className="input"
                min={0}
                max={23}
                value={draft.hour}
                onChange={(e) =>
                  setDraft({ ...draft, hour: Number(e.target.value) || 0 })
                }
              />
            </div>
            <div>
              <label className="label">分</label>
              <input
                type="number"
                className="input"
                min={0}
                max={59}
                value={draft.minute}
                onChange={(e) =>
                  setDraft({ ...draft, minute: Number(e.target.value) || 0 })
                }
              />
            </div>
          </div>

          <div>
            <span className="label">テーマモード</span>
            <div className="grid grid-cols-2 gap-2">
              {(['auto', 'manual'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setDraft({ ...draft, theme_mode: m })}
                  className={`py-2 rounded-lg text-sm font-semibold ${
                    draft.theme_mode === m
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-400 border border-border'
                  }`}
                >
                  {m === 'auto' ? '🤖 AI自動選択' : '✍️ 手動指定'}
                </button>
              ))}
            </div>
          </div>

          {draft.theme_mode === 'manual' && (
            <div>
              <label className="label">テーマ</label>
              <input
                className="input"
                value={draft.theme || ''}
                onChange={(e) => setDraft({ ...draft, theme: e.target.value })}
                placeholder="例: なぜ空は青いのか？"
              />
            </div>
          )}

          <div>
            <label className="label">尺（分）</label>
            <input
              type="number"
              className="input"
              min={1}
              max={60}
              value={draft.duration_minutes}
              onChange={(e) =>
                setDraft({ ...draft, duration_minutes: Number(e.target.value) || 12 })
              }
            />
          </div>

          <label className="flex items-center gap-2 select-none cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={draft.auto_publish}
              onChange={(e) =>
                setDraft({ ...draft, auto_publish: e.target.checked })
              }
              className="w-4 h-4 accent-accent"
            />
            <span>生成完了後にYouTubeへ自動投稿</span>
          </label>

          {draft.auto_publish && (
            <div className="border-l-2 border-accent/40 pl-3 ml-1 space-y-2">
              <label className="label">📅 公開タイミング</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setDraft({ ...draft, publish_offset_minutes: null })
                  }
                  className={`py-2 rounded-lg text-sm font-semibold ${
                    !draft.publish_offset_minutes
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-400 border border-border'
                  }`}
                >
                  即時公開
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      publish_offset_minutes: draft.publish_offset_minutes || 60,
                    })
                  }
                  className={`py-2 rounded-lg text-sm font-semibold ${
                    draft.publish_offset_minutes
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-400 border border-border'
                  }`}
                >
                  スケジュール公開
                </button>
              </div>
              {!!draft.publish_offset_minutes && (
                <div>
                  <label className="label">
                    生成完了から何分後に公開するか
                  </label>
                  <input
                    type="number"
                    className="input"
                    min={1}
                    max={60 * 24 * 30}
                    value={draft.publish_offset_minutes ?? ''}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        publish_offset_minutes:
                          Number(e.target.value) || null,
                      })
                    }
                  />
                  <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                    例: 60 → 生成完了から1時間後に YouTube 上で公開。最大 30 日 (43200 分)。
                  </p>
                </div>
              )}
            </div>
          )}

          <label className="flex items-center gap-2 select-none cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              className="w-4 h-4 accent-accent"
            />
            <span>有効化</span>
          </label>

          {error && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary flex-1"
            >
              キャンセル
            </button>
            <button type="submit" disabled={saving} className="btn-primary flex-1">
              {saving ? '保存中…' : '💾 保存'}
            </button>
          </div>
        </form>
      )}

      <div className="space-y-2">
        {schedules.length === 0 && !showForm && (
          <p className="text-sm text-slate-500 text-center py-6">
            まだスケジュールがありません
          </p>
        )}
        {schedules.map((s) => (
          <ScheduleRow
            key={s.id}
            schedule={s}
            onEdit={() => startEdit(s)}
            onToggle={() => onToggle(s)}
            onDelete={() => onDelete(s)}
            onRunNow={() => onRunNow(s)}
          />
        ))}
      </div>
    </section>
  );
}

function ScheduleRow({
  schedule,
  onEdit,
  onToggle,
  onDelete,
  onRunNow,
}: {
  schedule: Schedule;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
  onRunNow: () => void;
}) {
  const days = schedule.days_of_week
    .map((d) => DOW.find((x) => x.value === d)?.label || '?')
    .join('・');
  const nextRun = schedule.next_run_at
    ? new Date(schedule.next_run_at).toLocaleString('ja-JP', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h4 className="font-bold text-slate-100 truncate">{schedule.name}</h4>
          <p className="text-xs text-slate-400 mt-1">
            📺 {schedule.channel_id} · 毎週 <strong>{days}</strong>{' '}
            <strong>
              {String(schedule.hour).padStart(2, '0')}:
              {String(schedule.minute).padStart(2, '0')}
            </strong>
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {schedule.theme_mode === 'auto' ? '🤖 AI自動' : `✍️ ${schedule.theme}`}
            {' · '}
            {schedule.duration_minutes}分
            {schedule.auto_publish && ' · 📤 自動投稿'}
            {schedule.auto_publish && schedule.publish_offset_minutes
              ? ` (${schedule.publish_offset_minutes}分後)`
              : ''}
          </p>
          {schedule.enabled && (
            <p className="text-xs text-emerald-400 mt-1">⏰ 次回: {nextRun}</p>
          )}
          {schedule.last_run_at && (
            <p className="text-[10px] text-slate-500 mt-1">
              最終実行: {new Date(schedule.last_run_at).toLocaleString('ja-JP')}{' '}
              ({schedule.last_run_status})
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onToggle}
          className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${
            schedule.enabled
              ? 'bg-emerald-700/40 text-emerald-300 border border-emerald-700/40'
              : 'bg-bg-elev text-slate-500 border border-border'
          }`}
          aria-pressed={schedule.enabled}
        >
          {schedule.enabled ? 'ON' : 'OFF'}
        </button>
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={onRunNow} className="btn-ghost text-xs py-2 px-3 flex-1">
          ▶️ 今すぐ実行
        </button>
        <button onClick={onEdit} className="btn-ghost text-xs py-2 px-3 flex-1">
          ✏️ 編集
        </button>
        <button
          onClick={onDelete}
          className="btn-ghost text-xs py-2 px-3 text-red-300 hover:bg-red-500/10"
        >
          🗑️
        </button>
      </div>
    </div>
  );
}
