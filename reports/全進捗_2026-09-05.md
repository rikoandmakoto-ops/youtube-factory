# メモリ更新差分 — 2026-09-05 深夜（nightly-full-progress）

実行: 2026-09-05 23:10–23:40 JST

> ⛔ `~/.auto-memory/` は**8夜連続で接続フォルダ外**。接続済みは
> `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つのみ。
> **恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。**
> 当面は本ファイルと `youtube-factory/HANDOFF.md` を YouTube Factory のメモリ本体として扱う。

---

## 1. ★★★ 朝の宿題は全て片付いた — `apply_orchestrator_20260905.command` は実行済み

朝のメモ §4 は「投稿枠3件とサムネA/B修正はバックエンド再起動が必要」で終わっていたが、
**両方とも本日中に反映されている。**根拠は推測ではなく2つの実測。

### 1-1. 投稿枠は新スケジュールで再登録された

`logs/backend.log` に本日 `Application startup complete.` / `Uvicorn running` があり、
再起動後の `restore_all()` が新しい枠を登録している:

```
Autopilot scheduled for company-facts [slot 2]: ... 17:00 JST (生成開始 16:15 / 公開 17:00)
```

**★ 新事実: 枠の時刻は「公開時刻」で、ジョブ生成はその45分前に走る。**
これまで `job_queue.json` の `created_at` を公開時刻と読んでいたが誤り。
実測の対応: 2ch-matome 20:17 生成 → **21:00 公開枠**（旧18:00枠ではない）。
yokai-watch も 17:00 生成 = 17:45 公開。

> **再起動は 12:15 と 12:45 の生成の間**（`Application startup complete.` は
> scp-lab 12:15 発火と clip-fukada/company-facts 12:45 発火の間に出ている）。
> scp-lab が本日4本（08:15 / 12:15 / 16:15 / 18:15 生成）出たのは、
> **再起動日に旧枠と新枠が重なったため。**明日以降は3本に戻るはず。**09-06 に本数を確認すること。**

### 1-2. サムネA/B のベースラインは是正された

`thumbnail_ab_tests.channel_avg_ctr` の実測:

| ch | 件数 | min | max |
|---|---:|---:|---:|
| daily-science | 15 | 0.03368 | 0.03368 |
| scp-lab | 4 | 0.01454 | 0.01454 |

**ch内で単一値に揃い、`42.909` / `37.286` は消えた。**朝の §5-1 のバグは解消。
ただし `status` は **19件すべて `monitoring`** のままで、切替はまだ1件も起きていない。
判定は次回の A/B チェック時に走るので、**09-06 に status の変化を確認すること。**

---

## 2. ★★ ChatGPT 画像ブリッジ — thread_url は 13ch中12ch に登録された（09-04 の最大ブロッカーが前進）

09-04 夜は「13ch すべて未設定」だったが、本日 12ch に URL が入った。

> ⚠️ **置き場は 09-04 メモの `image_generation.chatgpt_thread_url` ではなく、
> `data/channels/<ch>.json` の top-level `chatgpt_thread_url` である。**（実読みで確認）
> 09-04 メモの記述は訂正する。

| 状態 | ch |
|---|---|
| 登録済み（12） | daily-science / scp-lab / company-facts / fake-paper / pokemon-lab / yokai-watch / akashic-librarian / socio-rx / clip-lab / clip-fukada / clip-kaneko / clip-animal |
| **未登録（1）** | **2ch-matome** |

`data/image_requests/threads.json` は `{}` のまま（`_default` 用なので実害なし）。

### ただし処理側が動いていないのでブリッジはまだ効果ゼロ

| ディレクトリ | 09-04 | 09-05 |
|---|---:|---:|
| `pending` | 1 | **49** |
| `delivered` / `cache` / `images` / `failed` | 0 | **0** |

**依頼は積まれているが1件も処理されていない。**画像は引き続き全て Pillow フォールバック。
**次の作業は 2ch-matome の URL 登録と、ワーカー（`.claude/skills/chatgpt-image-worker/`）を回すこと。**

---

## 3. ★ 本日の公開実績 — 合計 33本（ゆっくり系 25 + 切り抜き 8）。過去最多

> ⚠️ **数え方の注意（今日ここで1回間違えた）: ゆっくり系は `upload_done` を出すが、
> 切り抜き系は `✅ アップロード完了` しか出さない。`upload_done` だけで数えると
> 切り抜きが丸ごとゼロに見える。** 正しくは `watch?v=` のユニーク数で数える（本日33本）。

| ch | 本数 | 備考 |
|---|---:|---|
| scp-lab | 4 | 再起動日で旧枠＋新枠が重なったため（通常は3） |
| daily-science / company-facts / pokemon-lab / yokai-watch / fake-paper / akashic-librarian / 2ch-matome | 各3 | 全枠成功 |
| **clip-kaneko** | **3** | **3枠すべて成功** |
| **clip-lab** | **2** | local 2枠成功 / viral 1枠のみ失敗 |
| **clip-fukada** | **2** | **2枠とも成功（素材ゼロ問題が解消）** |
| **clip-animal** | **1** | 09:30 は失敗、18:00 は成功 |

**09-04 の21本（ゆっくり17＋切り抜き4）から 33本（+57%）。切り抜きも 4→8 に倍増。**

### 本日の失敗は10枠中2枠だけ

| ch・枠 | 失敗理由 |
|---|---|
| clip-lab 20:45（`engine: viral`） | `ANTHROPIC_API_KEY 未設定（3回試行）`。加えて Reddit RSS が `r/HolUp` / `r/funny` / `r/WatchPeopleDieInside` / `r/therewasanattempt` / `r/instant_regret` で **HTTP 429**（5秒・10秒のリトライも失敗） |
| clip-animal 09:30 | `全ての元動画が切り抜き済み`（`clips_per_video=1`）。ただし **18:00 枠は成功**しているので全滅ではない |

---

## 4. ★★ 09-04 の切り抜きブロッカー2件は実質解消していた（メモの訂正）

09-04 夜のメモは「clip-fukada の素材ゼロ」「clip-animal の枯渇」を**継続ブロッカー**としていたが、
**本日は fukada が2枠とも成功、animal も18:00枠が成功している。**

- **clip-fukada**: 09-03 から3日連続で全滅していたが、本日 `AyqVD5Kjq9k`（12:45枠）と
  `jp8kT5Ha0Fg`（20:00枠）を公開。**素材ゼロ問題は解消。**
- **clip-animal**: 09:30 は「全て切り抜き済み」で失敗したが 18:00 は `HaBYDy0J87w` を公開。
  **`clips_per_video=1` の制約は残っているので、1日2枠のうち1枠しか埋まらない状態。**
- **clip-kaneko**: 3枠すべて成功。素材は allowlist 登録チャンネル（ガジェット通信 MCN）から
  1,619秒の元動画を字幕タイムライン238行で解析し、LLM で34.4秒の区間を選定して公開している。
  **local エンジンは `ANTHROPIC_API_KEY` 無しでも動いている**（OpenAI で代替されている）。

> **したがって `ANTHROPIC_API_KEY` 未設定が止めているのは `clip-lab` の viral 枠1つだけ。**
> 09-04 メモが示唆した「切り抜き全体が止まる」ほどの影響ではない。ただし
> **翻訳依頼書は 09-04 の 9件 → 本日 10件**（`viral_1w639x6` / `viral_1w6etlj` / `viral_1w7j3u1`）で積み上がり続けている。

素材在庫（`data/analytics/clip_acquisition.json`）は 18 → **20本**。

---

## 5. 「正体」ルールの暴走は朝の config 書き換えで止まった（本日の施策が効いた実例）

本日の33本のうち「正体」を含むのは **3本（9%）**。09-03 の 71%、09-05 午前の 6本中4本から低下。

| 時刻 | ch | タイトル |
|---|---|---|
| 06:17 | 2ch-matome | 🤣ワイ健康診断歴3年やけど正体あるw🍑 |
| 06:47 | daily-science | あなたの耳が3秒で抜ける正体は？ |
| 07:30 | company-facts | 航空自衛隊千歳の正体、年収400万円台の実態 |

**3本すべて 07:30 までの生成分。朝の config 書き換え（10:12 頃）以降の30本には1本も入っていない。**
「1バッチ最大1本 / 不自然なら入れない」の上限が実効している。

> ★ **`style_rules` は実行ごとに読み直されるので、再起動を待たずに即日効く**（朝のメモ §4 の通り）。
> 一方 **投稿枠（cron）は再起動が要る**（§1-1）。**施策の種類で反映タイミングが違う。**
> 06:17 の 2ch-matome『🤣ワイ健康診断歴3年やけど正体あるw🍑』は書き換え前の生成で、
> 日本語として破綻したまま公開されている。**config を書き換えた日は、書き換え時刻より前に
> 生成された分が旧ルールで出ることを前提に読むこと。**

### company-facts の数値矛盾は本日は出ていない

本日の3本は 航空自衛隊千歳400万円台 / 東京エレクトロン1272万円 / キーエンス2067万円で、
**同一企業の重複なし。**09-03〜09-04 のマクドナルド矛盾（670万 vs 576万）は再発していない。

---

## 6. ⚠️ サムネ403 は悪化 — 33本中27本（82%）

`サムネイル設定失敗 (<video_id>)` のユニーク動画は **27本**。403 が付かなかったのは **6本のみ**:

```
WGMpYbnGXAU / Y94yR_35IyA / x1X8G1eVNfE   ← daily-science 3本
Wg5I1xjW-EQ / OYw_JIuVtdE / 6J3CwNc7vn4   ← akashic-librarian 3本
```

**403 を免れたのは電話認証済みの2ch分ちょうど6本。他11ch（切り抜き4chを含む）は全滅。**
09-04 は 17本中13本（76%）で、絶対数が **13 → 27 に倍増**した。
公開本数を増やした分だけ、サムネ無しの動画が増えている。

> 🆕 **切り抜き4chも 403 を受けている**（`ZuI-kOEL5ys` / `p2EaWnHI6AE` / `AyqVD5Kjq9k` /
> `_5P62LMYYa8` / `Ras7astkIYI` / `HaBYDy0J87w` / `jp8kT5Ha0Fg` / `Lta6vjjEeok` の8本すべて）。
> 09-04 メモはゆっくり系8chしか調べていなかった。**電話認証は13ch中11chで未完了。**

> **scp-lab の CTR 1.54%（全ch最下位・表示回数は全社の56%）はサムネA/Bの前に
> そもそもサムネが設定できていないことが原因である可能性が高い。**
> 朝の §9「scp-lab のサムネA/Bを開始する」は、**電話認証が先。**順序を入れ替えること。

---

## 7. 実績（09-04 → 09-05 累積差分・**暫定**）

⚠️ **23:00 開始の日次 PDCA が本レポート作成中も実行中。**
`video_metrics` の 09-05 取得は 243行で、**scp-lab 9/50 行・yokai-watch 0/43 行と未取得。**
下表はこの2chが欠けた暫定値であり、**確定値として引用してはいけない。**

| ch | Δ再生 | Δ登録 | Δ表示 | 登録/千再生 |
|---|---:|---:|---:|---:|
| fake-paper | 1,229 | 0 | 94 | 0.00 |
| akashic-librarian | 1,185 | 0 | 34 | 0.00 |
| clip-kaneko | 1,009 | 1 | 150 | 0.99 |
| clip-fukada | 82 | 0 | 836 | 0.00 |
| clip-lab | 45 | 0 | 18 | 0.00 |
| company-facts | 16 | 0 | 524 | 0.00 |
| 2ch-matome | 4 | 0 | 62 | 0.00 |
| pokemon-lab | 1 | 0 | 132 | 0.00 |
| daily-science | 0 | 0 | 129 | 0.00 |
| clip-animal | 0 | 0 | 0 | — |
| **合計（scp-lab / yokai-watch 欠）** | **3,571** | **1** | **1,979** | **0.280** |

- daily-science の Δ再生 0 は「不調」ではなく、50行取れているのに増分が付いていない＝
  **09-05 の取得時点が 09-04 より早い時刻だった可能性**が高い。朝のメモ §0（累積カウンタ）の通り、
  **1日単位の差分はスナップショット時刻のブレに弱い。日次で一喜一憂しないこと。**
- `cta_position` A/B の判定日は **09-11**。本日の数値では判断しない。

### 取得破損（朝の §5-3）は 09-05 も出ている・むしろ増えた

| 症状 | 09-04 | 09-05 |
|---|---:|---:|
| `views=0` かつ `impressions>0` | 7 | **15** |
| 累積 `views` が前日より減った動画 | 35（合計 -27,728） | **17（合計 -4,814）** |

**破損は解消していない。取得後の整合チェックを実装する必要がある。**
（ただし PDCA 実行中の中間状態を見ている可能性があるので、09-06 朝に確定値で再確認すること。）

### `channel_metrics` の欠測は悪化

最新 **09-02**（09-04 時点では 09-01 が最新だったので1日進んだが、依然**3日欠測**）。
日次の登録増減は引き続き `video_metrics` 差分で見ること。

---

## 8. 冒頭3秒フックの「導入前ベースライン」は取れなかった（09-06 に持ち越し）

朝の宿題 §13-3。`retention_curve` から 09-02 / 09-03 公開分の 5%→10% 落差を出そうとしたが、
**データが着信しているのは2本だけ**だった。

| ch | n | 5% | 10% | 落差 |
|---|---:|---:|---:|---:|
| akashic-librarian | 1 | 52.8% | 49.6% | -3.2pt |
| fake-paper | 1 | 32.1% | 28.4% | -3.7pt |

**n=1 では基準値にならない。09-06 以降に再取得すること。**
なお `retention_curve` のスキーマは `(video_id, channel_id, curve, fetched_at)` で、
**`curve` は JSON 文字列。`elapsed_ratio` という列は存在しない。**（今日ここで1回つまずいた）

---

## 9. テーマキュー残量（実測 = `autopilot.theme_queue` の要素数）

> ⚠️ **`theme_seeds` はキューではない。**キューは `autopilot.theme_queue`。今日ここで1回間違えた。

| ch | 残 | 1日本数 | 残日数 |
|---|---:|---:|---:|
| company-facts | 48 | 3 | 16日 |
| 2ch-matome | 43 | 3 | 14日 |
| daily-science | 43 | 3 | 14日 |
| fake-paper | 37 | 3 | 12日 |
| scp-lab | 33 | 4 | 8日 |
| akashic-librarian | 32 | 3 | 10日 |
| **pokemon-lab** | **26** | 3 | **8.7日** |
| **yokai-watch** | **24** | 3 | **8日** |
| socio-rx | 5 | — | 停止中 |
| clip系4ch | 14〜38 | — | 未使用（`trend_scanner` が補充し続けている） |

**補充は不要。09-10 頃に yokai-watch / pokemon-lab / scp-lab を再確認。**

---

## 10. 全チャンネル コンフィグ現況（09-05 23:20 実読み）

| ch | autopilot | 公開枠（新） | キュー | thread_url | 本日公開 |
|---|---|---|---:|---|---:|
| daily-science | ✅ | 07:30 / 12:30 / 17:00 | 43 | ✅ | 3 |
| scp-lab | ✅ | 13:00 / 17:00 / 19:00（平日・週末とも） | 33 | ✅ | 4 |
| pokemon-lab | ✅ | 08:30 / 15:00 / 17:30 | 26 | ✅ | 3 |
| yokai-watch | ✅ | 12:00 / 16:00 / **17:45** | 24 | ✅ | 3 |
| 2ch-matome | ✅ | 07:00 / 12:15 / **21:00** | 43 | **❌ 未登録** | 3 |
| company-facts | ✅ | 08:15 / 13:30 / 17:00 | 48 | ✅ | 3 |
| akashic-librarian | ✅ | 10:00 / 14:30 / 18:45 | 32 | ✅ | 3 |
| fake-paper | ✅ | 11:00 / 15:30 / 19:30 | 37 | ✅ | 3 |
| clip-lab | ✅ | 11:45 / 17:45 / 20:45（`engine: viral`） | 33 | ✅ | 2（viral枠のみ失敗） |
| clip-kaneko | ✅ | 08:00 / 14:00 / 20:30 | 38 | ✅ | 3 |
| clip-fukada | ✅ | 12:45 / 20:00 | 32 | ✅ | 2 |
| clip-animal | ✅ | 09:30 / 18:00 | 14 | ✅ | 1 |
| socio-rx | ❌ | 20:00（平日）/ 15:00（週末） | 5 | ✅ | 0 |

- **BGM は `daily-science` の7ファイルのみ（12ch 未設定）**で 09-04 から変化なし。
  判定は config の `bgm_path` ではなく `data/channels_assets/<ch>/bgm/` の実在で行うこと。
- `backend/.env` の実読み: **`ANTHROPIC_API_KEY` 未設定 / `REDDIT_CLIENT_ID` 未設定 /
  `REDDIT_CLIENT_SECRET` 未設定 / `OPENAI_API_KEY` 設定あり。**
  （`.env` はリポジトリ直下ではなく **`backend/.env`**。パスを間違えないこと。）

---

## 11. git 状態（youtube-factory）

- 本日 1コミット: **`e4eef9f fix: 指揮者(09-05)の指摘7件を反映する`**
- 未コミット **147件**（09-04 は82件）。増分は本日の実行結果（`data/` 配下の config / scenarios /
  analytics / image_requests）。
- ブランチ `main`。リモートは `origin = zaki21016` / `neworigin = rikoandmakoto-ops` の2本立てのまま。
  **どちらを正とするかは未決。**

---

## 12. 他プロジェクト（09-05 23:25 実読み）

### aiseki — https://aiseki-xi.vercel.app（canonical `https://aisekimatch.com/`）

