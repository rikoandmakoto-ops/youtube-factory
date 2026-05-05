'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Section, Field, Toggle } from '@/components/Field';
import YoutubeConnect from '@/components/YoutubeConnect';
import NotificationsSection from '@/components/NotificationsSection';
import type { Settings } from '@/lib/api';

export default function SettingsForm({ initial }: { initial: Settings }) {
  const router = useRouter();
  const [openaiKey, setOpenaiKey] = useState('');
  const [voicevoxUrl, setVoicevoxUrl] = useState(initial.voicevox_url);
  const [outputDir, setOutputDir] = useState(initial.output_dir);
  const [icloudSync, setIcloudSync] = useState(initial.icloud_sync);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // パスワード変更
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwResult, setPwResult] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      const patch: Record<string, unknown> = {
        voicevox_url: voicevoxUrl,
        output_dir: outputDir,
        icloud_sync: icloudSync,
      };
      if (openaiKey.trim()) patch.openai_api_key = openaiKey.trim();
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSavedMsg(`✅ 保存しました (${data.updated.join(', ')})`);
      setOpenaiKey('');
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  const onChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwSaving(true);
    setPwError(null);
    setPwResult(null);
    try {
      const res = await fetch('/api/auth/password', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'パスワード変更に失敗しました');
      }
      const data = await res.json();
      setPwResult(data.new_password_hash);
      setCurrentPw('');
      setNewPw('');
    } catch (e) {
      setPwError(e instanceof Error ? e.message : 'failed');
    } finally {
      setPwSaving(false);
    }
  };

  return (
    <form onSubmit={onSave} className="px-5 space-y-3">
      <Section title="🔌 YouTube API 連携" defaultOpen>
        <YoutubeConnect />
      </Section>

      <Section title="🔑 API キー" defaultOpen>
        <Field
          label="OpenAI API キー"
          hint={
            initial.openai.configured
              ? `現在: ${initial.openai.preview}（変更したい場合のみ入力）`
              : 'シナリオ生成・DALL-E に必要'
          }
        >
          <input
            type="password"
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
            placeholder={initial.openai.configured ? '変更しない場合は空欄のまま' : 'sk-...'}
            className="input"
            autoComplete="off"
          />
        </Field>
      </Section>

      <Section title="🖥️ システム" defaultOpen>
        <Field label="VOICEVOX URL" hint="例: http://localhost:50021">
          <input
            type="text"
            value={voicevoxUrl}
            onChange={(e) => setVoicevoxUrl(e.target.value)}
            className="input"
            inputMode="url"
          />
        </Field>
        <Field label="出力ディレクトリ" hint="完成動画の保存先">
          <input
            type="text"
            value={outputDir}
            onChange={(e) => setOutputDir(e.target.value)}
            className="input"
          />
        </Field>
        <Toggle
          checked={icloudSync}
          onChange={setIcloudSync}
          label="iCloud Drive にコピー"
          description="完成後、iCloud に動画をコピーして iPhone で確認可能に"
        />
      </Section>

      <NotificationsSection />

      <Section title="🔐 パスワード変更">
        <Field label="現在のパスワード">
          <input
            type="password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            className="input"
            autoComplete="current-password"
          />
        </Field>
        <Field label="新しいパスワード（4文字以上）">
          <input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            className="input"
            autoComplete="new-password"
            minLength={4}
          />
        </Field>
        <button
          type="button"
          onClick={onChangePassword}
          disabled={pwSaving || !currentPw || newPw.length < 4}
          className="btn-secondary w-full"
        >
          {pwSaving ? '生成中…' : '新しいハッシュを生成'}
        </button>
        {pwError && (
          <p
            role="alert"
            className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
          >
            {pwError}
          </p>
        )}
        {pwResult && (
          <div className="bg-emerald-900/20 border border-emerald-700/40 rounded-lg p-3 space-y-2">
            <p className="text-xs text-emerald-300">
              ✅ ハッシュを生成しました。<code>backend/.env</code> の{' '}
              <code>APP_PASSWORD_HASH</code> をこの値に置き換えてサーバを再起動してください。
            </p>
            <pre className="text-[10px] bg-bg whitespace-pre-wrap break-all p-2 rounded border border-border text-slate-300">
              {`APP_PASSWORD_HASH='${pwResult}'`}
            </pre>
          </div>
        )}
      </Section>

      <Section title="🚪 ログアウト">
        <p className="text-xs text-slate-500">
          セッション Cookie をクリアしてログイン画面に戻ります。
        </p>
        <button
          type="button"
          onClick={async () => {
            await fetch('/api/auth/logout', { method: 'POST' });
            router.push('/login');
            router.refresh();
          }}
          className="btn-secondary w-full"
        >
          ログアウト
        </button>
      </Section>

      {error && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {error}
        </p>
      )}
      {savedMsg && (
        <p className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {savedMsg}
        </p>
      )}

      <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-bg/95 backdrop-blur border-t border-border">
        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? '保存中…' : '💾 設定を保存'}
        </button>
      </div>
    </form>
  );
}
