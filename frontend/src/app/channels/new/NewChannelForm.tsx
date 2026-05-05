'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Field, Toggle } from '@/components/Field';
import type { Channel, IllustrationStyle, SampleIllustrationResponse } from '@/lib/api';

const ID_RE = /^[a-z0-9][a-z0-9-]*$/;

const FRAME_STYLES = [
  { v: 'none', label: 'なし' },
  { v: 'wooden', label: '木枠' },
  { v: 'blackboard', label: '黒板' },
  { v: 'whiteboard', label: 'ホワイトボード' },
  { v: 'comic-red-border', label: 'コミック赤枠' },
] as const;

const DEFAULT_ART_STYLE =
  'colorful hand-drawn educational illustration in a slightly more refined, ' +
  'textbook-diagram-leaning manga style. Confident clean outlines, flat-color ' +
  'shading with subtle gradients, friendly but textbook-clear.';
const DEFAULT_BACKGROUND =
  'soft pastel cream background with subtle decorative shapes';
const DEFAULT_EXTRA_PROMPT =
  'Use neat Japanese labels with pointer lines, arrows, and small icons to ' +
  'explain cause→effect — like a friendly science textbook figure.';
const DEFAULT_SAMPLE_TOPIC =
  '朝起きると身長が少し伸びている：椎間板が水分を吸って膨らむ仕組みを示す解剖図';

type StepId = 1 | 2 | 3 | 4;

const STEPS: { id: StepId; label: string }[] = [
  { id: 1, label: '基本情報' },
  { id: 2, label: '画像スタイル' },
  { id: 3, label: 'サンプル確認' },
  { id: 4, label: '確定・保存' },
];

