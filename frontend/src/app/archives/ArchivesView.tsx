'use client';

import { useEffect, useMemo, useState } from 'react';
import type {
  ScenarioArchiveDetail,
  ScenarioArchiveItem,
  ScenarioArchivesResponse,
} from '@/lib/api';

function formatDate(mtime: number): string {
  try {
    return new Date(mtime * 1000).toLocaleString('ja-JP', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

function badgeForProvider(p: string | null | undefined): string {
  if (!p) return 'bg-slate-700 text-slate-300';
  const v = p.toLowerCase();
  if (v.includes('claude')) return 'bg-orange-500/20 text-orange-300 border border-orange-500/30';
  if (v.includes('gpt')) return 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
  return 'bg-slate-700 text-slate-300';
}

export default function ArchivesView({
  initial,
}: {
  initial: ScenarioArchivesResponse | null;
}) {
  const [data, setData] = useState<ScenarioArchivesResponse | null>(initial);
  const [channelId, setChannelId] = useState('');
  const [q, setQ] = useState('');
  const [competeOnly, setCompeteOnly] = useState(false);
  const [selected, setSelected] = useState<ScenarioArchiveItem | null>(null);
  const [detail, setDetail] = useState<ScenarioArchiveDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setErr(null);
    try {
      const qp = new URLSearchParams();
      if (channelId) qp.set('channel_id', channelId);
      if (q) qp.set('q', q);
      if (competeOnly) qp.set('has_compete', 'true');
      qp.set('limit', '300');
      const res = await fetch(`/api/scenario-archives?${qp}`, {
        cache: 'no-store',
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error || 'failed');
      setData(body as ScenarioArchivesResponse);
    } catch (e) {
      setErr((e as Error).message || 'failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId, q, competeOnly]);

  const loadDetail = async (item: ScenarioArchiveItem) => {
    setSelected(item);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await fetch(
        `/api/scenario-archives/${encodeURIComponent(item.channel_id)}/${encodeURIComponent(item.file)}`,
        { cache: 'no-store' }
      );
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error || 'failed');
      setDetail(body as ScenarioArchiveDetail);
    } catch (e) {
      setErr((e as Error).message || 'failed');
    } finally {
      setDetailLoading(false);
    }
  };

  const channels = data?.channels || [];
  const items = data?.items || [];

  const counts = useMemo(() => {
    let withCompete = 0;
    let gpt = 0;
    let claude = 0;
    items.forEach((it) => {
      if (it.has_compete) withCompete++;
      const winner = it.compete_summary?.winner_model;
      if (winner === 'gpt') gpt++;
      else if (winner === 'claude') claude++;
    });
    return { total: items.length, withCompete, gpt, claude };
  }, [items]);

  return (
    <div className="px-5">
      <div className="rounded-xl bg-bg-elev border border-border p-3 mb-3 text-xs text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
        <span>📁 {counts.total} 件</span>
        <span>🥊 比較あり: {counts.withCompete}</span>
        <span className="text-emerald-300">GPT 勝ち: {counts.gpt}</span>
        <span className="text-orange-300">Claude 勝ち: {counts.claude}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
        <select
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
          className="bg-bg-elev border border-border rounded-lg px-3 py-2 text-sm"
        >
          <option value="">全チャンネル</option>
          {channels.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="🔍 タイトル / テーマ検索"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="bg-bg-elev border border-border rounded-lg px-3 py-2 text-sm"
        />
        <div className="flex items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={competeOnly}
              onChange={(e) => setCompeteOnly(e.target.checked)}
            />
            GPT vs Claude 比較ありのみ
          </label>
          <button
            onClick={reload}
            className="ml-auto rounded-md bg-slate-700 hover:bg-slate-600 px-2 py-1"
            disabled={loading}
          >
            {loading ? '...' : '更新'}
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-2 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">
          ⚠️ {err}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="rounded-xl bg-bg-elev border border-border max-h-[70vh] overflow-y-auto">
          {items.length === 0 ? (
            <div className="p-4 text-sm text-slate-400">
              (一致するシナリオがありません)
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((it) => {
                const isSel =
                  selected?.channel_id === it.channel_id &&
                  selected?.file === it.file;
                return (
                  <li
                    key={`${it.channel_id}/${it.file}`}
                    onClick={() => loadDetail(it)}
                    className={`p-3 text-sm cursor-pointer hover:bg-slate-700/40 ${isSel ? 'bg-slate-700/60' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 text-xs">
                        {it.channel_id}
                      </span>
                      <span className="text-slate-500 text-xs">
                        · {formatDate(it.mtime)}
                      </span>
                      {it.compete_summary?.winner_model && (
                        <span
                          className={`ml-auto rounded-full px-2 py-[1px] text-[10px] ${badgeForProvider(it.compete_summary.winner_model)}`}
                        >
                          🥊 {it.compete_summary.winner_model}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 font-semibold truncate">
                      {it.title}
                    </div>
                    <div className="mt-1 text-xs text-slate-400 flex gap-3 flex-wrap">
                      <span>short: {it.short.count}行 / {it.short.chars}字</span>
                      <span>full: {it.full.count}行 / {it.full.chars}字</span>
                      <span>{it.style}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="rounded-xl bg-bg-elev border border-border p-3 max-h-[70vh] overflow-y-auto">
          {!selected ? (
            <div className="text-sm text-slate-400">
              ← 左の一覧から選択すると詳細が表示されます
            </div>
          ) : detailLoading ? (
            <div className="text-sm text-slate-400">読み込み中…</div>
          ) : !detail ? (
            <div className="text-sm text-slate-400">詳細を取得できませんでした</div>
          ) : (
            <DetailPane item={selected} detail={detail} />
          )}
        </div>
      </div>
    </div>
  );
}

function DetailPane({
  item,
  detail,
}: {
  item: ScenarioArchiveItem;
  detail: ScenarioArchiveDetail;
}) {
  const data = detail.data || {};
  const compete = (data.compete as any) || null;
  const blind = (compete?.blind_eval as any) || null;
  const mapping = blind?.mapping || null;
  const scores = (blind?.scores_by_label || blind?.scores || {}) as Record<
    string,
    Record<string, number>
  >;

  return (
    <div className="text-sm">
      <h2 className="text-lg font-bold mb-1">{data.title || item.title}</h2>
      <div className="text-xs text-slate-400 mb-2 font-mono break-all">
        {item.channel_id}/{item.file}
      </div>

      {data.theme && (
        <div className="mb-3 rounded-lg bg-bg border border-border p-2 text-xs">
          <div className="font-semibold text-slate-300">テーマ</div>
          <div>{(data.theme as any).title}</div>
          {(data.theme as any).angle && (
            <div className="text-slate-400">{(data.theme as any).angle}</div>
          )}
        </div>
      )}

      {compete && (
        <div className="mb-3 rounded-lg bg-orange-500/5 border border-orange-500/30 p-2 text-xs">
          <div className="font-semibold text-orange-300 mb-1">
            🥊 GPT vs Claude 比較
          </div>
          <div className="grid grid-cols-2 gap-2">
            {compete.candidates?.gpt && (
              <div className="rounded-md bg-bg p-2">
                <div className="font-semibold text-emerald-300">GPT</div>
                <div className="truncate">{compete.candidates.gpt.title}</div>
              </div>
            )}
            {compete.candidates?.claude && (
              <div className="rounded-md bg-bg p-2">
                <div className="font-semibold text-orange-300">Claude</div>
                <div className="truncate">{compete.candidates.claude.title}</div>
              </div>
            )}
          </div>
          {blind?.winner_model && (
            <div className="mt-2">
              ブラインド勝者:{' '}
              <span
                className={`rounded-full px-2 py-[1px] text-[10px] ${
                  blind.winner_model === 'claude'
                    ? 'bg-orange-500/20 text-orange-300'
                    : 'bg-emerald-500/20 text-emerald-300'
                }`}
              >
                {blind.winner_model}
              </span>
              {compete.selected_by && (
                <span className="ml-2 text-slate-400">
                  (採用根拠: {compete.selected_by})
                </span>
              )}
            </div>
          )}
          {mapping && (
            <div className="mt-1 text-slate-400">
              A→{mapping.A} / B→{mapping.B}
            </div>
          )}
          {scores && Object.keys(scores).length > 0 && (
            <table className="mt-2 w-full text-[11px]">
              <thead className="text-slate-400">
                <tr>
                  <th className="text-left">項目</th>
                  {Object.keys(scores).map((k) => (
                    <th key={k} className="text-right">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.keys((Object.values(scores)[0] as any) || {}).map(
                  (key) => (
                    <tr key={key}>
                      <td className="text-slate-300">{key}</td>
                      {Object.keys(scores).map((label) => (
                        <td key={label} className="text-right">
                          {scores[label]?.[key] ?? '-'}
                        </td>
                      ))}
                    </tr>
                  )
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      <details className="mb-3" open>
        <summary className="cursor-pointer text-slate-300 font-semibold">
          short_scenario ({item.short.count}行 / {item.short.chars}字)
        </summary>
        <ol className="mt-2 space-y-1 text-xs">
          {((data.short_scenario as any[]) || []).map((line, i) => (
            <li key={i} className="rounded-md bg-bg border border-border p-2">
              <div className="text-slate-400 text-[10px]">
                {line.speaker} · {line.expression || ''}
              </div>
              <div className="whitespace-pre-wrap">{line.text}</div>
            </li>
          ))}
        </ol>
      </details>

      <details className="mb-3">
        <summary className="cursor-pointer text-slate-300 font-semibold">
          full_scenario ({item.full.count}行 / {item.full.chars}字)
        </summary>
        <ol className="mt-2 space-y-1 text-xs">
          {((data.full_scenario as any[]) || []).map((line, i) => (
            <li key={i} className="rounded-md bg-bg border border-border p-2">
              <div className="text-slate-400 text-[10px]">
                {line.speaker} · {line.expression || ''}
              </div>
              <div className="whitespace-pre-wrap">{line.text}</div>
            </li>
          ))}
        </ol>
      </details>

      <details>
        <summary className="cursor-pointer text-slate-300 font-semibold">
          生 JSON
        </summary>
        <pre className="mt-2 text-[10px] font-mono text-slate-300 whitespace-pre-wrap break-words bg-black/50 p-2 rounded-md">
{JSON.stringify(data, null, 2)}
        </pre>
      </details>
    </div>
  );
}
