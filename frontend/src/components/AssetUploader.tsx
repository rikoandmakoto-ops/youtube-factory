'use client';

import { useRef, useState } from 'react';
import type { AssetEntry, AssetKind } from '@/lib/api';

const ACCEPTS: Record<AssetKind, string> = {
  background: 'image/*',
  character: 'image/*',
  reference: 'image/*',
  thumbnail: 'image/*',
  bgm: 'audio/*',
  se: 'audio/*',
  intro: 'video/*',
  outro: 'video/*',
};

function formatSize(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function isImageKind(k: AssetKind) {
  return ['background', 'character', 'reference', 'thumbnail'].includes(k);
}

function isAudioKind(k: AssetKind) {
  return k === 'bgm' || k === 'se';
}

function isVideoKind(k: AssetKind) {
  return k === 'intro' || k === 'outro';
}

function previewUrl(channelId: string, kind: AssetKind, filename: string) {
  return `/api/channels/${encodeURIComponent(channelId)}/assets/${encodeURIComponent(
    kind
  )}/${encodeURIComponent(filename)}`;
}

export default function AssetUploader({
  channelId,
  kind,
  initial,
  label,
  hint,
}: {
  channelId: string;
  kind: AssetKind;
  initial: AssetEntry[];
  label: string;
  hint?: string;
}) {
  const [items, setItems] = useState<AssetEntry[]>(initial);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = async (files: FileList | File[]) => {
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.set('kind', kind);
        fd.set('file', file, file.name);
        const res = await fetch(
          `/api/channels/${encodeURIComponent(channelId)}/upload`,
          {
            method: 'POST',
            body: fd,
          }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || `${file.name}: アップロード失敗`);
        }
        const data: AssetEntry = await res.json();
        setItems((prev) => {
          const without = prev.filter((p) => p.filename !== data.filename);
          return [...without, data];
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const remove = async (filename: string) => {
    if (!confirm(`${filename} を削除しますか？`)) return;
    setError(null);
    const res = await fetch(
      `/api/channels/${encodeURIComponent(channelId)}/assets/${encodeURIComponent(
        kind
      )}/${encodeURIComponent(filename)}`,
      { method: 'DELETE' }
    );
    if (!res.ok) {
      setError('削除に失敗しました');
      return;
    }
    setItems((prev) => prev.filter((p) => p.filename !== filename));
  };

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="block text-sm text-slate-300 font-semibold">{label}</span>
        <span className="text-xs text-slate-500">{items.length} 件</span>
      </div>
      {hint && <p className="text-xs text-slate-500 mb-2">{hint}</p>}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length > 0) upload(e.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed px-4 py-6 text-center cursor-pointer transition ${
          dragOver
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elev/40 text-slate-400 hover:bg-bg-elev/70'
        }`}
        onClick={() => inputRef.current?.click()}
        role="button"
        aria-label={`${label} をアップロード`}
      >
        {uploading ? (
          <p className="text-sm">アップロード中…</p>
        ) : (
          <>
            <p className="text-sm">タップしてファイル選択 or ドラッグ＆ドロップ</p>
            <p className="text-[10px] mt-1 opacity-70">最大 100MB</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTS[kind]}
          multiple
          className="hidden"
          onChange={(e) => e.target.files && upload(e.target.files)}
        />
      </div>

      {error && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 mt-2"
        >
          {error}
        </p>
      )}

      {items.length > 0 && (
        <ul className="mt-3 grid grid-cols-2 gap-2">
          {items.map((it) => (
            <li
              key={it.filename}
              className="rounded-lg bg-bg-elev border border-border overflow-hidden"
            >
              {isImageKind(kind) && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={previewUrl(channelId, kind, it.filename)}
                  alt={it.filename}
                  className="w-full aspect-video object-cover bg-black"
                />
              )}
              {isAudioKind(kind) && (
                <audio
                  src={previewUrl(channelId, kind, it.filename)}
                  controls
                  preload="none"
                  className="w-full"
                />
              )}
              {isVideoKind(kind) && (
                <video
                  src={previewUrl(channelId, kind, it.filename)}
                  controls
                  preload="metadata"
                  className="w-full aspect-video bg-black"
                />
              )}
              <div className="p-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs truncate" title={it.filename}>
                    {it.filename}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {formatSize(it.size_bytes)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => remove(it.filename)}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
                  aria-label={`${it.filename} を削除`}
                >
                  🗑️
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
