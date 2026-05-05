import type { DayPoint } from '@/lib/api';

/**
 * 過去28日の再生数バーチャート（SVG inline）。recharts などは入れず軽量に。
 */
export default function ViewsChart({
  data,
  height = 120,
}: {
  data: DayPoint[];
  height?: number;
}) {
  if (!data || data.length === 0) {
    return (
      <div className="text-xs text-slate-500 text-center py-6">
        データがありません
      </div>
    );
  }

  const W = 320;
  const H = height;
  const pad = { l: 28, r: 8, t: 8, b: 18 };
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;

  const maxV = Math.max(1, ...data.map((d) => d.views));
  const barW = innerW / data.length;
  const barGap = Math.min(2, barW * 0.2);

  const yTicks = [0, Math.round(maxV / 2), maxV];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label="再生数推移チャート"
    >
      {/* y軸目盛 */}
      {yTicks.map((v) => {
        const y = pad.t + innerH - (v / maxV) * innerH;
        return (
          <g key={v}>
            <line
              x1={pad.l}
              x2={W - pad.r}
              y1={y}
              y2={y}
              stroke="#334155"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text
              x={pad.l - 4}
              y={y + 3}
              textAnchor="end"
              fontSize="9"
              fill="#64748b"
            >
              {v >= 1000 ? `${(v / 1000).toFixed(1)}K` : v}
            </text>
          </g>
        );
      })}

      {/* バー */}
      {data.map((d, i) => {
        const h = (d.views / maxV) * innerH;
        const x = pad.l + i * barW + barGap / 2;
        const y = pad.t + innerH - h;
        return (
          <g key={d.date}>
            <rect
              x={x}
              y={y}
              width={Math.max(1, barW - barGap)}
              height={Math.max(1, h)}
              fill="url(#bar-grad)"
              rx={1}
            >
              <title>{`${d.date}: ${d.views.toLocaleString()} 再生`}</title>
            </rect>
          </g>
        );
      })}

      {/* x軸ラベル（最初・中央・最終） */}
      {[0, Math.floor(data.length / 2), data.length - 1].map((i) => (
        <text
          key={i}
          x={pad.l + i * barW + barW / 2}
          y={H - 4}
          textAnchor="middle"
          fontSize="9"
          fill="#64748b"
        >
          {data[i]?.date.slice(5)}
        </text>
      ))}

      <defs>
        <linearGradient id="bar-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
    </svg>
  );
}
