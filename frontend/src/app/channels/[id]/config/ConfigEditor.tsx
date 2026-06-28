'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColorField,
  Field,
  NumberField,
  Row,
  Section,
  Toggle,
} from '@/components/Field';
import AssetUploader from '@/components/AssetUploader';
import ChannelYoutubeConnect from '@/components/ChannelYoutubeConnect';
import ChannelTiktokConnect from '@/components/ChannelTiktokConnect';
import AutopilotSection from './AutopilotSection';
import ResearchEffectsSection from './ResearchEffectsSection';
import type { AssetEntry, AssetKind, Channel } from '@/lib/api';

type ConfigShape = Record<string, any>;

function getIn(obj: any, path: (string | number)[]): any {
  return path.reduce((acc, k) => (acc == null ? undefined : acc[k]), obj);
}

function setIn(obj: any, path: (string | number)[], value: any): any {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  const isArr = typeof head === 'number';
  const current = obj == null ? (isArr ? [] : {}) : obj;
  const nextChild = setIn(current[head as any], rest, value);
  if (isArr) {
    const arr = Array.isArray(current) ? [...current] : [];
    arr[head as number] = nextChild;
    return arr;
  }
  return { ...current, [head]: nextChild };
}

const SPEAKER_PRESETS: { id: number; name: string }[] = [
  { id: 2, name: '四国めたん' },
  { id: 3, name: 'ずんだもん' },
  { id: 8, name: '春日部つむぎ' },
  { id: 13, name: '青山龍星' },
  { id: 14, name: '冥鳴ひまり' },
  { id: 20, name: 'もち子' },
  { id: 30, name: '雨晴はう' },
];

const PERSONA_AGE_OPTIONS = ['', '10代', '20代', '30代', '40代+'];
const PERSONA_GENDER_OPTIONS = ['', '男性', '女性', '全般'];
const PERSONA_TONE_OPTIONS = ['', 'カジュアル', '丁寧', 'フランク', 'ゆるい'];
const PERSONA_DEPTH_OPTIONS = ['ライト', 'ミドル', 'ディープ'];
const PERSONA_INTEREST_PRESETS = [
  '科学',
  'エンタメ',
  '雑学',
  'テクノロジー',
  '日常',
  'ビジネス',
  '健康',
  '心理',
  '歴史',
  'お金',
];

