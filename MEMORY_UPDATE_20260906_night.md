# メモリ更新差分 — 2026-09-06 深夜（nightly-full-progress）

実行: 2026-09-06 23:10–23:45 JST

> ⛔ `~/.auto-memory/` は **9夜連続で接続フォルダ外**。接続済みは
> `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つのみ。
> タスク指定の `reference_all_projects.md` / `project_aiseki_*.md` / `project_orchestrator.md` 等は
> **1つも読めていない**。**恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。**
> 当面は本ファイルと `youtube-factory/HANDOFF.md` をメモリ本体として扱う。

---

## 0. 本日の結論（3行）

1. **公開30本（09-05の33本から -3）。** 内訳は `clip-kaneko` 3→1（素材枯渇）と `scp-lab` 4→3（再起動日の枠重複が解消した正常化）。**ゆっくり系8chの24枠は全成功。**
2. **サムネ403 は 24/30本（80%）で横ばい。403を免れたのは電話認証済みの daily-science と akashic-librarian の各3本＝ちょうど6本で、09-05 と全く同じ構図。**
3. **Δ再生 10,723 / Δ登録 8（登録/千再生 0.746）。**09-05 の暫定値（3,571 / 1）から大幅改善だが、09-05 は2ch欠測の暫定値なので単純比較はできない。

---

## 1. ★★★ 画像ブリッジ — 真因2つは直ったが、まだ delivered 0

朝の HANDOFF（§37449ae）で ①`channel_id` 欠落 ②スレッドURLの置き場 の2件を修正し、
`backfill` で滞留分に宛先を貼り直した。**設定側は完成した。**

| 項目 | 09-05 | 09-06 |
|---|---:|---:|
| `thread_url` 登録 ch | 12 / 13 | **13 / 13** ✅（2ch-matome を登録） |
| `pending` | 49 | **131** |
| `delivered` | 0 | **0** |
| `cache` / `images` / `failed` | 0 | 0 |

> ★ **配送レッグが壊れていないことは実測で確認済み**（HANDOFF）。
> **残っているのは「ワーカーを人が回す」ことだけ**（`.claude/skills/chatgpt-image-worker/`）。
> ⚠️ `pending` が 49 → 131 と1日で **+82件**。ワーカーを回さない限り毎日80件ずつ積み上がる。
> 画像は引き続き全て Pillow フォールバック。

> ★ **設定を直したら必ず `python3 scripts/image_bridge.py backfill` を走らせること。**
> 依頼はキューに積まれた時点のスナップショットなので、スレッドを後から登録しても既存分は空のまま残る。

---

## 2. ★★ サムネ403 は「認証済み2ch＝6本」の構図が固定化した

本日公開30本のうち **サムネ403 は24本（80%）**。403 を免れた6本は:

```
0s70fyHmkv4 / QFUfc37jobI / _oXJSYtJ1S8   ← daily-science 3本
D7pl44Ba8_U / VDSOW8w8yEY / UsJ5hLH6p5w   ← akashic-librarian 3本
```

**09-05 と完全に同じパターン**（09-05 は daily-science 3 + akashic-librarian 3 の6本）。

| 日 | 公開 | 403 | 率 |
|---|---:|---:|---:|
| 09-04 | 17 | 13 | 76% |
| 09-05 | 33 | 27 | 82% |
| **09-06** | **30** | **24** | **80%** |

**電話認証が済んでいるのは 13ch中2ch（daily-science / akashic-librarian）だけ、という事実が3日連続で再確認された。**
残り11ch は https://www.youtube.com/verify を**ユーザー本人が**実施する必要がある。
`gen_thumbs_v4_all.py` の生成物は依然1枚も反映されていない。

---

## 3. ★★ OAuth — 4chが 09-07 中に失効する見込み（最短で明日）

`youtube_tokens.db` の `expires_at` は**アクセストークン（1時間）**の期限であり、13ch すべて
09-07 00:00 で揃っている。**これは7日失効の指標ではない。**（読み違えないこと）

7日失効の実測は HANDOFF（09-06 朝）の値が最新:
- `akashic-librarian` / `clip-animal` / `fake-paper` / `socio-rx` の**4ch が 2026-09-07 13:30頃 失効**（残 約14時間）
- 他9ch は 09-10 前後

> ⚠️ **akashic-librarian は「403を免れている2chのうちの1つ」なので、失効するとサムネが付く動画がゼロになる。**
> 再認可は Google の同意画面を人がブラウザで通す必要がある。
> 恒久対策は GCP 同意画面を「テスト中」→「本番」へ公開（https://console.cloud.google.com/auth/audience / project 844705815004）。
> ★ **寿命は認可した瞬間に決まるので、本番公開しても再認可するまで既存トークンは7日のまま。**

---

## 4. ★ 本日の公開実績 — 30本（ゆっくり系24 + 切り抜き6）

`video_status` の `updated_at` が 09-06 の行を集計（`watch?v=` のログ数え上げは元動画URLを拾うので使わない）。

| ch | 本数 | 枠 | 備考 |
|---|---:|---|---|
| daily-science | 3 | 06:49 / 11:49 / 16:45 | 全枠成功・**403なし** |
| scp-lab | 3 | 12:22 / 16:45 / 18:22 | **09-05の4本から3本に戻った**（再起動日の重複は解消。09-05 §1-1 の予測どおり） |
| pokemon-lab | 3 | 07:50 / 14:20 / 16:50 | 全枠成功 |
| yokai-watch | 3 | 11:21 / 15:22 / 17:06 | 全枠成功 |
| 2ch-matome | 3 | 06:23 / 11:37 / 20:22 | 全枠成功 |
| company-facts | 3 | 07:34 / 12:50 / 16:41 | 全枠成功 |
| akashic-librarian | 3 | 09:17 / 13:47 / 18:02 | 全枠成功・**403なし** |
| fake-paper | 3 | 10:20 / 14:50 / 18:50 | 全枠成功 |
| clip-lab | 2 | 11:45 / 17:45（国内） | **20:45 海外バイラル枠のみ失敗** |
| clip-fukada | 2 | 12:45 / 20:00 | 2枠とも成功（2日連続） |
| clip-animal | **1** | 09:30 のみ | **18:00 枠は失敗。09-05 と同じ1本のまま** |
| **clip-kaneko** | **1** | 20:30 のみ | **3枠中2枠が「全ての元動画が切り抜き済み」で失敗** |
| socio-rx | 0 | — | autopilot 停止中 |

ゆっくり系8ch は **24枠すべて成功（失敗ゼロ）**。

### 本日の失敗は4件、すべて切り抜き系

| ch・枠 | 失敗理由 |
|---|---|
| clip-kaneko ×2 | `全ての元動画が切り抜き済みです` |
| clip-animal ×1（18:00） | `切り抜ける元動画が見つかりません`（09:30 枠は成功） |
| clip-lab 20:45（`engine: viral`） | `ANTHROPIC_API_KEY 未設定（3回試行）`。依頼書 `viral_1w8*` が滞留 |

---

## 5. ★★ `clips_per_video` の修正は、本日の実績には現れていない

本日 16:48 に `c51c3de fix: 使い切った元動画が候補枠を食い潰して切り抜きが出せない件を直す` をコミット。
backend は本日3回再起動しているので**コードは反映済み**。だが実績は改善していない。

| ch | 09-05 | 09-06 | 判定 |
|---|---:|---:|---|
| clip-animal | 1 | **1** | ❌ 変化なし（18:00 枠は依然失敗） |
| clip-kaneko | 3 | **1** | ❌ 悪化。20:30 のみ成功（`XnK3cRrc3eo`） |
| clip-fukada | 2 | 2 | ✅ 維持 |
| clip-lab | 2 | 2 | ✅ 維持（viral 枠は別要因で失敗） |

> ⚠️ **16:48 のコミットは、本日の切り抜き6枠のうち 17:45(clip-lab) / 20:00(clip-fukada) / 20:30(clip-kaneko)
> の3枠にしか適用機会が無かった。効果判定には 09-07 の丸1日が要る。**
> ただし clip-kaneko は**16:48 以降の 20:30 枠だけが成功**しているので、修正が効いた可能性は残る。
> **09-07 に clip-kaneko / clip-animal の本数を必ず再確認すること。**
- 素材在庫 `data/analytics/clip_acquisition.json` は **20 → 23本**（+3）。
  内訳（元チャンネルID別）: `UCw_7_DkX4ftnQJJtZTrCOOQ` 9 / `UC0yQ2h4gQXmVUFWZSqlMVOA` 4 /
  `UCRUdyowhXEQhoNT7uNEvGJA` 4 / `UCprlj3Bvn0c3XsyvZsIrzEg` 4 / 他2件1本ずつ。

> **次の一手は `clips_per_video` の追加引き上げではなく、clip-kaneko の元動画を仕入れること。**
> 在庫23本を4chで分け合っている構造自体が律速。

---

## 6. 実績（09-05 → 09-06 累積差分）

`video_metrics` の同一動画の 09-05/09-06 両日行を突き合わせた差分。

| ch | Δ再生 | Δ表示 | Δ登録 | 登録/千再生 |
|---|---:|---:|---:|---:|
| scp-lab | 2,963 | 789 | 4 | **1.35** |
| company-facts | 2,634 | 397 | 1 | 0.38 |
| clip-lab | 2,442 | 12 | 0 | 0.00 |
| clip-kaneko | 946 | 431 | 0 | 0.00 |
| 2ch-matome | 939 | 48 | 2 | **2.13** |
| fake-paper | 642 | 57 | 0 | 0.00 |
| akashic-librarian | 475 | 9 | 0 | 0.00 |
| clip-fukada | 89 | 509 | 0 | 0.00 |
| clip-animal | 17 | 83 | 0 | 0.00 |
| pokemon-lab | **-178** | 76 | 1 | — |
| daily-science | **-246** | 129 | 0 | 0.00 |
| **合計（yokai-watch 欠）** | **10,723** | **2,540** | **8** | **0.746** |

> ⚠️ **2ch-matome の 2.13 と scp-lab の 1.35 を「勝ち」と読んではいけない。**
> Δ登録が2〜4人しかない母数で千再生あたりに換算した値であり、1人の増減で倍半分に動く。
> 判断は 09-11 の cta_position A/B と、published_at ベースの区間集計で行うこと。

### 🆕 `yokai-watch` が 09-06 の video_metrics に1行も無い

他11ch は 3〜50行取れているのに **yokai-watch だけ 0行**。09-05 も未取得だった（09-05 §7）。
**2日連続の欠測。** 本日3本公開しているので投稿側は動いている。**取得側の障害。要調査。**

### `channel_metrics` の欠測は 3日で横ばい

最新 **09-03**（yokai-watch のみ 09-02）。09-05 時点の最新は 09-02 だったので1日進んだが、依然3日遅れ。
日次の登録増減は引き続き `video_metrics` 差分で見ること。

---

## 7. テーマキュー残量（`autopilot.theme_queue` の実測）

| ch | 09-05 | **09-06** | 1日 | 残日数 |
|---|---:|---:|---:|---:|
| company-facts | 48 | 43 | 3 | 14日 |
| 2ch-matome | 43 | 40 | 3 | 13日 |
| daily-science | 43 | 38 | 3 | 13日 |
| clip-kaneko | 38 | 38 | — | 未使用 |
| fake-paper | 37 | 35 | 3 | 12日 |
| clip-lab | 33 | 33 | — | 未使用 |
| clip-fukada | 32 | 32 | — | 未使用 |
| akashic-librarian | 32 | 28 | 3 | 9日 |
| scp-lab | 33 | **26** | 3 | 8.7日 |
| pokemon-lab | 26 | **22** | 3 | 7.3日 |
| **yokai-watch** | 24 | **16** | 3 | **5.3日 ⚠️** |
| clip-animal | 14 | 14 | — | 未使用 |
| socio-rx | 5 | 5 | — | 停止中 |

> 🆕 **yokai-watch が 24 → 16 に8件減った。**1日3本のはずが8件消費しているのは、
> 朝の指揮者タスクでコンセプト外2件を除去したうえで、機械ゲート（`cross_channel_gate` /
> `title_constraints`）が弾いた分も `_pop_or_refill_theme` で消費しているため。
> **残5.3日。09-09 までに補充が要る。**（09-05 メモの「09-10 頃に再確認」は前倒しすること）

---

## 8. 全チャンネル コンフィグ現況（09-06 23:20 実読み）

| ch | autopilot | キュー | thread_url | 本日公開 | 403 |
|---|---|---:|---|---:|---|
| daily-science | ✅ | 38 | ✅ | 3 | **なし** |
| scp-lab | ✅ | 26 | ✅ | 3 | あり |
| pokemon-lab | ✅ | 22 | ✅ | 3 | あり |
| yokai-watch | ✅ | **16** | ✅ | 3 | あり |
| 2ch-matome | ✅ | 40 | ✅ 🆕 | 3 | あり |
| company-facts | ✅ | 43 | ✅ | 3 | あり |
| akashic-librarian | ✅ | 28 | ✅ | 3 | **なし** |
| fake-paper | ✅ | 35 | ✅ | 3 | あり |
| clip-lab | ✅ | 33 | ✅ | 2 | あり |
| clip-kaneko | ✅ | 38 | ✅ | **1** | あり |
| clip-fukada | ✅ | 32 | ✅ | 2 | あり |
| clip-animal | ✅ | 14 | ✅ | **1** | あり |
| socio-rx | ❌ | 5 | ✅ | 0 | — |

- **`thread_url` は 09-06 に 13/13 到達**（`missing` が0件）。
- **BGM は `daily-science` の7ファイルのみ。`data/channels_assets/` に他chのディレクトリ自体が存在しない**（12ch 未設定・09-04 から変化なし）。判定は config の `bgm_path` ではなくディレクトリの実在で行うこと。
- `backend/.env` の実読み: **`ANTHROPIC_API_KEY` 行が無い / `REDDIT_CLIENT_ID` 無し / `REDDIT_CLIENT_SECRET` 無し / `OPENAI_API_KEY` 設定あり**。他に `PEXELS_API_KEY` / `YOUTUBE_API_KEY` / `VOICEVOX_URL` は設定済み。`API_KEY` と `NGROK_*` は空。
- `thumbnail_ab_tests.status` は **19件すべて `monitoring` のまま**（09-05 から変化なし）。**切替は1件も起きていない。** ただし §2 のとおり11chはサムネ自体が設定できていないので、A/B の前提が成立していない。

---

## 9. git 状態（youtube-factory）

- 本日 **3コミット**:
  - `37449ae fix: 画像ブリッジの配送を開通し、機械ゲートの取りこぼしを塞ぐ`（00:50）
  - `9245aab data: 09-04〜09-05 の実行結果とレポートを記録する`（00:50）
  - `c51c3de fix: 使い切った元動画が候補枠を食い潰して切り抜きが出せない件を直す`（16:48）
- ブランチ `main`。**`origin/main` と一致（ahead 0）。未push なし。**
- 未コミット **96件**（09-05 は147件）。00:50 のコミットで一度消し込まれ、本日の実行結果が再度積まれた分。
- リモートは `origin = zaki21016` / `neworigin = rikoandmakoto-ops` の2本立てのまま。**どちらを正とするかは未決。**

---

## 10. 他プロジェクト（09-06 23:30 実読み）

### aiseki — https://aiseki-xi.vercel.app（canonical `https://aisekimatch.com/`）

