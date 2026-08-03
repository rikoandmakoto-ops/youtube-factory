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

同じ企業を狙うクエリは上位ヒットが一致しがちなので、重複を検知したら
`settings["skip"]` を増やして「次のヒット」を取りに行く（最大3回）。
これをやらないと1〜2枚しか集まらず、スライドショーが成立しない。

### 背景写真の質について

ストックフォト系プロバイダ（Pexels / Pixabay / Unsplash）は
「ニトリの店舗」のような**実在企業の写真を返さない**。雰囲気の近い
無関係な一般写真になり、企業ファクト動画としては成立しない。

そのため **APIキー不要**の2プロバイダを実装済み。`company-facts.json` は
`image_collect.provider: "wikimedia,openverse,pexels"` を設定していて、
カンマ区切りは**上から順に試すフォールバック連鎖**として解釈される。

| provider | キー | 特徴 |
|---|---|---|
| `wikimedia` | 不要 | Wikimedia Commons。実在企業の店舗・本社・製品写真が最も取れる |
| `openverse` | 不要 | Openverse（Flickr等のCC集約）。Commons に無い街角写真を拾える |
| `google_cse` | 要 | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID`。網羅性は最高だがキーと課金が要る |

`auto` の解決順は従来のまま（ストック優先）にしてある。既存チャンネルの
絵柄を変えないためで、実写が要るチャンネルだけが明示指定する。

補足:
- Wikimedia は User-Agent に連絡先が無いと `429` を返す。`_UA` は連絡先付きで
  組み立てており、`IMAGE_COLLECTOR_CONTACT` で上書きできる。
- Commons 検索は全語 AND なので、`ユニクロ 店舗 外観` のような多語クエリは
  語を後ろから落としながら再試行する。
- 原寸URLではなく必ずサムネイルURL経由で取得する（帯域制限に触れるため）。
- `license_filter: "cc"` は設定済みだが、企業ロゴ・店舗写真の利用可否は
  別途確認すること。

### 企業ロゴチップ

`fetch_entity_logo()` が **Wikidata の logo image (P154)** からロゴを1枚取り、
白いカードに載せて左上に常時表示する（`facts_overlay.logo_chip`）。

Wikipedia の pageimage は本社ビルの写真が入っていることが多くロゴにならないため、
ロゴ専用プロパティである P154 だけを見る。取得できなければチップを描かない
（無関係な画像を出すよりは何も出さない方がよい）。

### 画面の動き

静止画スライドショーは「切り替わる瞬間しか動かない」ため、そのままだと
紙芝居に見える。`facts_overlay.motion` で常時わずかに動いている状態を作る。

| キー | 既定 | 内容 |
|---|---|---|
| `ken_burns` | 0.10 | シーン全体でかける寄り量。偶数カットは寄り／奇数カットは引き、ドリフト方向も交互に振って単調さを避ける |
| `crossfade` | 0.35 | カット頭で前カットから溶ける秒数 |
| `text_in` | 0.32 | 文字の入りアニメ。バッジ→本文→補足の順に少しずつ遅らせて出す |

`motion.enabled: false` で全部止めて従来の静止フレームに戻せる。

実装上、文字を毎フレーム描き直すと重いのでレイヤーは1シーンにつき1度だけ
描き、フレームごとには平行移動とアルファ調整だけを行う。

`fact_text.scrim_alpha`（既定120）は文字帯の裏に敷くぼかし暗幕。実店舗写真は
情報量が多く、縁取りだけでは数字が背景に埋もれるため。`0` で無効。

### 同ジャンル競合の調べ方

`effects_researcher` に `business_facts` ジャンルを追加済み。`style` が
`facts_overlay` のチャンネルは自動でこのジャンルに解決される。

このジャンルは `prefer_shorts: true` で、長さフィルタが**反転**する
（`shorts_threshold_sec` 以下＝縦型ショートだけを集める）。ショート専用
チャンネルで長尺を分析しても演出の参考にならないため。

なお集約フェーズは Claude を使うので、クレジット切れのときは検索・選定までしか
通らない（`_search_videos` / `_select_per_channel` は単体で呼べる）。

## 設定（`video_format.facts_overlay`）

```jsonc
{
  "overlay_alpha": 100,          // 背景写真を暗くする量 (0-255)
  "header_badge": { "text": "超ホワイト企業", "bg_color": [220,40,40], "font_size": 56, "y_position": 150, "padding": [18,44] },
  "fact_text":    { "font_size_main": 96, "font_size_main_min": 62, "highlight_color": [255,230,50], "stroke_width": 8, "y_center": 760, "max_lines": 3 },
  "bottom_text":  { "font_size": 52, "text_color": [255,60,60], "y_position": 1420 },
  "slideshow":    { "enabled": true, "max_images": 6, "switch_per_fact": true, "query_suffixes": ["店舗 外観", "看板", ...] },
  "motion":       { "enabled": true, "ken_burns": 0.12, "crossfade": 0.35, "text_in": 0.32 },
  "logo_chip":    { "enabled": true, "size": 170, "position": "top_left", "margin": 40 },
  "cta":          { "enabled": true, "headline": "他の企業もチェック", "sub": "プロフィールから見れます" }
}
```

`VideoFormat.from_dict` は未知キーを落とすため、これらは
`layout` 配下ではなく **`facts_overlay` セクション**に置くこと
（`short_illustrations` と同じ自由形式dict扱い）。

背景の寄り・カット間クロスフェード・文字の入りは `facts_overlay.motion` が持つ
（`video_format.effects` 側のクリップ全体エフェクトとは別レイヤー。effects は
文字ごと動かすのに対し、`motion` は背景と文字を別々に扱う）。
`slideshow.ken_burns` / `slideshow.crossfade` に書いても読む（設定の書き場所ゆれ対策）。

## 生成物

`generate_all(gen_type="short")` の戻り値:

- `short` … mp4
- `short_thumbnail` / `thumbnail` … 1枚目のフレームを流用した縦サムネ
- `short_description` … 説明文txt

長尺（`gen_type="full"`）は未対応。指定された場合は警告を出してスキップする。

## 競合分析メモ（2026-08-03）

YouTube Data API で「企業 年収 / ホワイト企業 / 就職偏差値」系の日本語ショートを
横断収集し、上位のサムネイル・構成を目視で確認した結果。設計の根拠。

- **伸びている上位の大半はスキット系**（東京ウーバーズ、テイコウペンギン等の
  アニメコント）。ファクトオーバーレイ形式は再生数の絶対値では劣るが、
  自動生成で再現できるのはこちら側。
- **画面の主役は「企業そのもの」**。ランキング系上位（`s747zxNUvhI`,
  `xb2FsHL-Kok`）は画面が企業ロゴで埋め尽くされている。汎用ストック写真は
  この形式では機能しない → keyless プロバイダ導入とロゴチップの根拠。
- **実写系の参考例**（`tMZMvs4azTs`, 転職.com / ニトリ）: 実店舗の映像を背景に、
  企業ロゴを小さくコーナーに常置、赤い小バッジ＋見出し、キーワードだけ色替え。
  現行の赤帯バッジ＋白太字＋数字黄色ハイライトはこの構成と一致している。
- **数字が主役**。「1,000万超え」「年収3000万」のように、数字だけ極太・
  縁取り・別色。既存の `_highlight_segments`（数字だけ強調色）はこの流儀。
- **1画面1情報でテンポよく切る**。`switch_per_fact: true` を維持する根拠。

分析対象の生データは `effects_researcher` の `business_facts` ジャンルで
再取得できる（上記「同ジャンル競合の調べ方」）。

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
