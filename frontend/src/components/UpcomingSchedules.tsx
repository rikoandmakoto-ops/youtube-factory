import Link from 'next/link';
import { listUpcomingSchedules, ApiError } from '@/lib/api';

function formatDateTime(s: string): string {
  try {
    return new Date(s).toLocaleString('ja-JP', {
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return s;
  }
}

export default async function UpcomingSchedules() {
  let upcoming: Awaited<ReturnType<typeof listUpcomingSchedules>>['upcoming'] = [];
  try {
    const r = await listUpcomingSchedules(5);
    upcoming = r.upcoming || [];
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    return null;
  }

  return (
    <section aria-label="次回スケジュール" className="mx-5 mt-4 card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-bold text-slate-100">⏰ 次回スケジュール</h2>
        <Link href="/schedule" className="text-xs text-accent hover:underline">
          管理 →
        </Link>
      </div>
      {upcoming.length === 0 ? (
        <p className="text-xs text-slate-500">
          有効なスケジュールはありません
        </p>
      ) : (
        <ul className="space-y-1.5">
          {upcoming.map((u) => (
            <li
              key={u.id}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <p className="text-slate-200 truncate">{u.name}</p>
                <p className="text-slate-500 text-[10px]">
                  📺 {u.channel_id} ·{' '}
                  {u.theme_mode === 'auto' ? '🤖 AI' : `✍️ ${u.theme || ''}`}
                </p>
              </div>
              <span className="shrink-0 text-emerald-400 tabular-nums">
                {formatDateTime(u.next_run_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