- ✅ 稼働中。SEO メタ・OG・構造化データは 09-03 の改修どおり。
- 🆕 **本日 12:34–12:38 に営業・マーケ資材を5点新規作成。**コードではなく事業側の作業。
  - `influencer_outreach.md` — インフルエンサー10名の優先リスト（Tier1: @erikojiaoi 4.9万 /
    @mi_yan0101 3万 / @urarie_kobe 2.5万 / @osaka_nomiaruki 1.5万 / @kansai_nomikai 0.6万）と
    想定報酬（0.5〜5万円/件）。**エリアは神戸・大阪・心斎橋＝関西。**
  - `dm_templates.md` — DM文面テンプレート
  - `sns_profile_guide.md` — SNSプロフィール設計
  - `revenue_simulation.xlsx` — 4シート（収益モデル / シナリオ比較 / 価格感度分析 / ユニットエコノミクス）
  - `sns_content_calendar.xlsx` — 3シート（30日投稿カレンダー / ハッシュタグ戦略 / 投稿時間帯）
- ⚠️ **`.md` 3点は未コミット。`.xlsx` 2点は gitignore されており git 管理外。**
  → **本日の成果物はバックアップされていない。**
- ⚠️ **コードの最終コミットは 09-03 11:08（`af5f442`）から3日停滞。未push 1件も 09-03 から未解消。**
- ⚠️ **`HANDOFF.md` は 09-01 20:17 のまま。09-02 の e2e 検証、09-03 の LP 改修、
  本日のマーケ資材が4日分未記載。**