- ✅ 稼働中。SEO メタ・OG・構造化データ正常。
- 🆕 **本日 16:55 に新規コミット `a33d809 紹介ボーナスの量産穴を塞ぎ、SNS投稿用の画像素材とマーケ資料の誤りを直す`。3日ぶりにコードが動いた。**
- 🆕 **`HANDOFF.md` が本日 16:54 に更新された（3,114行）。09-05 メモの「4日分未記載」は解消。**
- 🆕 09-05 の未コミットだったマーケ資材（`.md` 3点）は**このコミットに取り込まれた**。
- ⚠️ **未push が 1件 → 2件に増えた**（`af5f442`（09-03）と `a33d809`（本日））。**バックアップされていない状態が続いている。**
- 未コミット2件は LibreOffice のロックファイル（`.~lock.revenue_simulation.xlsx#` / `.~lock.sns_content_calendar.xlsx#`）。**実体はなく無害だが、xlsx を開きっぱなしという意味なので閉じること。**
- `.xlsx` 2点（`revenue_simulation` / `sns_content_calendar`）は依然 **gitignore で git 管理外＝バックアップなし**。

### FanUp — https://fanup-rouge.vercel.app

- ✅ 稼働中。トップの数値は **09-04 から3日連続で変化なし**: サポーター **1,248** / 進行中 **3** / 達成 **8** / 手数料 ¥0。
  注目クリエイター3名（みみき / けけんた / ああかり、いずれもサポーター0）、プロジェクト3件（82% / 45% / 60%）。
  **実ユーザーの流入がゼロの状態が継続。**
