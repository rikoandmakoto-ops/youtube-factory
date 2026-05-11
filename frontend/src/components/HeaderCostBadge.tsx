import Link from 'next/link';
import { getCostSummary, ApiError } from '@/lib/api';

const USD_TO_JPY = 155;

export default async function HeaderCostBadge() {
  let today = 0;
  let monthly = 0;
  try {
    const cost = await getCostSummary();
    today = Math.round((cost.today?.cost_usd || 0) * USD_TO_JPY);
    monthly = Math.round((cost.this_month?.cost_usd || 0) * USD_TO_JPY);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    return null;
  }

  return (
    <Link
      href="/history"
      aria-label={`API使用料金: 今日 ¥${today.toLocaleString('ja-JP')}, 今月 ¥${monthly.toLocaleString('ja-JP')} (詳細を見る)`}
      className="flex items-stretch gap-px rounded-md bg-bg-elev border border-border overflow-hidden hover:border-accent/50 transition"
    >
      <div className="px-2 py-1 text-right">
        <div className="text-[9px] leading-none text-slate-400 uppercase tracking-wide">今日</div>
        <div className="text-xs font-bold leading-tight tabular-nums text-slate-100">
          ¥{today.toLocaleString('ja-JP')}
        </div>
      </div>
      <div className="px-2 py-1 text-right bg-accent/10 border-l border-border">
        <div className="text-[9px] leading-none text-accent/80 uppercase tracking-wide">今月</div>
        <div className="text-xs font-bold leading-tight tabular-nums text-accent">
          ¥{monthly.toLocaleString('ja-JP')}
        </div>
      </div>
    </Link>
  );
}