### FanUp — https://fanup-rouge.vercel.app

- ✅ 稼働中。トップの数値は 09-04 から変化なし: サポーター **1,248** / 進行中 **3** / 達成 **8**。
  注目クリエイター3名（みみき / けけんた / ああかり）、プロジェクト3件（82% / 45% / 60%）。
  **数値が動いていない＝実ユーザーの流入がない状態が継続。**
- ⚠️ 最終コミット 08-31 14:22（`2681dfd`）から**5日停滞**。未push 0。未コミット 25件（09-04 と同数）。
  うち `supabase/apply_missing_functions.sql` はコード資産。適用状況が未確認のまま。
- ブロッカーは **Stripe / Resend の環境変数**で変化なし。

### ORIPA — https://oripa-omega.vercel.app

- ⚠️ **トップページが空レスポンス（本文ゼロ）。09-03 から3日連続。実質ダウン。**
- 最終コミット 08-11 11:09（`5c15784`）から**25日停滞**。
- ⚠️ **ブランチが `feat/stripe-checkout` のまま main 未マージ。**
- 🆕 未コミット 1件は **`HANDOFF.md`（新規・未追跡）**。
- ブロッカーは **古物商許可（審査約40日・未着手）**。

### ai-english-coach

- 最終コミット 08-18 22:14（`a90c4ad`）から**18日停滞**。未コミット 2件。**リモート未設定＝バックアップなし。**
- ブロッカーは **LINE Pay 加盟店申込が未着手**。