- ⚠️ 最終コミット 08-31 14:22（`2681dfd`）から **6日停滞**。未push 0。未コミット **25件**（09-04 から同数のまま3日据え置き）。
  うち `supabase/apply_missing_functions.sql` はコード資産。適用状況が未確認のまま。
- ブロッカーは **Stripe / Resend の環境変数**で変化なし。

### ORIPA — https://oripa-omega.vercel.app

- ⚠️ **トップページが空レスポンス（本文ゼロ）。09-03 から4日連続。実質ダウン。**
- 最終コミット 08-11 11:09（`5c15784`）から **26日停滞**。
- ⚠️ **ブランチが `feat/stripe-checkout` のまま main 未マージ。**
- 未コミット1件は `HANDOFF.md`（新規・未追跡、09-05 から変化なし）。
- ブロッカーは **古物商許可（審査約40日・未着手）**。

### ai-english-coach

- 最終コミット 08-18 22:14（`a90c4ad`）から **19日停滞**。未コミット2件。**リモート未設定＝バックアップなし。**
- ブロッカーは **LINE Pay 加盟店申込が未着手**。

### ai-orchestrator

- 最終コミット 08-09 16:04（`052a617`）から **28日停滞**。未コミット1件。リモート未設定。
- **アーカイブ継続の判断が保留のまま**（09-03 から変化なし）。

