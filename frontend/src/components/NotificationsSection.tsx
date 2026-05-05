'use client';

import { useEffect, useState } from 'react';
import { Section, Field, Toggle } from '@/components/Field';
import type { NotificationSettings } from '@/lib/api';

export default function NotificationsSection() {
  const [data, setData] = useState<NotificationSettings | null>(null);
  const [lineToken, setLineToken] = useState('');
  const [slackUrl, setSlackUrl] = useState('');
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState<number>(587);
  const [smtpUser, setSmtpUser] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [smtpFrom, setSmtpFrom] = useState('');
  const [smtpTo, setSmtpTo] = useState('');
  const [onGenerate, setOnGenerate] = useState(true);
  const [onUpload, setOnUpload] = useState(true);
  const [onSchedule, setOnSchedule] = useState(true);
  const [onError, setOnError] = useState(true);

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/settings/notifications', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: NotificationSettings) => {
        setData(d);
        setSmtpHost(d.smtp_host || '');
        setSmtpPort(d.smtp_port || 587);
        setSmtpUser(d.smtp_user || '');
        setSmtpFrom(d.smtp_from || '');
        setSmtpTo(d.smtp_to || '');
        setOnGenerate(d.notify_on_generate_done);
        setOnUpload(d.notify_on_upload_done);
        setOnSchedule(d.notify_on_schedule_run);
        setOnError(d.notify_on_error);
      })
      .catch(() => {});
  }, []);

  const onSave = async () => {
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const payload: Record<string, unknown> = {
        smtp_host: smtpHost,
        smtp_port: smtpPort,
        smtp_user: smtpUser,
        smtp_from: smtpFrom,
        smtp_to: smtpTo,
        notify_on_generate_done: onGenerate,
        notify_on_upload_done: onUpload,
        notify_on_schedule_run: onSchedule,
        notify_on_error: onError,
      };
      if (lineToken.trim()) payload.line_token = lineToken.trim();
      if (slackUrl.trim()) payload.slack_webhook_url = slackUrl.trim();
      if (smtpPassword.trim()) payload.smtp_password = smtpPassword.trim();

      const res = await fetch('/api/settings/notifications', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      setMsg('✅ 通知設定を保存しました');
      setLineToken('');
      setSlackUrl('');
      setSmtpPassword('');
      // 再取得
      const r2 = await fetch('/api/settings/notifications', { cache: 'no-store' });
      if (r2.ok) setData(await r2.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失敗');
    } finally {
      setSaving(false);
    }
  };

  const onTest = async (channel?: 'line' | 'slack' | 'email') => {
    setTesting(channel || 'all');
    setMsg(null);
    setErr(null);
    try {
      const res = await fetch('/api/notifications/test', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ channel: channel || null }),
      });
      const d = await res.json();
      if (!res.ok) {
        throw new Error(d.error || `テスト失敗 (${res.status})`);
      }
      const okCount = (d.results || []).filter((r: any) => r.ok).length;
      const total = (d.results || []).length;
      setMsg(`📨 テスト送信: ${okCount}/${total} 成功`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'テスト失敗');
    } finally {
      setTesting(null);
    }
  };

  return (
    <Section title="🔔 通知設定" description="生成完了・スケジュール実行・エラー時に通知">
      <Field
        label="LINE Notify トークン"
        hint={
          data?.line_token_set
            ? `現在: ${data.line_token_preview}（変更したい場合のみ入力）`
            : 'https://notify-bot.line.me/ で取得'
        }
      >
        <div className="flex gap-2">
          <input
            type="password"
            value={lineToken}
            onChange={(e) => setLineToken(e.target.value)}
            placeholder={data?.line_token_set ? '変更しない場合は空欄' : 'LINE Notify トークン'}
            className="input flex-1"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => onTest('line')}
            disabled={testing === 'line' || !data?.line_token_set}
            className="btn-secondary text-xs px-3"
          >
            {testing === 'line' ? '…' : 'テスト'}
          </button>
        </div>
      </Field>

      <Field
        label="Slack Webhook URL"
        hint={
          data?.slack_webhook_set
            ? `現在: ${data.slack_webhook_preview}（変更したい場合のみ入力）`
            : 'Slack の incoming webhook URL'
        }
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={slackUrl}
            onChange={(e) => setSlackUrl(e.target.value)}
            placeholder={data?.slack_webhook_set ? '変更しない場合は空欄' : 'https://hooks.slack.com/...'}
            className="input flex-1"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => onTest('slack')}
            disabled={testing === 'slack' || !data?.slack_webhook_set}
            className="btn-secondary text-xs px-3"
          >
            {testing === 'slack' ? '…' : 'テスト'}
          </button>
        </div>
      </Field>

      <details className="bg-bg-elev/40 rounded-lg p-3">
        <summary className="text-sm font-semibold text-slate-300 cursor-pointer">
          📧 SMTPメール（クリックで開く）
        </summary>
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Field label="SMTPホスト">
              <input
                type="text"
                value={smtpHost}
                onChange={(e) => setSmtpHost(e.target.value)}
                placeholder="smtp.gmail.com"
                className="input"
              />
            </Field>
            <Field label="ポート">
              <input
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(Number(e.target.value) || 587)}
                placeholder="587"
                className="input"
              />
            </Field>
          </div>
          <Field label="ユーザー名">
            <input
              type="text"
              value={smtpUser}
              onChange={(e) => setSmtpUser(e.target.value)}
              className="input"
              autoComplete="off"
            />
          </Field>
          <Field
            label="パスワード"
            hint={data?.smtp_password_set ? '保存済み（変更しない場合は空欄）' : ''}
          >
            <input
              type="password"
              value={smtpPassword}
              onChange={(e) => setSmtpPassword(e.target.value)}
              className="input"
              autoComplete="off"
            />
          </Field>
          <Field label="差出人 (From)">
            <input
              type="email"
              value={smtpFrom}
              onChange={(e) => setSmtpFrom(e.target.value)}
              placeholder="factory@example.com"
              className="input"
            />
          </Field>
          <Field label="宛先 (To)">
            <div className="flex gap-2">
              <input
                type="email"
                value={smtpTo}
                onChange={(e) => setSmtpTo(e.target.value)}
                placeholder="me@example.com"
                className="input flex-1"
              />
              <button
                type="button"
                onClick={() => onTest('email')}
                disabled={testing === 'email' || !data?.smtp_host}
                className="btn-secondary text-xs px-3"
              >
                {testing === 'email' ? '…' : 'テスト'}
              </button>
            </div>
          </Field>
        </div>
      </details>

      <div className="space-y-2 border-t border-border pt-3">
        <h4 className="text-sm font-semibold text-slate-300">通知タイミング</h4>
        <Toggle checked={onGenerate} onChange={setOnGenerate} label="生成完了" />
        <Toggle checked={onUpload} onChange={setOnUpload} label="アップロード完了" />
        <Toggle checked={onSchedule} onChange={setOnSchedule} label="スケジュール実行" />
        <Toggle checked={onError} onChange={setOnError} label="エラー発生" />
      </div>

      {msg && (
        <p className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {msg}
        </p>
      )}
      {err && (
        <p
          role="alert"
          className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
        >
          {err}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="btn-primary flex-1"
        >
          {saving ? '保存中…' : '💾 通知設定を保存'}
        </button>
        <button
          type="button"
          onClick={() => onTest()}
          disabled={!!testing || !data?.configured}
          className="btn-secondary text-xs px-3"
        >
          {testing === 'all' ? '送信中…' : '📨 全部にテスト送信'}
        </button>
      </div>
    </Section>
  );
}
