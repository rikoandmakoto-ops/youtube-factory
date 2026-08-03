# ファクトオーバーレイ形式（style="facts_overlay"）

「企業のホンネ」(`company-facts`) 向けの縦型ショート専用スタイル。
ゆっくり系（対話＋立ち絵）とは別系統で、**キャラクターを一切描かない**。

- 1080x1920 / 30fps
- 背景: 実写写真のスライドショー（1ファクト＝1枚）
- 上部: 赤帯バッジ（常時表示）
- 中央: 白太字のファクト（数字だけ自動で黄色に強調）
- 下部: 赤の補足テキスト
- 末尾: プロフィール誘導のCTA画面（単色・赤い上向き矢印）
- 音声: VOICEVOX 単独ナレーション（対話なし）

参考フォーマット: @sakai-l7u スタイル。

---

## 実装の入り口

| 役割 | 場所 |
| --- | --- |
| レンダラー | `backend/pipeline/video_generator.py` → `FactsOverlayShortRenderer` |
| 生成関数 | 同 `generate_facts_overlay_short()` |
| スタイル分岐 | 同 `generate_all()` の `if style == "facts_overlay"` |
| シナリオ生成 | `backend/pipeline/auto_scenario/generator.py` → `_build_facts_overlay_prompt()` |
| 設定 | `data/channels/company-facts.json` の `video_format.facts_overlay` |

`style` はチャンネル JSON の値がそのまま `generate_all(style=...)` に流れる。
既存の `yukkuri` / `monologue` の経路には手を入れていない。

## シナリオ形式

対話形式（`{"speaker": ..., "text": ...}`）ではなく、1画面＝1ファクトのリスト。

```json
{
  "fact_header": "超ホワイト企業",
  "fact_main": "平均年収 850万円",
  "fact_sub": "業界平均は420万円",
  "fact_note": "有価証券報告書ベース",
  "text": "ニトリの平均年収は850万円。小売業界の平均の2倍だ。",
  "bg_query": "ニトリ 店舗 外観",
  "duration": 5,
  "mood": "bright"
}
```

| フィールド | 表示位置 | 補足 |
| --- | --- | --- |
| `fact_header` | 上部の赤帯バッジ | 省略時は直前の値を引き継ぐ。最初は設定の既定バッジ |
| `fact_main` | 中央の白太字 | 数字＋単位（`850万円`）は自動で強調色。折返しで分断されない |
| `fact_sub` | 下部の赤テキスト | 比較・出典・注意点 |
| `fact_note` | `fact_main` の直下（小さめ白） | 任意 |
| `text` | 画面には出ない | VOICEVOX が読むナレーション |
| `bg_query` | — | その画面の背景写真の検索クエリ |
| `duration` | — | **最低**表示秒数。実尺は音声長に合わせて伸びる |
| `mood` | — | 既存のBGM/演出タグと共通 |

末尾のCTA行は `{"is_cta": true, ...}`。`fact_header` / `bg_query` は付けない
（専用の全画面デザインになる）。シナリオにCTA行が無い場合は
`facts_overlay.cta` の設定から自動で1枚合成される。

対話形式のシナリオを誤って渡した場合も落ちない（`text` をそのまま
`fact_main` に流用して描画する）。

## 背景スライドショー

`image_collector` は1クエリにつき先頭ヒット1枚しか返さないため、
**クエリを振り分けて複数枚集める**方式にしている。

1. 各シーンの `bg_query`
2. タイトル先頭から切り出した企業名 + `facts_overlay.slideshow.query_suffixes`
3. `image_collect.query_template` の `{company_name}` 展開
4. 既存の `_short_bg_query()`（チャンネル共通フォールバック）

縮小画像のハッシュで重複を弾き、1枚も集まらなければ手描き背景
（赤いアクセントストライプ入りグラデーション）にフォールバックする。
真っ黒な動画にはならない。

写真は `settings["orientation"] = "portrait"` で縦写真を優先取得する
（`image_collector` 側は未指定なら従来どおりなので、他チャンネルの収集結果は変わらない）。

### 背景写真の質について

現状 `provider: "auto"` は Pexels に解決される。Pexels はストックフォト
ライブラリなので「ニトリの店舗」のような**実在企業の写真は返さない**
（雰囲気の近い一般写真になる）。実店舗写真が要るなら Google CSE を使う:

1. `GOOGLE_CSE_API_KEY` と `GOOGLE_CSE_ID` を `backend/.env` に設定
2. `company-facts.json` の `image_collect.provider` を `"google_cse"` に変更

`license_filter: "cc"` は設定済みだが、企業ロゴ・店舗写真の利用可否は
別途確認すること。

## 設定（`video_format.facts_overlay`）

```jsonc
{
  "overlay_alpha": 100,          // 背景写真を暗くする量 (0-255)
  "header_badge": { "text": "超ホワイト企業", "bg_color": [220,40,40], "font_size": 56, "y_position": 150, "padding": [18,44] },
  "fact_text":    { "font_size_main": 96, "font_size_main_min": 62, "highlight_color": [255,230,50], "stroke_width": 8, "y_center": 760, "max_lines": 3 },
  "bottom_text":  { "font_size": 52, "text_color": [255,60,60], "y_position": 1420 },
  "slideshow":    { "enabled": true, "max_images": 5, "switch_per_fact": true, "query_suffixes": ["店舗 外観", "看板", ...] },
  "cta":          { "enabled": true, "headline": "他の企業もチェック", "sub": "プロフィールから見れます" }
}
```

`VideoFormat.from_dict` は未知キーを落とすため、これらは
`layout` 配下ではなく **`facts_overlay` セクション**に置くこと
（`short_illustrations` と同じ自由形式dict扱い）。

スライド間のクロスフェードは `video_format.effects.transition_duration`、
微ズームは `effects.zoom_max` が担当する（`facts_overlay` 側には持たない）。

## 生成物

`generate_all(gen_type="short")` の戻り値:

- `short` … mp4
- `short_thumbnail` / `thumbnail` … 1枚目のフレームを流用した縦サムネ
- `short_description` … 説明文txt

長尺（`gen_type="full"`）は未対応。指定された場合は警告を出してスキップする。

## メタデータまわりの注意

このスタイルのチャンネルは「ゆっくり」ではないので、以下を JSON で明示している。

- `main_title_prefix: ""` … 既定の `【ゆっくり解説】` を付けない
  （既定はスタイルが `yukkuri` / `monologue` のときだけ付く）
- `defaults.short_title_hashtags` … 末尾ハッシュタグを差し替え
- `description_template.omit_fullvideo_cta: true` … 本編が無いので
  「続きはフル動画で」誘導を出さない
- `description_template.short_intro` … 代わりに出典の注記を入れる

## 動作確認の手順

VOICEVOX を起動し、`backend/.env` を読み込んでから:

```bash
set -a && source backend/.env && set +a
python3 backend/run_channel_short_upload.py company-facts   # 生成＋投稿（SKIP_UPLOAD=1 で生成のみ）
```

レンダラーだけ確認したい場合は `generate_all` を直接呼ぶ短いスクリプトで足りる
（フレームだけなら TTS/ffmpeg 無しで `build_overlay()` を叩けばよい）。