### rhythm-pop / claude-codex-bridge

- rhythm-pop: 06-22 17:17 停止・未コミット19件・リモートなし・アーカイブ予定のまま放置。
- claude-codex-bridge: 07-04 02:45 停止・未コミット1件・リモートなし。

> **リモート未設定は `ai-english-coach` / `ai-orchestrator` / `rhythm-pop` / `claude-codex-bridge` の4つ**（変化なし）。

---

## 11. ブロッカー一覧（09-06 時点）

| ブロッカー | 状態 | 変化 |
|---|---|---|
| **電話認証未完了（13ch中11ch）** | 本日24本（80%）が403。認証済みは daily-science / akashic-librarian のみ | 横ばい・最優先 |
| **OAuth 7日失効（4ch が 09-07 13:30頃）** | akashic / clip-animal / fake-paper / socio-rx。**akashic は403免除ch なので影響大** | **明日 期限** |
| GCP 同意画面の本番公開 | 未着手。7日失効の恒久対策 | 継続 |
| **画像ブリッジのワーカー未稼働** | 設定は13ch完備・真因2件も修正済み。**あとは回すだけ。`pending` 49→131** | 前進・未着手 |
| **clip-kaneko の素材枯渇** | 3枠中2枠失敗。`clips_per_video` 修正では解決せず。元動画の仕入れが必要 | 🆕 悪化 |
| `ANTHROPIC_API_KEY` 未設定 | clip-lab の viral 枠1つのみ。依頼書11件が滞留 | 継続（影響は限定的） |
| **`yokai-watch` の video_metrics 欠測** | 2日連続で0行。取得側の障害 | 🆕 |
| `channel_metrics` 欠測 | 最新 09-03（3日遅れ） | 横ばい |
| `video_metrics` の負のΔ | pokemon-lab -178 / daily-science -246。スナップショット時刻ブレ | 継続 |
| `thumbnail_ab_tests` が全件 `monitoring` | 切替ゼロ。ただしサムネ403が前提を壊している | 継続 |
| BGM 12ch 未設定 | `channels_assets/` に daily-science しか存在しない | 継続 |
| `REDDIT_CLIENT_ID`/`SECRET` 未設定 | RSS のみ | 継続 |
| `socio-rx` の運用可否 | 未決。autopilot ❌ | 継続 |
| CTA 遵守率の効果測定 | 09-01 から**7日連続で未実施** | 悪化 |
| **aiseki の未push 2件** | 09-03 分に本日分が加算。バックアップなし | 🆕 悪化 |
| aiseki の xlsx 2点が git 管理外 | gitignore。バックアップなし | 継続 |
| ORIPA トップが空レスポンス | **4日連続** | 継続 |
| FanUp の未コミット25件 | 3日据え置き | 継続 |
| `~/.auto-memory` が接続フォルダ外 | **9夜連続** | 継続 |