export default function ConfigEditor({
  channelId,
  initialConfig,
  channels,
  initialAssets,
}: {
  channelId: string;
  initialConfig: ConfigShape;
  channels: Channel[];
  initialAssets: Record<string, AssetEntry[]>;
}) {
  const router = useRouter();
  const [cfg, setCfg] = useState<ConfigShape>(initialConfig);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const update = (path: (string | number)[], value: any) =>
    setCfg((prev) => setIn(prev, path, value));

  const characters = (cfg.characters || {}) as Record<string, any>;
  const characterNames = Object.keys(characters);

  // Phase 2 拡張フィールド
  const references: Array<{ type: string; url: string; label?: string }> =
    cfg.references || [];
  const prompts = cfg.prompts || {};
  const generationRules = cfg.generation_rules || {};

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      // 全フィールドを送る（バックエンドが部分更新としてマージ）
      const patch: ConfigShape = {
        name: cfg.name,
        concept: cfg.concept,
        style: cfg.style,
        youtube_channel_id: cfg.youtube_channel_id ?? null,
        characters: cfg.characters,
        thumbnail_template: cfg.thumbnail_template,
        defaults: cfg.defaults,
        content_policy: cfg.content_policy,
        theme_seeds: cfg.theme_seeds,
        video_format: cfg.video_format,
        references: cfg.references,
        prompts: cfg.prompts,
        generation_rules: cfg.generation_rules,
        image_mode: cfg.image_mode,
        image_collect: cfg.image_collect,
        publish_settings: cfg.publish_settings,
        tiktok: cfg.tiktok,
      };
      const res = await fetch(`/api/channels/${encodeURIComponent(channelId)}/config`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || '保存に失敗しました');
      }
      const data = await res.json();
      setCfg(data.config || cfg);
      setSavedMsg('✅ 設定を保存しました');
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    if (!confirm(`チャンネル "${cfg.name}" を削除しますか？関連アセットも削除されます。`)) {
      return;
    }
    setDeleting(true);
    try {
      const res = await fetch(`/api/channels/${encodeURIComponent(channelId)}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(await res.text());
      router.push('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed');
      setDeleting(false);
    }
  };

  return (
    <div className="px-5 space-y-3">
      {/* チャンネル切替タブ */}
      <nav
        aria-label="チャンネル切替"
        className="flex gap-2 overflow-x-auto -mx-1 px-1 pb-2"
      >
        {channels.map((c) => (
          <Link
            key={c.id}
            href={`/channels/${encodeURIComponent(c.id)}/config`}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-sm border ${
              c.id === channelId
                ? 'bg-accent text-white border-accent'
                : 'bg-bg-elev text-slate-300 border-border hover:bg-slate-700'
            }`}
          >
            {c.name}
          </Link>
        ))}
      </nav>

      {/* 0. YouTube 連携 */}
      <Section title="🔌 YouTube 連携" defaultOpen>
        <ChannelYoutubeConnect channelId={channelId} />
      </Section>

      {/* 0.1 TikTok 連携 */}
      <Section title="📱 TikTok 連携">
        <ChannelTiktokConnect channelId={channelId} />

        <div className="mt-4 pt-4 border-t border-border/50 space-y-4">
          <p className="text-xs text-slate-400">
            自動投稿の投稿先と TikTok 投稿の挙動を設定します（保存ボタンで反映）。
          </p>

          <Field label="自動投稿の投稿先">
            <select
              value={(() => {
                const t: string[] =
                  cfg.publish_settings?.publish_targets ?? ['youtube'];
                const hasYt = t.includes('youtube');
                const hasTt = t.includes('tiktok');
                if (hasYt && hasTt) return 'both';
                if (hasTt) return 'tiktok';
                return 'youtube';
              })()}
              onChange={(e) => {
                const v = e.target.value;
                const targets =
                  v === 'both'
                    ? ['youtube', 'tiktok']
                    : v === 'tiktok'
                    ? ['tiktok']
                    : ['youtube'];
                update(['publish_settings', 'publish_targets'], targets);
              }}
              className="input"
            >
              <option value="youtube">YouTube のみ</option>
              <option value="both">YouTube + TikTok 同時投稿</option>
              <option value="tiktok">TikTok のみ</option>
            </select>
          </Field>

          <Toggle
            checked={cfg.tiktok?.enabled ?? false}
            onChange={(b) => update(['tiktok', 'enabled'], b)}
            label="TikTok 自動投稿を有効化"
            description="投稿先に TikTok を含めた場合に、生成完了時へ自動でショートを投稿します"
          />

          <Field label="TikTok 公開範囲 (privacy_level)">
            <select
              value={cfg.tiktok?.privacy_level ?? 'SELF_ONLY'}
              onChange={(e) =>
                update(['tiktok', 'privacy_level'], e.target.value)
              }
              className="input"
            >
              <option value="SELF_ONLY">非公開 (SELF_ONLY) — 未審査アプリ必須</option>
              <option value="MUTUAL_FOLLOW_FRIENDS">相互フォロー</option>
              <option value="FOLLOWER_OF_CREATOR">フォロワー</option>
              <option value="PUBLIC_TO_EVERYONE">全員に公開 — 審査通過後のみ</option>
            </select>
          </Field>

          <Field label="追加ハッシュタグ（カンマ区切り）">
            <input
              type="text"
              value={(cfg.tiktok?.extra_hashtags ?? []).join(', ')}
              onChange={(e) =>
                update(
                  ['tiktok', 'extra_hashtags'],
                  e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                )
              }
              className="input"
              placeholder="#fyp, #おすすめ"
            />
          </Field>

          <Row>
            <Toggle
              checked={cfg.tiktok?.disable_comment ?? false}
              onChange={(b) => update(['tiktok', 'disable_comment'], b)}
              label="コメント無効"
            />
            <Toggle
              checked={cfg.tiktok?.disable_duet ?? false}
              onChange={(b) => update(['tiktok', 'disable_duet'], b)}
              label="デュエット無効"
            />
            <Toggle
              checked={cfg.tiktok?.disable_stitch ?? false}
              onChange={(b) => update(['tiktok', 'disable_stitch'], b)}
              label="ステッチ無効"
            />
          </Row>
        </div>
      </Section>

      {/* 0.5 フルオート自動投稿 */}
      <AutopilotSection channelId={channelId} />

      {/* 1. 基本情報 */}
      <Section title="📝 基本情報" defaultOpen>
        <Field label="チャンネル名">
          <input
            type="text"
            value={cfg.name || ''}
            onChange={(e) => update(['name'], e.target.value)}
            className="input"
          />
        </Field>
        <Field label="コンセプト">
          <textarea
            value={cfg.concept || ''}
            onChange={(e) => update(['concept'], e.target.value)}
            className="input min-h-[60px]"
          />
        </Field>
        <Row>
          <Field label="スタイル">
            <select
              value={cfg.style || 'yukkuri'}
              onChange={(e) => update(['style'], e.target.value)}
              className="input"
            >
              <option value="yukkuri">ゆっくり（2人）</option>
              <option value="monologue">モノローグ（1人）</option>
            </select>
          </Field>
          <Field label="YouTube チャンネルID" hint="UC...（Phase 3 で連携）">
            <input
              type="text"
              value={cfg.youtube_channel_id || ''}
              onChange={(e) => update(['youtube_channel_id'], e.target.value || null)}
              className="input"
              placeholder="UCxxx..."
            />
          </Field>
        </Row>
      </Section>

      {/* 1.5 ペルソナ（ターゲット視聴者） */}
      <Section
        title="🎯 ターゲット視聴者ペルソナ"
        description="シナリオ生成時にプロンプトへ注入され、口調・例え・解説の深さが自動で切り替わる"
      >
        {(() => {
          const persona = (getIn(cfg, ['video_format', 'persona']) || {}) as {
            age_group?: string;
            gender?: string;
            interest_categories?: string[];
            tone_style?: string;
            content_depth?: string;
            custom_notes?: string;
          };
          const interests: string[] = Array.isArray(persona.interest_categories)
            ? persona.interest_categories
            : [];
          const toggleInterest = (label: string) => {
            const next = interests.includes(label)
              ? interests.filter((x) => x !== label)
              : [...interests, label];
            update(['video_format', 'persona', 'interest_categories'], next);
          };
          const allChips = Array.from(
            new Set([...PERSONA_INTEREST_PRESETS, ...interests])
          );
          return (
            <>
              <Row>
                <Field label="年齢層">
                  <select
                    value={persona.age_group || ''}
                    onChange={(e) =>
                      update(['video_format', 'persona', 'age_group'], e.target.value)
                    }
                    className="input"
                  >
                    {PERSONA_AGE_OPTIONS.map((v) => (
                      <option key={v || 'unset'} value={v}>
                        {v || '指定なし'}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="性別傾向">
                  <select
                    value={persona.gender || ''}
                    onChange={(e) =>
                      update(['video_format', 'persona', 'gender'], e.target.value)
                    }
                    className="input"
                  >
                    {PERSONA_GENDER_OPTIONS.map((v) => (
                      <option key={v || 'unset'} value={v}>
                        {v || '指定なし'}
                      </option>
                    ))}
                  </select>
                </Field>
              </Row>

              <Field
                label="興味カテゴリ"
                hint="クリックでオン/オフ。複数選択可"
              >
                <div className="flex flex-wrap gap-2">
                  {allChips.map((label) => {
                    const active = interests.includes(label);
                    return (
                      <button
                        key={label}
                        type="button"
                        onClick={() => toggleInterest(label)}
                        className={`px-3 py-1 rounded-full text-xs border transition ${
                          active
                            ? 'bg-accent text-white border-accent'
                            : 'bg-bg-elev text-slate-300 border-border hover:bg-slate-700'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </Field>

              <Row>
                <Field label="口調スタイル">
                  <select
                    value={persona.tone_style || ''}
                    onChange={(e) =>
                      update(['video_format', 'persona', 'tone_style'], e.target.value)
                    }
                    className="input"
                  >
                    {PERSONA_TONE_OPTIONS.map((v) => (
                      <option key={v || 'unset'} value={v}>
                        {v || '指定なし'}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field
                  label="コンテンツ深さ"
                  hint="ライト=雑学中心 / ミドル=データ織り交ぜ / ディープ=専門用語OK"
                >
                  <div className="flex gap-1 rounded-xl bg-bg-elev border border-border p-1">
                    {PERSONA_DEPTH_OPTIONS.map((v) => {
                      const active = persona.content_depth === v;
                      return (
                        <button
                          key={v}
                          type="button"
                          onClick={() =>
                            update(
                              ['video_format', 'persona', 'content_depth'],
                              active ? '' : v
                            )
                          }
                          className={`flex-1 px-2 py-1.5 rounded-lg text-xs transition ${
                            active
                              ? 'bg-accent text-white'
                              : 'text-slate-300 hover:bg-slate-700'
                          }`}
                        >
                          {v}
                        </button>
                      );
                    })}
                  </div>
                </Field>
              </Row>

              <Field
                label="カスタムメモ"
                hint="例: 「結論を冒頭で言い切る」「数字は必ず %形式」など、追加で守らせたい指示"
              >
                <textarea
                  value={persona.custom_notes || ''}
                  onChange={(e) =>
                    update(['video_format', 'persona', 'custom_notes'], e.target.value)
                  }
                  className="input min-h-[80px] text-xs"
                  placeholder="(任意)"
                />
              </Field>
            </>
          );
        })()}
      </Section>

      {/* 2. キャラクター */}
      <Section title="🎭 キャラクター設定">
        {characterNames.length === 0 && (
          <p className="text-xs text-slate-500">まだキャラクターが登録されていません</p>
        )}

        {characterNames.map((charName) => {
          const ch = characters[charName] || {};
          const renameChar = (newName: string) => {
            if (!newName || newName === charName || characters[newName]) return;
            const next = { ...characters };
            next[newName] = next[charName];
            delete next[charName];
            update(['characters'], next);
          };
          const removeChar = () => {
            if (!confirm(`${charName} を削除しますか？`)) return;
            const next = { ...characters };
            delete next[charName];
            update(['characters'], next);
          };
          return (
            <div
              key={charName}
              className="rounded-xl bg-bg-elev/60 border border-border p-3 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <input
                  type="text"
                  defaultValue={charName}
                  onBlur={(e) => renameChar(e.target.value.trim())}
                  className="input flex-1 font-bold"
                  aria-label="キャラクター名"
                />
                <button
                  type="button"
                  onClick={removeChar}
                  className="text-xs text-red-400 hover:text-red-300 px-2"
                >
                  🗑️
                </button>
              </div>
              <Row>
                <Field label="サイド">
                  <select
                    value={ch.side || 'left'}
                    onChange={(e) =>
                      update(['characters', charName, 'side'], e.target.value)
                    }
                    className="input"
                  >
                    <option value="left">左</option>
                    <option value="right">右</option>
                    <option value="center">中央</option>
                  </select>
                </Field>
                <Field label="VOICEVOX Speaker ID">
                  <select
                    value={Number(ch.speaker_id ?? 13)}
                    onChange={(e) =>
                      update(
                        ['characters', charName, 'speaker_id'],
                        Number(e.target.value)
                      )
                    }
                    className="input"
                  >
                    {SPEAKER_PRESETS.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id} — {s.name}
                      </option>
                    ))}
                    {!SPEAKER_PRESETS.find((s) => s.id === Number(ch.speaker_id)) && (
                      <option value={Number(ch.speaker_id)}>
                        {Number(ch.speaker_id)}（カスタム）
                      </option>
                    )}
                  </select>
                </Field>
              </Row>
              <Field label="字幕カラー">
                <ColorField
                  value={
                    Array.isArray(ch.text_color)
                      ? (ch.text_color.slice(0, 3) as [number, number, number])
                      : [255, 255, 255]
                  }
                  onChange={(c) =>
                    update(['characters', charName, 'text_color'], c)
                  }
                />
              </Field>
              <Field label="役割">
                <input
                  type="text"
                  value={ch.role || ''}
                  onChange={(e) =>
                    update(['characters', charName, 'role'], e.target.value)
                  }
                  className="input"
                  placeholder="例: 解説役"
                />
              </Field>
              <Field
                label="DALL-E プロンプト用 appearance"
                hint="イラスト生成時にこのキャラを描く際のプロンプト"
              >
                <textarea
                  value={ch.appearance || ''}
                  onChange={(e) =>
                    update(['characters', charName, 'appearance'], e.target.value)
                  }
                  className="input min-h-[80px] text-xs"
                />
              </Field>
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => {
            let i = characterNames.length + 1;
            let n = `キャラ${i}`;
            while (characters[n]) {
              i += 1;
              n = `キャラ${i}`;
            }
            update(['characters', n], {
              side: 'left',
              speaker_id: 13,
              text_color: [255, 255, 255],
              role: '',
              appearance: '',
            });
          }}
          className="btn-secondary w-full"
        >
          ＋ キャラクター追加
        </button>
      </Section>

      {/* 3. 画像素材 */}
      <Section title="🖼️ 画像素材">
        <AssetUploader
          channelId={channelId}
          kind="background"
          initial={initialAssets.background || []}
          label="背景画像"
        />
        <AssetUploader
          channelId={channelId}
          kind="character"
          initial={initialAssets.character || []}
          label="キャラ立ち絵"
        />
        <AssetUploader
          channelId={channelId}
          kind="reference"
          initial={initialAssets.reference || []}
          label="参考画像"
          hint="DALL-E に与えるスタイル参考用"
        />
        <AssetUploader
          channelId={channelId}
          kind="thumbnail"
          initial={initialAssets.thumbnail || []}
          label="サムネイル素材"
        />
      </Section>

      {/* 4. ビジュアル設定 */}
      <Section title="🎨 ビジュアル設定">
        <Row>
          <Field
            label="字幕ボックス不透明度 (0-255)"
            hint={`現在: ${getIn(cfg, ['video_format', 'layout', 'text_box_opacity']) ?? 180}`}
          >
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'text_box_opacity']) ?? 180)}
              onChange={(n) => update(['video_format', 'layout', 'text_box_opacity'], n)}
              min={0}
              max={255}
            />
          </Field>
          <Field
            label="非発話側の透明度 (0.0-1.0)"
            hint="0=非表示, 1=完全表示"
          >
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'nonspeaker_opacity']) ?? 0.5)}
              onChange={(n) => update(['video_format', 'layout', 'nonspeaker_opacity'], n)}
              min={0}
              max={1}
              step={0.05}
            />
          </Field>
        </Row>
        <Field label="キャラ Y オフセット (px)">
          <NumberField
            value={Number(getIn(cfg, ['video_format', 'layout', 'char_y_offset']) ?? 130)}
            onChange={(n) => update(['video_format', 'layout', 'char_y_offset'], n)}
          />
        </Field>
        <Field
          label="ショート解説カードの作画方法"
          hint="pillow=ローカル図解で生成（APIコスト0・推奨） / dalle=ChatGPT(DALL-E)でAI生成（失敗時はpillowへ自動フォールバック）"
        >
          <select
            value={
              getIn(cfg, ['video_format', 'short_illustrations', 'illustration_method']) ||
              'pillow'
            }
            onChange={(e) =>
              update(['video_format', 'short_illustrations', 'illustration_method'], e.target.value)
            }
            className="input"
          >
            <option value="pillow">pillow（ローカル図解・コスト0）</option>
            <option value="dalle">dalle（ChatGPT/DALL-E でAI生成）</option>
          </select>
        </Field>
        <Field label="DALL-E スタイル">
          <select
            value={getIn(cfg, ['video_format', 'illustration_style', 'style']) || 'vivid'}
            onChange={(e) =>
              update(['video_format', 'illustration_style', 'style'], e.target.value)
            }
            className="input"
          >
            <option value="vivid">vivid（ビビッド）</option>
            <option value="natural">natural（ナチュラル）</option>
          </select>
        </Field>
        <Field label="DALL-E サイズ">
          <select
            value={getIn(cfg, ['video_format', 'illustration_style', 'size']) || '1792x1024'}
            onChange={(e) =>
              update(['video_format', 'illustration_style', 'size'], e.target.value)
            }
            className="input"
          >
            <option value="1024x1024">1024×1024（正方形）</option>
            <option value="1792x1024">1792×1024（横長）</option>
            <option value="1024x1792">1024×1792（縦長）</option>
          </select>
        </Field>
        <Field label="DALL-E アートスタイル（プロンプト断片）">
          <textarea
            value={getIn(cfg, ['video_format', 'illustration_style', 'art_style']) || ''}
            onChange={(e) =>
              update(['video_format', 'illustration_style', 'art_style'], e.target.value)
            }
            className="input min-h-[80px] text-xs"
            placeholder="例: colorful hand-drawn cartoon illustration ..."
          />
        </Field>
        <Field
          label="画像取得モード"
          hint="generate=AI生成 / collect=Web画像収集（出典表示） / mix=シーンごとに自動選択"
        >
          <select
            value={getIn(cfg, ['image_mode']) || 'generate'}
            onChange={(e) => update(['image_mode'], e.target.value)}
            className="input"
          >
            <option value="generate">generate（AI生成のみ）</option>
            <option value="collect">collect（Web収集＋出典表示）</option>
            <option value="mix">mix（シーンに応じて自動）</option>
          </select>
        </Field>
        {(getIn(cfg, ['image_mode']) || 'generate') !== 'generate' && (
          <>
            <Field
              label="画像検索プロバイダ"
              hint="auto=APIキーが設定されたものを順に使う"
            >
              <select
                value={getIn(cfg, ['image_collect', 'provider']) || 'auto'}
                onChange={(e) => update(['image_collect', 'provider'], e.target.value)}
                className="input"
              >
                <option value="auto">auto</option>
                <option value="pixabay">Pixabay</option>
                <option value="unsplash">Unsplash</option>
                <option value="google_cse">Google Custom Search</option>
              </select>
            </Field>
            <Field label="出典表示テンプレ">
              <input
                type="text"
                value={
                  getIn(cfg, ['image_collect', 'attribution_template']) || '出典: {source}'
                }
                onChange={(e) =>
                  update(['image_collect', 'attribution_template'], e.target.value)
                }
                className="input"
                placeholder="出典: {source}"
              />
            </Field>
            {(getIn(cfg, ['image_mode']) || 'generate') === 'mix' && (
              <Field label="mix 判定ストラテジ">
                <select
                  value={getIn(cfg, ['image_collect', 'mix_strategy']) || 'heuristic'}
                  onChange={(e) =>
                    update(['image_collect', 'mix_strategy'], e.target.value)
                  }
                  className="input"
                >
                  <option value="heuristic">heuristic（自動）</option>
                  <option value="always_collect">always_collect</option>
                  <option value="always_generate">always_generate</option>
                </select>
              </Field>
            )}
          </>
        )}
      </Section>

      {/* 5. BGM/SE */}
      <Section title="🎵 BGM / SE">
        <Row>
          <Field
            label="BGM 音量 (0.0-1.0)"
            hint={`現在: ${getIn(cfg, ['video_format', 'audio', 'bgm_volume']) ?? 0.30}`}
          >
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'audio', 'bgm_volume']) ?? 0.30)}
              onChange={(n) => update(['video_format', 'audio', 'bgm_volume'], n)}
              min={0}
              max={1}
              step={0.05}
            />
          </Field>
          <Field label="SE 音量 (0.0-1.0)">
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'audio', 'se_volume']) ?? 0.5)}
              onChange={(n) => update(['video_format', 'audio', 'se_volume'], n)}
              min={0}
              max={1}
              step={0.05}
            />
          </Field>
        </Row>
        <AssetUploader
          channelId={channelId}
          kind="bgm"
          initial={initialAssets.bgm || []}
          label="BGM 音源"
        />
        <AssetUploader
          channelId={channelId}
          kind="se"
          initial={initialAssets.se || []}
          label="SE 音源"
        />
      </Section>

      {/* 6. 字幕 */}
      <Section title="💬 字幕レンダリング">
        <Row>
          <Field label="フォント">
            <select
              value={getIn(cfg, ['video_format', 'layout', 'text_font_family']) || 'system-ui'}
              onChange={(e) =>
                update(['video_format', 'layout', 'text_font_family'], e.target.value)
              }
              className="input"
            >
              <option value="system-ui">system-ui</option>
              <option value="Hiragino Sans">ヒラギノ角ゴ</option>
              <option value="Noto Sans JP">Noto Sans JP</option>
              <option value="Yu Gothic">游ゴシック</option>
              <option value="Meiryo">メイリオ</option>
            </select>
          </Field>
          <Field label="文字サイズ (px)">
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'text_font_size']) ?? 42)}
              onChange={(n) => update(['video_format', 'layout', 'text_font_size'], n)}
            />
          </Field>
        </Row>
        <Row>
          <Field label="アウトライン色">
            <ColorField
              value={
                (getIn(cfg, ['video_format', 'colors', 'text_stroke_color']) || [0, 0, 0]).slice(
                  0,
                  3
                ) as [number, number, number]
              }
              onChange={(c) =>
                update(['video_format', 'colors', 'text_stroke_color'], c)
              }
            />
          </Field>
          <Field label="アウトライン太さ (px)">
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'text_stroke_width']) ?? 3)}
              onChange={(n) => update(['video_format', 'layout', 'text_stroke_width'], n)}
            />
          </Field>
        </Row>
        <Field label="字幕の縦位置">
          <select
            value={getIn(cfg, ['video_format', 'layout', 'text_position']) || 'bottom'}
            onChange={(e) =>
              update(['video_format', 'layout', 'text_position'], e.target.value)
            }
            className="input"
          >
            <option value="bottom">下</option>
            <option value="middle">中央</option>
            <option value="top">上</option>
          </select>
        </Field>
      </Section>

      {/* 7. エンコード */}
      <Section title="🎞️ エンコード設定">
        <Row>
          <Field label="解像度（横）">
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'width']) ?? 1920)}
              onChange={(n) => update(['video_format', 'layout', 'width'], n)}
            />
          </Field>
          <Field label="解像度（縦）">
            <NumberField
              value={Number(getIn(cfg, ['video_format', 'layout', 'height']) ?? 1080)}
              onChange={(n) => update(['video_format', 'layout', 'height'], n)}
            />
          </Field>
        </Row>
        <Row>
          <Field label="FPS">
            <select
              value={Number(getIn(cfg, ['video_format', 'layout', 'fps']) ?? 24)}
              onChange={(e) =>
                update(['video_format', 'layout', 'fps'], Number(e.target.value))
              }
              className="input"
            >
              <option value={24}>24</option>
              <option value={30}>30</option>
              <option value={60}>60</option>
            </select>
          </Field>
          <Field label="ビットレート" hint="例: 8M, 12M">
            <input
              type="text"
              value={getIn(cfg, ['video_format', 'layout', 'bitrate']) || '8M'}
              onChange={(e) =>
                update(['video_format', 'layout', 'bitrate'], e.target.value)
              }
              className="input"
            />
          </Field>
        </Row>
      </Section>

      {/* 7.5 競合演出リサーチ */}
      <ResearchEffectsSection channelId={channelId} />

      {/* 8. OP/ED/トランジション */}
      <Section title="🎬 OP / ED / トランジション">
        <AssetUploader
          channelId={channelId}
          kind="intro"
          initial={initialAssets.intro || []}
          label="OP 動画"
        />
        <AssetUploader
          channelId={channelId}
          kind="outro"
          initial={initialAssets.outro || []}
          label="ED 動画"
        />
        <Row>
          <Field label="トランジション種類">
            <select
              value={getIn(cfg, ['defaults', 'transition_type']) || 'fade'}
              onChange={(e) =>
                update(['defaults', 'transition_type'], e.target.value)
              }
              className="input"
            >
              <option value="none">なし</option>
              <option value="fade">フェード</option>
              <option value="slide">スライド</option>
              <option value="zoom">ズーム</option>
            </select>
          </Field>
          <Field label="トランジション時間 (秒)">
            <NumberField
              value={Number(getIn(cfg, ['defaults', 'transition_duration']) ?? 0.5)}
              onChange={(n) => update(['defaults', 'transition_duration'], n)}
              min={0}
              max={5}
              step={0.1}
              unit="秒"
            />
          </Field>
        </Row>
      </Section>

      {/* 9. 参考リンク */}
      <Section title="🔗 参考チャンネル / 動画">
        {references.length === 0 && (
          <p className="text-xs text-slate-500">まだ登録がありません</p>
        )}
        {references.map((r, i) => (
          <div
            key={i}
            className="rounded-lg bg-bg-elev border border-border p-3 space-y-2"
          >
            <Row>
              <Field label="種類">
                <select
                  value={r.type || 'video'}
                  onChange={(e) =>
                    update(['references', i, 'type'], e.target.value)
                  }
                  className="input"
                >
                  <option value="channel">チャンネル</option>
                  <option value="video">動画</option>
                </select>
              </Field>
              <Field label="ラベル">
                <input
                  type="text"
                  value={r.label || ''}
                  onChange={(e) =>
                    update(['references', i, 'label'], e.target.value)
                  }
                  className="input"
                />
              </Field>
            </Row>
            <Field label="URL">
              <input
                type="url"
                value={r.url || ''}
                onChange={(e) =>
                  update(['references', i, 'url'], e.target.value)
                }
                className="input"
                placeholder="https://youtube.com/..."
              />
            </Field>
            <button
              type="button"
              onClick={() =>
                update(
                  ['references'],
                  references.filter((_, j) => j !== i)
                )
              }
              className="text-xs text-red-400 hover:text-red-300"
            >
              🗑️ 削除
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            update(['references'], [...references, { type: 'video', url: '', label: '' }])
          }
          className="btn-secondary w-full"
        >
          ＋ 参考リンクを追加
        </button>
      </Section>

      {/* 10. プロンプト設定 */}
      <Section title="🤖 プロンプト設定">
        <Field
          label="シナリオ生成プロンプト"
          hint="変数: {theme}, {duration_min}, {channel_name}, {style}"
        >
          <textarea
            value={prompts.scenario || ''}
            onChange={(e) => update(['prompts', 'scenario'], e.target.value)}
            className="input min-h-[120px] text-xs font-mono"
            placeholder="例: あなたは {channel_name} のシナリオライターです。{theme} について {duration_min} 分の動画シナリオを作成してください..."
          />
        </Field>
        <Field
          label="DALL-E イラスト生成プロンプト"
          hint="変数: {scene_description}, {character_appearance}, {art_style}"
        >
          <textarea
            value={prompts.illustration || ''}
            onChange={(e) => update(['prompts', 'illustration'], e.target.value)}
            className="input min-h-[100px] text-xs font-mono"
            placeholder="例: {art_style}, scene: {scene_description}, characters: {character_appearance}"
          />
        </Field>
        <Field
          label="サムネイル生成プロンプト"
          hint="変数: {title}, {hook}, {bg_tone}"
        >
          <textarea
            value={prompts.thumbnail || ''}
            onChange={(e) => update(['prompts', 'thumbnail'], e.target.value)}
            className="input min-h-[100px] text-xs font-mono"
          />
        </Field>
      </Section>

      {/* 11. 生成ルール */}
      <Section title="📐 生成ルール">
        <Row>
          <Field label="メイン尺 (秒)">
            <NumberField
              value={Number(getIn(cfg, ['defaults', 'target_duration']) ?? 720)}
              onChange={(n) => update(['defaults', 'target_duration'], n)}
              min={60}
              unit="秒"
            />
          </Field>
          <Field label="ショート尺 (秒)">
            <NumberField
              value={Number(getIn(cfg, ['defaults', 'short_duration']) ?? 30)}
              onChange={(n) => update(['defaults', 'short_duration'], n)}
              min={5}
              max={60}
              unit="秒"
            />
          </Field>
        </Row>
        <Row>
          <Field label="セクション数">
            <NumberField
              value={Number(generationRules.sections ?? 4)}
              onChange={(n) => update(['generation_rules', 'sections'], n)}
              min={1}
              max={20}
            />
          </Field>
          <Field label="話速">
            <NumberField
              value={Number(getIn(cfg, ['defaults', 'speed']) ?? 1.3)}
              onChange={(n) => update(['defaults', 'speed'], n)}
              min={0.5}
              max={2.0}
              step={0.05}
              unit="倍"
            />
          </Field>
        </Row>
        <Row>
          <Field label="行幅 最小 (文字)">
            <NumberField
              value={Number(generationRules.line_width_min ?? 15)}
              onChange={(n) => update(['generation_rules', 'line_width_min'], n)}
              min={5}
              max={60}
            />
          </Field>
          <Field label="行幅 最大 (文字)">
            <NumberField
              value={Number(generationRules.line_width_max ?? 30)}
              onChange={(n) => update(['generation_rules', 'line_width_max'], n)}
              min={10}
              max={80}
            />
          </Field>
        </Row>
        <Toggle
          checked={Boolean(getIn(cfg, ['defaults', 'use_illustrations']) ?? true)}
          onChange={(b) => update(['defaults', 'use_illustrations'], b)}
          label="DALL-E イラストを生成"
        />
      </Section>

      {/* 12. 危険ゾーン */}
      <Section title="⚠️ 危険ゾーン">
        <p className="text-xs text-slate-400">
          このチャンネルを完全に削除します。アップロードしたアセットも一緒に削除されます。
        </p>
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          className="btn w-full bg-red-600 hover:bg-red-700 text-white"
        >
          {deleting ? '削除中…' : 'チャンネルを削除'}
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
        <button type="button" onClick={onSave} disabled={saving} className="btn-primary w-full">
          {saving ? '保存中…' : '💾 設定を保存'}
        </button>
      </div>
    </div>
  );
}
