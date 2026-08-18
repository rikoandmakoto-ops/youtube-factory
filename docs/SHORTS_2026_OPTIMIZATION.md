# ショート最適化 2026（冒頭3秒・尺・テンポ・クリフハンガー）

_実装: 2026-08-18 / 対象: ショート運用の全チャンネル（daily-science / scp-lab / 2ch-matome / company-facts / pokemon-lab / yokai-watch）_
_対象外: akashic-librarian（長尺・手動台本）、clip-lab（切り抜き別系統）_

2026 年の YouTube ショート・アルゴリズム調査に基づく改善をパイプラインへ反映した。
狙いは **冒頭3秒の離脱を止める → 完視聴率を上げる → チャンネル回遊で登録に繋げる** の一本道。

---

## 1. 冒頭3秒フックの強化

| 実装 | 場所 |
|---|---|
| 全生成経路で共有する「冒頭3秒ルール」 | `backend/pipeline/auto_scenario/generator.py` の `_HOOK_3SEC_RULE` |
| 4型のフック（これ知ってた？ / 実は〇〇 / 〇〇した結果 / 違和感の問い） | 同上 |
| チャンネル別の 1 行目フック例 | 各 `data/channels/*.json` の `voice_style.opening_hooks` |

- 1 行目は **15〜30 字・断定・答えを言わない**。挨拶／自己紹介／テーマ紹介は 1 文字でも不合格。
- チャンネル固有の `short_format` で 1 行目の書式を指定している場合（2ch まとめのスレタイ型）は
  そちらが優先され、その書式のまま「問い or 驚き」を作らせる。

### 画面中央の 10 文字テロップ（`hook_caption`）

- シナリオ生成が `thumb_info.hook_caption`（全角 10 文字以内）を出力する（`_HOOK_CAPTION_RULE`）。
- `generate_all` → `generate_short_video` → `ShortFrameRenderer` へ渡り、
  **冒頭 0〜3 秒の画面中央に特大テロップ**として焼き込まれる（`_draw_hook_caption`）。
- 記号除去と 10 文字への切り詰めは `_sanitize_hook_caption` が保険で行う。空なら従来どおりテロップ無し。
- チャンネル別の見た目は `defaults.short_overlay_style.hook_caption` で上書き可能:

```json
"hook_caption": { "accent_color": [210, 25, 25], "band_alpha": 195, "y_center": 1000 }
```

---

## 2. 動画構成の最適化

- **尺**: ショート既定を 6 行 → **7 行 / 総 220〜290 字 ≒ 30〜40 秒**（30〜45 秒が最も伸びる。25 秒未満は禁止）。
  - 構成: 3秒フック → 追い打ち → 事実① → 理由/事実② → 意外な展開 → オチ → CTA。
  - 1 行を 24〜36 字に短くしたのは、**テロップの切替を 3〜4 秒ごと**に起こすため。
- **1.5〜2 秒ごとの視覚変化**: `video_effects` に `beat_zoom` を追加。
  1 行の中で `beat_interval`（既定 1.8 秒）ごとに寄り → 引きを繰り返し、疑似的なカット割りを作る。
  ショート経路（`decide_effect_plan(..., is_short=True)`）でのみ付与し、
  従来の `zoom_in` とは二重掛けしない（リサイズ 1 回分のままでレンダー時間を抑える）。
  - チャンネル別チューニング: `video_format.effects` の
    `short_beat_zoom`(bool) / `beat_interval`(秒) / `beat_zoom_max`(寄り量)。
- **クリフハンガー**: `content_policy.cliffhanger` を宣言したチャンネルだけ、
  オチで**核心の 6 割だけ**明かし、残りを「まだ語られていない謎」として CTA に接続する。

```json
"cliffhanger": { "enabled": true, "wording": "この続きはチャンネルの他の動画で" }
```

  - 有効: daily-science / scp-lab / pokemon-lab / yokai-watch
  - 無効: 2ch まとめ（お題型でオチを断定しない）、企業のホンネ（ファクト列挙型）
- **シリーズ化**: `theme_priority.series_lineup` に連作名を並べると、
  テーマ提案（`_theme_priority_block`）とシナリオ生成（`_series_hint_block`）の両方で使われ、
  最終行の CTA が必ずシリーズ名に触れる。シナリオは `series_name` を出力する。

---

## 3. チャンネル別

| チャンネル | 主な変更 |
|---|---|
| daily-science | 「これ知ってた？」型フック、体の謎／食べ物の科学などシリーズ6本、クリフハンガー有効 |
| scp-lab | ホラー演出強化（暗転 170・パンチイン強め・赤テロップ・glitch/pixelate 解禁・beat 1.6 秒）、「このSCP、実は…」型クリフハンガー |
| 2ch-matome | 6→7 行（ボケ 4 連）、軽い下ネタ・きわどいネタを冒頭最優先、共感→笑いの順、スレタイは答えを伏せる |
| company-facts | 1 画面目のナレーションを「問い or 驚き」で開始、時事ネタ連動カテゴリを最優先に追加、1 画面 4〜6 秒 |
| pokemon-lab | 対決・種族値のギャップ型フック、5 行目の反転を必須化、クリフハンガー有効 |
| yokai-watch | 「可愛い見た目 → 原典の残酷さ」のギャップ設計、伝承原典シリーズ、クリフハンガー有効 |

---

## 4. タイトル / サムネ

- タイトルは「説明」ではなく **「衝動」**（`_title_rule_block` の共通ルール）。
  「〜について」「〜とは」「〜を解説」を禁止し、実は/なぜ/だけ/本当は/知らない/やめて/ヤバい/99% を必ず 1 つ入れる。
- サムネ文字 `thumb_info.hook_lines` は **2 行 × 各 8 文字以内**に統一。

---

## 5. 反映方法（重要）

稼働中の backend はチャンネル JSON もコードもメモリに保持するため、**backend を再起動しないと反映されない**。

```
launchctl kickstart -k gui/$(id -u)/com.youtube-factory.agent   # agent
# backend 本体はデプロイ手順に従って再起動
```