export default function NewChannelForm({
  templates,
}: {
  templates: Channel[];
}) {
  const router = useRouter();
  const [step, setStep] = useState<StepId>(1);

  // Step 1
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [concept, setConcept] = useState('');
  const [style, setStyle] = useState<'yukkuri' | 'monologue'>('yukkuri');
  const [template, setTemplate] = useState<string>('');
  const [hashtags, setHashtags] = useState('');

  // Step 2 — illustration_style
  const [artStyle, setArtStyle] = useState(DEFAULT_ART_STYLE);
  const [background, setBackground] = useState(DEFAULT_BACKGROUND);
  const [frameStyle, setFrameStyle] = useState<string>('comic-red-border');
  const [allowTextLabels, setAllowTextLabels] = useState(true);
  const [allowFrame, setAllowFrame] = useState(true);
  const [extraPrompt, setExtraPrompt] = useState(DEFAULT_EXTRA_PROMPT);
  const [dalleStyle, setDalleStyle] = useState<'vivid' | 'natural'>('vivid');
  const [format, setFormat] = useState<'landscape' | 'square' | 'portrait'>(
    'landscape'
  );
  const [sampleTopic, setSampleTopic] = useState(DEFAULT_SAMPLE_TOPIC);

  // Step 3
  const [sample, setSample] = useState<SampleIllustrationResponse | null>(null);
  const [sampling, setSampling] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [sampleApproved, setSampleApproved] = useState(false);

  // Step 4
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const idValid = ID_RE.test(id) && id.length >= 2;
  const step1Valid = idValid && name.trim().length > 0;
  const step2Valid = artStyle.trim().length > 0;
  const canSubmit = step1Valid && step2Valid && sampleApproved && !submitting;

  const hashtagList = useMemo(
    () =>
      hashtags
        .split(/[\s,、]+/g)
        .filter(Boolean)
        .map((t) => (t.startsWith('#') ? t : `#${t}`)),
    [hashtags]
  );

  const illustStyle: IllustrationStyle = useMemo(
    () => ({
      style: dalleStyle,
      format,
      art_style: artStyle.trim(),
      background: background.trim(),
      frame_style: frameStyle,
      include_characters: false, // ウィザード時点ではキャラ未設定なので OFF
      allow_text_labels: allowTextLabels,
      allow_frame: allowFrame,
      extra_prompt: extraPrompt.trim(),
    }),
    [
      dalleStyle,
      format,
      artStyle,
      background,
      frameStyle,
      allowTextLabels,
      allowFrame,
      extraPrompt,
    ]
  );

  const onGenerateSample = async () => {
    if (sampling) return;
    setSampleError(null);
    setSampleApproved(false);
    setSampling(true);
    try {
      const prevId = sample?.sample_id;
      const res = await fetch('/api/illustrations/sample', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          topic: sampleTopic.trim() || DEFAULT_SAMPLE_TOPIC,
          illust_style: illustStyle,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'サンプル生成に失敗しました');
      }
      const data: SampleIllustrationResponse = await res.json();
      setSample(data);
      if (prevId && prevId !== data.sample_id) {
        fetch(`/api/illustrations/sample/${encodeURIComponent(prevId)}`, {
          method: 'DELETE',
        }).catch(() => {});
      }
    } catch (e) {
      setSampleError(e instanceof Error ? e.message : 'サンプル生成に失敗しました');
    } finally {
      setSampling(false);
    }
  };

  const onCreate = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload: Record<string, unknown> = {
        id,
        name: name.trim(),
        concept: concept.trim(),
        style,
        video_format: {
          illustration_style: {
            style: illustStyle.style,
            format: illustStyle.format,
            art_style: illustStyle.art_style,
            background: illustStyle.background,
            frame_style: illustStyle.frame_style,
            include_characters: true, // 動画生成時はキャラを描き込む（プロフィール更新後）
            allow_text_labels: illustStyle.allow_text_labels,
            allow_frame: illustStyle.allow_frame,
            extra_prompt: illustStyle.extra_prompt,
          },
        },
      };
      if (template) payload.template = template;
      if (hashtagList.length > 0) {
        payload.defaults = { hashtags: hashtagList };
      }
      const res = await fetch('/api/channels', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || '作成に失敗しました');
      }
      // 確定したサンプルは GC に任せる（24h で消える）
      router.push(`/channels/${encodeURIComponent(id)}/config`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'failed');
    } finally {
      setSubmitting(false);
    }
  };

  const goNext = () => {
    if (step === 1 && step1Valid) setStep(2);
    else if (step === 2 && step2Valid) setStep(3);
    else if (step === 3 && sampleApproved) setStep(4);
  };
  const goBack = () => {
    if (step > 1) setStep((step - 1) as StepId);
  };

  return (
    <div className="px-5 space-y-4">
      <ol
        aria-label="ステップ"
        className="grid grid-cols-4 gap-1 text-[10px] font-semibold"
      >
        {STEPS.map((s) => {
          const isPast = s.id < step;
          const isCurrent = s.id === step;
          return (
            <li
              key={s.id}
              className={`text-center py-2 px-1 rounded ${
                isCurrent
                  ? 'bg-accent text-white'
                  : isPast
                  ? 'bg-emerald-700/60 text-white'
                  : 'bg-bg-elev text-slate-500'
              }`}
              aria-current={isCurrent ? 'step' : undefined}
            >
              {s.id}. {s.label}
            </li>
          );
        })}
      </ol>

      {step === 1 && (
        <section className="card space-y-4">
          <h2 className="font-bold text-slate-100">Step 1: 基本情報</h2>
          <Field
            label="チャンネルID"
            hint="小文字英数字とハイフンのみ。後から変更できません"
          >
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value.toLowerCase())}
              className="input"
              placeholder="例: tech-lab"
              autoCapitalize="none"
              required
              pattern="[a-z0-9][a-z0-9\-]*"
              minLength={2}
              maxLength={64}
            />
            {id && !idValid && (
              <p className="text-xs text-red-400 mt-1">
                小文字英数字とハイフンのみ、2文字以上
              </p>
            )}
          </Field>

          <Field label="チャンネル名">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
              placeholder="例: テクノロジー研究所"
              required
              maxLength={120}
            />
          </Field>

          <Field label="チャンネル説明（コンセプト）">
            <textarea
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              className="input min-h-[80px]"
              placeholder="どんな動画を作るチャンネル？"
              maxLength={500}
            />
          </Field>

          <Field label="動画スタイル">
            <div role="radiogroup" className="grid grid-cols-2 gap-2">
              {(['yukkuri', 'monologue'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={style === s}
                  onClick={() => setStyle(s)}
                  className={`btn py-3 text-sm ${
                    style === s
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-300 border border-border'
                  }`}
                >
                  {s === 'yukkuri' ? 'ゆっくり（2人）' : 'モノローグ（1人）'}
                </button>
              ))}
            </div>
          </Field>

          <Field
            label="ハッシュタグ"
            hint="スペースまたはカンマで区切り。# は省略可"
          >
            <input
              type="text"
              value={hashtags}
              onChange={(e) => setHashtags(e.target.value)}
              className="input"
              placeholder="科学 雑学 解説"
            />
            {hashtagList.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {hashtagList.map((h) => (
                  <span
                    key={h}
                    className="badge bg-bg-elev text-slate-300 border border-border"
                  >
                    {h}
                  </span>
                ))}
              </div>
            )}
          </Field>

          <Field
            label="既存チャンネルをベースにする（任意）"
            hint="選んだチャンネルの設定をコピーしてから上書きします"
          >
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className="input"
            >
              <option value="">空白から作成</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.id})
                </option>
              ))}
            </select>
          </Field>
        </section>
      )}

      {step === 2 && (
        <section className="card space-y-4">
          <h2 className="font-bold text-slate-100">Step 2: 画像スタイル</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            DALL-E 3 に渡すスタイルプロンプトを設定します。
            次のステップで実際にサンプルを1枚生成して確認できます。
          </p>

          <Field label="DALL-E スタイル">
            <div className="grid grid-cols-2 gap-2">
              {(['vivid', 'natural'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setDalleStyle(v)}
                  className={`btn py-2 text-sm ${
                    dalleStyle === v
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-300 border border-border'
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </Field>

          <Field label="画像のフォーマット">
            <div className="grid grid-cols-3 gap-2">
              {(['landscape', 'square', 'portrait'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setFormat(v)}
                  className={`btn py-2 text-xs ${
                    format === v
                      ? 'bg-accent text-white'
                      : 'bg-bg-elev text-slate-300 border border-border'
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </Field>

          <Field
            label="アートスタイル"
            hint="絵柄・線・色味の方向性を英語で記述"
          >
            <textarea
              value={artStyle}
              onChange={(e) => setArtStyle(e.target.value)}
              className="input min-h-[120px] text-xs"
            />
          </Field>

          <Field label="背景の指定">
            <textarea
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              className="input min-h-[60px] text-xs"
            />
          </Field>

          <Field label="フレームスタイル">
            <select
              value={frameStyle}
              onChange={(e) => setFrameStyle(e.target.value)}
              className="input"
            >
              {FRAME_STYLES.map((f) => (
                <option key={f.v} value={f.v}>
                  {f.label}
                </option>
              ))}
            </select>
          </Field>

          <div className="space-y-2">
            <Toggle
              checked={allowTextLabels}
              onChange={setAllowTextLabels}
              label="日本語ラベル・矢印を許可"
              description="教科書風の図解で「水分吸収」「膨張」などのラベルを描いてOK"
            />
            <Toggle
              checked={allowFrame}
              onChange={setAllowFrame}
              label="赤枠などのコミック風フレームを許可"
              description="OFF だと DALL-E に「枠なし」を強制します"
            />
          </div>

          <Field
            label="追加プロンプト（任意）"
            hint="表情の指示や擬人化のトーンなど、独自要素をここに"
          >
            <textarea
              value={extraPrompt}
              onChange={(e) => setExtraPrompt(e.target.value)}
              className="input min-h-[80px] text-xs"
            />
          </Field>

          <Field
            label="サンプル用トピック"
            hint="サンプル画像の題材。チャンネルの典型的な解説テーマを入れる"
          >
            <textarea
              value={sampleTopic}
              onChange={(e) => setSampleTopic(e.target.value)}
              className="input min-h-[60px] text-xs"
            />
          </Field>
        </section>
      )}

      {step === 3 && (
        <section className="card space-y-4">
          <h2 className="font-bold text-slate-100">Step 3: サンプル確認</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            設定したプロンプトで DALL-E にサンプルを1枚生成します。
            意図通りの仕上がりなら「OK」を、違っていたら Step 2 に戻って調整するか、再生成してください。
          </p>

          {!sample && !sampling && (
            <button
              type="button"
              onClick={onGenerateSample}
              className="btn-secondary w-full"
            >
              ✨ サンプルを生成
            </button>
          )}

          {sampling && (
            <div className="text-xs text-slate-400 text-center py-6">
              DALL-E でサンプル生成中… (10〜20秒)
            </div>
          )}

          {sample && !sampling && (
            <div className="space-y-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={sample.url}
                alt="サンプルイラスト"
                className="w-full rounded-lg border border-border bg-bg-elev"
              />
              <details className="text-xs text-slate-500">
                <summary className="cursor-pointer">
                  DALL-E に送ったプロンプトを表示
                </summary>
                <pre className="mt-2 p-2 bg-bg rounded border border-border whitespace-pre-wrap text-[10px]">
                  {sample.prompt}
                </pre>
              </details>
              {!sampleApproved ? (
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={onGenerateSample}
                    className="btn bg-bg-elev text-slate-200 border border-border py-3"
                  >
                    🔁 再生成
                  </button>
                  <button
                    type="button"
                    onClick={() => setSampleApproved(true)}
                    className="btn bg-emerald-600 hover:bg-emerald-700 text-white py-3"
                  >
                    ✅ OK この画像で進む
                  </button>
                </div>
              ) : (
                <p className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
                  ✓ サンプル承認済み。Step 4 で確定してください
                </p>
              )}
            </div>
          )}

          {sampleError && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              ⚠️ {sampleError}
            </p>
          )}
        </section>
      )}

      {step === 4 && (
        <section className="card space-y-4">
          <h2 className="font-bold text-slate-100">Step 4: 確定・保存</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            内容を確認してチャンネルを作成します。後から「チャンネル設定」画面で詳細を編集できます。
          </p>

          {sample && (
            <div>
              <div className="text-xs text-slate-400 mb-1">承認済みサンプル</div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={sample.url}
                alt="承認済みサンプル"
                className="w-full rounded-lg border border-emerald-700/50"
              />
            </div>
          )}

          <pre className="text-[10px] bg-bg whitespace-pre-wrap break-all p-2 rounded border border-border text-slate-300 overflow-auto max-h-72">
            {JSON.stringify(
              {
                id,
                name,
                concept,
                style,
                template: template || null,
                hashtags: hashtagList,
                illustration_style: illustStyle,
              },
              null,
              2
            )}
          </pre>

          {submitError && (
            <p
              role="alert"
              className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2"
            >
              {submitError}
            </p>
          )}

          <button
            type="button"
            onClick={onCreate}
            disabled={!canSubmit}
            className="btn-primary w-full"
          >
            {submitting ? '作成中…' : '✨ チャンネルを作成'}
          </button>
        </section>
      )}

      <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-bg/95 backdrop-blur border-t border-border flex gap-2">
        <button
          type="button"
          onClick={goBack}
          disabled={step === 1}
          className="btn bg-bg-elev text-slate-200 border border-border flex-1 py-3 disabled:opacity-40"
        >
          ← 戻る
        </button>
        {step < 4 && (
          <button
            type="button"
            onClick={goNext}
            disabled={
              (step === 1 && !step1Valid) ||
              (step === 2 && !step2Valid) ||
              (step === 3 && !sampleApproved)
            }
            className="btn-primary flex-1"
          >
            次へ →
          </button>
        )}
      </div>
    </div>
  );
}