---

## 12. 反証条件の期限（変更なし）

- **cta_position A/B（09-11）** — 変更アーム yokai / pokemon / 2ch（`end`）vs 対照 scp-lab / fake-paper（`after_hook`）。baseline: 妖怪 0.23 / ポケモン 0.23 / 2ch 0.17。**09-11 まで CTA 位置に触らないこと。**
- **4行目ルール（09-13）** — 朝の指揮者が scp / pokemon / yokai の4行目を「新情報追加」→「比較・言い換えで自分ゴト化」に変更。09-13 に 0.3→0.7 減衰pt を再測定し、09-06 時点（scp 23.6 / pokemon 22.0 / yokai 25.0）を下回らなければ**仮説を棄却して元に戻す**。旧文は `short_format._prev_structure_20260906.line4`。
- **尺の対照実験（09-12）** — 実験群 scp-lab / 2ch-matome（32〜36秒）vs 対照群 daily-science / pokemon-lab / yokai-watch。**09-12 まで対照群の尺に触れないこと。**
- **冒頭3秒フック（09-12）** — ベースラインは 09-05 に n=2 しか取れず未取得のまま。**09-07 に再取得すること。**
- **「正体」効果の再測定（09-08）**
- **枠配分の見直し（09-12）**

---

## 13. 明日（09-07）の優先順