### ai-orchestrator

- 最終コミット 08-09 16:04（`052a617`）から**27日停滞**。未コミット 1件。リモート未設定。
- **アーカイブ継続の判断が保留のまま**（09-03 から変化なし）。

### rhythm-pop / claude-codex-bridge

- rhythm-pop: 06-22 17:17 停止・未コミット19件・リモートなし・アーカイブ予定のまま放置。
- claude-codex-bridge: 07-04 02:45 停止・未コミット1件・リモートなし。

> **リモート未設定は `ai-english-coach` / `ai-orchestrator` / `rhythm-pop` / `claude-codex-bridge` の4つ**（変化なし）。

---

## 13. ブロッカー一覧（09-05 時点）

| ブロッカー | 状態 | 継続日数 |
|---|---|---|
| **電話認証未完了（13ch中11ch）** | **サムネ403 が本日27本（82%）。切り抜き4chも対象だと判明。scp-lab の低CTRの主因の可能性** | 悪化 |
| `ANTHROPIC_API_KEY` が `backend/.env` に未追加 | 止めているのは clip-lab の viral 枠1つ。依頼書10件が滞留 | 継続（影響は限定的と判明） |
| ChatGPT 画像ブリッジのワーカー未稼働 | thread_url は 12ch 登録済み（前進）。だが `pending` 1→49、`delivered` 0 | 前進・未解決 |
| 2ch-matome の thread_url 未登録 | 13ch中1chだけ残 | 🆕 |
| GCP 同意画面の本番公開 | 未着手。**次の失効が 09-09 前後** | 継続 |
| ~~clip-fukada の素材ゼロ~~ | **✅ 解消。本日2枠とも成功** | 解消 |
| clip-animal の `clips_per_video=1` | 2枠中1枠のみ成功。制約は残存 | 継続（軽微） |
| `REDDIT_CLIENT_ID`/`SECRET` 未設定 | RSS のみ。本日 6 サブレディットが HTTP 429（リトライも失敗） | 継続 |
| BGM 12ch 未設定 | daily-science のみ | 継続 |
| `socio-rx` の運用可否 | 未決。autopilot ❌ | 継続 |
| CTA 遵守率の効果測定 | **09-01 から6日連続で未実施** | 継続 |
| `channel_metrics` 欠測 | 最新 09-02（3日） | 継続 |
| `video_metrics` の取得破損 | `views=0 & impressions>0` が 7→15 に増 | 悪化 |
| aiseki の未push 1件 / HANDOFF 4日未更新 | 09-03 から未解消 | 継続 |
| ORIPA トップが空レスポンス | 3日連続 | 継続 |
| `~/.auto-memory` が接続フォルダ外 | **8夜連続** | 継続 |

