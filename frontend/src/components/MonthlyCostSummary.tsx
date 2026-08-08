import Link from 'next/link';
import { ApiError } from '@/lib/api';
import { getCostSummaryCached } from '@/lib/server-cost';

const USD_TO_JPY = 155;

export default async function MonthlyCostSummary() {
  try {
    const cost = await getCostSummaryCached();
    const monthly = Math.round((cost.this_month?.cost_usd || 0) * USD_TO_JPY);
    const today = Math.round((cost.today?.cost_usd || 0) * USD_TO_JPY);
    return (
      <section aria-label="今月のコスト" className="mx-5 mt-4 card">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-slate-100">💰 今月のコスト</h2>
          <Link href="/history" className="text-xs text-accent hover:underline">
            詳細 →
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-bg-elev rounded p-2 text-center">
            <div className="text-[10px] text-slate-400 uppercase">今日</div>
            <div className="text-base font-bold tabular-nums">
              ¥{today.toLocaleString('ja-JP')}
            </div>
            <div className="text-[10px] text-slate-500">
              {cost.today?.calls || 0}回
            </div>
          </div>
          <div className="bg-accent/10 border border-accent/30 rounded p-2 text-center">
            <div className="text-[10px] text-slate-400 uppercase">今月</div>
            <div className="text-base font-bold tabular-nums text-accent">
              ¥{monthly.toLocaleString('ja-JP')}
            </div>
            <div className="text-[10px] text-slate-500">
              {cost.this_month?.calls || 0}回 / {cost.this_month?.images || 0}枚
            </div>
          </div>
        </div>
      </section>
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    return null;
  }
}