1. **OAuth 再認可（4ch・09-07 13:30 期限）。** akashic-librarian / clip-animal / fake-paper / socio-rx。
   **akashic は403を免れている2chの片方なので、失効するとサムネが付く動画が1日3本→0本になる。**
2. **電話認証（11ch）。** 403 が24本/日。1日で最も損失の大きい未対応項目。
3. **画像ブリッジのワーカーを回す。** `pending` 131件。設定は完成しているので、あとは実行だけ。
4. **clip-kaneko の元動画を仕入れる。** 3枠中2枠が空振り。在庫23本を4chで分け合う構造が律速。
5. **`yokai-watch` の video_metrics 欠測を調査**（2日連続0行）。
6. **`yokai-watch` のテーマキュー補充**（残16件＝5.3日）。09-09 までに。
7. GCP 同意画面の本番公開（7日失効の恒久対策）。
8. **aiseki: 未push 2件を push**（`af5f442` / `a33d809`）。LibreOffice のロックファイルを解消。
9. `ANTHROPIC_API_KEY` を `backend/.env` に追加（clip-lab viral 枠・依頼書11件）。
10. 冒頭3秒フックのベースライン再取得（§12）。

---

## 14. 生成物

- `reports/全進捗_2026-09-06.md`
- `MEMORY_UPDATE_20260906_night.md`（本ファイル）
