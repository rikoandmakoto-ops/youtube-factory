# Daily Handoff Log

**実行日時**: 2026-09-08 23:15 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-08.md`
**前回**: 2026-09-07 23:15 / **参照した文脈**: `last_handoff_log.md`(09-07)、`last_merge_log.md`(09-08)、`MEMORY_UPDATE_20260908.md`

> ⚠️ `~/Documents/Claude/.auto-memory/` は接続フォルダ外で読めず（**12日連続**）。youtube-factory 内の `MEMORY_UPDATE_*.md` で代用。
> ℹ️ 実行中（23:00〜）に PDCA/指揮者タスクが並走。`data/reports/2026-09-08/*.json` は `fake-paper` まで生成済み。
> ℹ️ サンドボックスから Mac の localhost:8000 に到達できないため、ログ・DB・設定ファイルの直読みで判定した。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 稼働中・要対応 | 09-08 に **21本**（公開7/予約14）。**減少が加速**（33→30→27→21／-3・-3・-6）。13ch中12ch autopilot稼働、ERRORログ0。未コミット 164→**2**・未プッシュ **0→6**。サムネ403は**8夜連続**（39本中30本）<br>※ 予約は後日追加されうる（前回の09-07は17→21に増えた）。09-09 に本日の確定値を取り直すこと |
| aiseki | 🟢 進捗あり・人手待ち | 本番 `aisekimatch.com` 正常応答。作業ツリー**クリーン**（2→0）・**未プッシュ 2→4**。`migration_referral_guard.sql` 未掲載は**未解消（3日目）** |
| ai-english-coach | 🔵 凍結 | 実装は 08-18 停止・**21日**。09-08 は HANDOFF 追加のみ。未コミット0。**Gitリモート未設定のまま** |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から変化なし。本番正常。未コミット25 |
| oripa | 🟡 Phase1 MVP | 最終コミット08-11。`feat/stripe-checkout` push済み・main へ未マージ9。未コミット1 |
| 切り抜きラボ(clip-lab) | 🟡 稼働・**転換ほぼゼロ** | 30日 **42,604再生・登録+2**。20:45 viral枠は APIキー未設定で失敗継続 |
| rhythm-pop | ✅ 完成済み | 06-22 以降動きなし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降動きなし。未コミット1・リモート未設定 |

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **前回N1「『正体』収斂＋クロスch重複ブロック」→ 114回 → 0回。クローズ。** commit `e4f35f1`（cross_channel_gate / theme_dedup / title_constraints）で解消
- **前回N3「未コミット164件」→ 2件。クローズ。** マージタスクが5コミットに整理・日次生成物を .gitignore へ
- **前回#9「clip-kaneko 全ての元動画が切り抜き済み」→ 14回 → 0回。クローズ。** commit `c51c3de`
- **前回#14「サムネA/B `channel_avg_ctr` の回帰・悪化」→ 18件すべて NULL にクリア。書き戻しループ停止。クローズ。** 正常な1件のみ 0.0291（exhausted）
- **前回#5「Reddit RSS 429」→ 152回 → 0回。課題から観察へ格下げ。** `REDDIT_CLIENT_ID` は未設定のままなので、取得を試みていないだけの可能性は残る
- **09-08朝の枠移設3件が APScheduler に反映済み**（company-facts 19:00 / pokemon-lab 17:00 / yokai-watch 17:00・17:45消滅）。`restart_and_trigger_20260908.command` は実行された。backend は本日3回再起動
- **`channel_metrics` が 09-04 → 09-05 へ1日前進**（ただし詰まりは未解消・下記#3）
- ⚠️ **前回レポートの誤り訂正**: 「OAuth 13ch正常」は誤り。4chは09-06〜07で更新停止＝失効している（下記#5）

### ❌ 未解決

| # | 内容 | 種別 | 本日の実測 |
|---|---|---|---|
| 1 | **サムネイル `thumbnails/set` が HTTP 403**（本人確認未了） | 継続・**最優先**・**8夜連続** | 403発生 **163回**／対象43動画。本日アップの39本中**403を免れたのは9本（23%）のみ** |
| 2 | `ANTHROPIC_API_KEY` 未設定（`backend/.env` 18行目がコメントアウト） | 継続・**8夜連続** | Autopilot失敗3件の直接原因。`series_engine` が5ch（clip-animal/pokemon-lab/clip-lab/company-facts/fake-paper）で「Claude 未応答」 |
| 3 | `channel_metrics` が **09-05止まり・9chのみ**（09-03までは12ch）＝09-06〜08の3日欠測 | 継続・1日前進 | `video_metrics` は09-08分 **351行** 取得済み。channel_metrics の経路だけ詰まっている |
| 4 | 画像ブリッジのスレッドURL未登録（`threads.json` が `{}`） | 継続・**悪化** | `pending` **57件**（全て本日分）／`delivered` **0件**／`failed` **235件** |
| 5 | **OAuth 4ch失効**（clip-animal / socio-rx / fake-paper / akashic-librarian） | 継続 | 9chは本日23:00に更新成功。4chは `updated_at` が09-06〜07で停止。PDCAが3ch分析不能 |
| 6 | GCP OAuth 同意画面が「テスト中」 | 継続・**期限当日** | project 844705815004。失効は09-09前後 |
| 7 | サムネA/B 18件すべて `monitoring`、切替ゼロ | 継続 | 原因は#1 |
| 8 | clip-lab の転換ほぼゼロ | 継続・**悪化** | 42,604再生で登録+2（前日 35,143再生で+1） |
| 9 | clip-animal 実質停止 | 継続 | OAuth失効で分析不能。本日Autopilot失敗4回（元動画なし）・公開0本。autopilotはenabledのまま |
| 10 | aiseki: Twilio トライアルのまま / DM自動送信の規約リスク | 継続 | 紹介報酬の支払いが電話番号認証依存 |
| 11 | aiseki: Instagram DM ワーカーが1通も送れない | 継続 | `worker/` にログイン済み cookies ファイルが存在しない＝未ログイン確定 |
| 12 | ai-english-coach: Gitリモート未設定（消失リスク最大） | 継続・**21日** | `git remote -v` が空 |
| 13 | `~/Documents/Claude/.auto-memory/` が読めない | 継続・**12日連続** | — |
| 14 | aiseki: `migration_referral_guard.sql` が `apply_migrations.command` に未掲載 | 継続・**3日目** | 適用は旧3本のみ。本番適用済みか未確認 |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨 **`require_answer_marker` が効いておらず、かつタイトルを壊している** | 対象6chの本日公開 **36本中21本（58%）** しか答え提示語を含まない。ch差が極端で **daily-science 6/6 vs pokemon-lab 3/9**。さらに助詞が破綻したタイトルが公開: 「RTX5090**はで**部屋の外から名前を呼ぶのか」「7日間**でずつ**消えたエージェント名簿異常事件」「…3作品で徹底比較**の本当**」。最後は `本当の` を語尾に貼り付けた痕跡＝**機械的挿入**。「7日間でずつ」は09-07の数字制約が「1人」を削った跡。**制約追加が日本語を壊す、同じ失敗の3回目**。※午前中（変更完了10:20）の生成分を含むため58%は過小評価の可能性。**09-09は全数が変更後生成なので確定判定できる** |
| **N2** | **画像依頼書が `failed` 235件に積み上がった** | 前回 `pending` 210件が配送されず失敗側へ移動。`delivered` は依然0件。「滞留」から「失敗として捨てられている」へ変質 |
| **N3** | **`phase4.db` の `schedules` テーブルが空** | 実枠は `data/channels/*.json` 由来でAPSchedulerに登録され稼働に実害なし。Phase4予約UIからは枠ゼロに見えるはず。二重管理の残骸の可能性 |
| **N4** | **未プッシュが youtube-factory 0→6 / aiseki 2→4** | マージタスクがコミットまで進めたが GitHub 認証がなく push 未実施。ローカルにしか無いコミットが増えた |
| **N5** | **`.git` 内に `*.lock.stale.*` のゴミ参照が残存** | `git branch` が16行の warning。youtube-factory / ai-orchestrator / claude-codex-bridge / fanup / oripa / rhythm-pop に残る。掃除は Mac 側で `find ~/Developer/<repo>/.git -name '*.stale.*' -delete` |

## 3. ユーザー手動待ちタスク一覧

**期限（今日・明日）**

1. 🚨 **GCP OAuth 同意画面の本番公開**（project 844705815004・**09-09期限＝当日**）← ★①本番公開 → ②13ch再認可 の順厳守
2. 🚨 **YouTube 13ch の電話番号確認**（youtube.com/verify）← サムネ403の唯一の解・8夜連続

**一撃で複数の詰まりが消えるもの**

3. `ANTHROPIC_API_KEY` を `backend/.env` 18行目のコメント解除で有効化
4. 失効4chの再認可（clip-animal / socio-rx / fake-paper / akashic-librarian）※1のあと

**消失リスク**

5. **ai-english-coach の GitHub リモート作成と push**（21日ローカルのみ）
6. 未プッシュの push — `youtube-factory`(6件) / `aiseki`(4件)

**aiseki（公開前の必須条件）**

7. `migration_referral_guard.sql` が本番DBに当たっているか確認（3日目）
8. Twilio を本番アップグレード
9. Instagram にログイン（`cd worker && npm run login`）＋ `/admin/dm` からCSV取り込み

**その他**

10. ChatGPT スレッドURLを13ch分登録（`threads.json` が空・failed 235件）
11. `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加
12. `REDDIT_CLIENT_ID` の設定
13. oripa の `feat/stripe-checkout` を main へマージするか判断（未マージ9）
14. **clip-animal を続けるか止めるか判断**（OAuth失効＋素材枯渇で公開0本）
15. `.git` の `*.stale.*` ゴミ掃除（任意）

## 4. 次回（09-09）の実行時に確認すること

- **サムネ403が解消したか**
- **OAuth 同意画面が本番公開されたか。されていなければ残り9chも失効しているはず** ← 最優先
- **N1: 答え提示語の充足率。09-09は全数が変更後生成なので6chで100%に届くか判定できる。** 届かないなら `title_rules` が backend から読まれていない（09-03に死に設定だった前例あり）。**同時に助詞の壊れたタイトルの再発を目視すること**
- **制作本数。まず 09-08 の確定値を取り直し（予約が後追いで増えるため）、そのうえで 09-09 が21本を上回るか見る。減少は -3/-3/-6 と加速している**
- **`channel_metrics` が09-05から前進したか。ch数が9→12に戻ったか**
- **画像ブリッジ `failed` が235件からさらに増えたか**
- **09-11**: `cta_position` A/B の判定日
- **09-12**: 尺の対照実験の評価日。**それまで対照群の尺に触れない**
- **09-13**: 4行目ルール変更の反証日（scp 23.6 / pokemon 22.0 / yokai 25.0 を下回らなければ棄却）
- **09-15**: 答え提示型100%化の反証期限 — (a) 全体の登録/千再生が0.47を超えるか (b) 2ch-matome が0.20→0.35を超えるか (c) 移設3枠が移設前を下回らないか
- **09-19**: yokai-watch の枠移動の影響評価

## 5. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-08.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクトへの書き込み・git 操作（push/merge/commit）・設定変更・外部DB接続は一切していない。読み取りのみ。
