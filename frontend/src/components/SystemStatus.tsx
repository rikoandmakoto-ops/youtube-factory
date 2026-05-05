import type { SystemStatus } from '@/lib/api';

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block w-2 h-2 rounded-full ${
        ok ? 'bg-emerald-400' : 'bg-red-400'
      }`}
    />
  );
}

export default function SystemStatusGrid({
  status,
}: {
  status: SystemStatus | null;
}) {
  return (
    <section
      aria-label="システムステータス"
      className="grid grid-cols-3 gap-2 px-5"
    >
      <div className="card text-center py-3">
        <div className="flex items-center justify-center gap-1.5 text-xs font-semibold">
          <StatusDot ok={!!status?.voicevox.connected} />
          VOICEVOX
        </div>
        <div className="text-xs text-slate-400 mt-1">
          {status === null
            ? '…'
            : status.voicevox.connected
            ? 'オンライン'
            : 'オフライン'}
        </div>
      </div>

      <div className="card text-center py-3">
        <div className="flex items-center justify-center gap-1.5 text-xs font-semibold">
          <StatusDot ok={!!status?.gpt.connected} />
          GPT
        </div>
        <div className="text-xs text-slate-400 mt-1">
          {status === null
            ? '…'
            : status.gpt.connected
            ? '接続OK'
            : status.gpt.configured
            ? '接続失敗'
            : 'キー未設定'}
        </div>
      </div>

      <div className="card text-center py-3">
        <div className="flex items-center justify-center gap-1.5 text-xs font-semibold">
          <StatusDot ok={!!status && status.disk.free_gb > 5} />
          ディスク
        </div>
        <div className="text-xs text-slate-400 mt-1">
          {status === null
            ? '…'
            : `${Math.round(status.disk.free_gb)}GB空き`}
        </div>
      </div>
    </section>
  );
}