---

## 14. 反証条件の期限

- **cta_position A/B（09-11）** — 変更アーム yokai / pokemon / 2ch（`end`）vs
  対照 scp-lab / fake-paper（`after_hook`）。baseline: 妖怪 0.23 / ポケモン 0.23 / 2ch 0.17。
- **尺の対照実験（09-12）** — 実験群 scp-lab / 2ch-matome（32〜36秒）vs
  対照群 daily-science / pokemon-lab / yokai-watch。**09-12まで対照群の尺に触れないこと。**
- **冒頭3秒フック（09-12）** — 比較用ベースラインが未取得（§8）。**09-06 に取り直すこと。**
- **「正体」効果の再測定（09-08）** — 本日の投入で母数増。pokemon-lab を除く3chの効果量も併記。
- **枠配分の見直し（09-12）** — pokemon-lab / 2ch-matome は再生を稼ぐが登録に繋がっていない。
  尺実験の評価と同時に判断する。

---

## 15. 明日（09-06）の優先順

1. **電話認証（最優先）。** サムネ403 が **27本/日**、13ch中11chで未完了。
   公開本数を33本まで増やした今、これが最大の損失。**scp-lab のサムネA/B より先。**
2. ChatGPT 画像ワーカーを回す（`pending` 49件が未処理）＋ **2ch-matome の thread_url 登録。**
3. **GCP 同意画面の本番公開**（次の失効が 09-09 前後）。
4. `ANTHROPIC_API_KEY` を `backend/.env` に追加（clip-lab の viral 枠と依頼書10件）。
   **09-04 メモが示唆したほど広範な影響は無かったので、優先度は3番手以降に下げる。**
5. 冒頭3秒フックの導入前ベースラインを取り直す（§8）。
6. `thumbnail_ab_tests.status` が `monitoring` 以外に動いたか確認（§1-2）。
7. scp-lab の公開本数が3本に戻ったか確認（再起動日の重複が解消したか。§1-1）。
8. `video_metrics` の取得破損に整合チェックを入れる（§7）。
9. aiseki: 未push 1件を push、本日のマーケ資材5点をコミット、`HANDOFF.md` に §34 を追記。
10. clip-animal の `clips_per_video` を上げる（2枠中1枠しか埋まっていない）。

---

## 16. 生成物

- `reports/全進捗_2026-09-05.md`
- `MEMORY_UPDATE_20260905_night.md`（本ファイル）
