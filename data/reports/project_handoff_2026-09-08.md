# 全プロジェクト 引き継ぎレポート — 2026-09-08

**実行**: 2026-09-08 23:15 JST（daily-project-handoff 自動実行）
**前回**: 2026-09-07 23:15
**参照した文脈**: `last_handoff_log.md`(09-07) / `last_merge_log.md`(09-08) / `MEMORY_UPDATE_20260908.md`

> ⚠️ `~/Documents/Claude/.auto-memory/` は接続フォルダ外で読めず（**12日連続**）。youtube-factory 内の `MEMORY_UPDATE_*.md` で代用。
> ℹ️ 実行中（23:00〜）に PDCA/指揮者タスクが並走。`data/reports/2026-09-08/*.json` は `fake-paper` まで生成済み。
> ℹ️ サンドボックスから Mac の localhost:8000 には到達できないため、backend API は叩かず **ログ・DB・設定ファイルの直読み**で判定した。

---

## 0. 今夜の要点（3行）

1. **昨夜の「NEW」3件がすべて閉じた。** 「正体」重複ブロック 114回→**0回**、clip-kaneko の素材枯渇 14回→**0回**、未コミット 164件→**2件**。朝の指揮者コミット `e4f35f1` / `c51c3de` とマージタスクが効いている。
2. **`channel_avg_ctr` の壊れた値（42〜55）が全消去された。** 18件すべて NULL になり、書き戻しループは止まった。長期課題#14 はクローズ。
3. 🚨 **代わりに同型の副作用が再発している。** 09-08朝に入れた `require_answer_marker` が、対象6chで **36本中21本（58%）** しか効いておらず、しかも**助詞が壊れたタイトルが5本公開された**。前回の「数字制約→『正体』収斂」と同じ、制約追加が語を壊すパターン。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 稼働中・要対応 | 09-08 に **21本**（公開7/予約14）。**減少が加速**（33→30→27→21）。13ch中12ch autopilot稼働、ERRORログ0。未コミット 164→**2**・未プッシュ **0→6**。サムネ403は**8夜連続**（本日39本中30本） |
| aiseki | 🟢 進捗あり・人手待ち | 本番 `aisekimatch.com` 正常応答。作業ツリー**クリーン**（未コミット 2→0）・**未プッシュ 2→4**。`migration_referral_guard.sql` の適用スクリプト未掲載は**未解消（3日目）** |
| ai-english-coach | 🔵 凍結 | 実装は 08-18 で停止、**21日間**中身の変化なし。09-08 に HANDOFF 追加のみ。**Gitリモート未設定のまま** |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から変化なし。本番正常応答。未コミット25 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11。`feat/stripe-checkout` は push済み・main へ**未マージ9**。未コミット1。本番は応答するが本文が空 |
| 切り抜きラボ(clip-lab) | 🟡 稼働・**転換ほぼゼロ** | 30日 **42,604再生 / 登録+2**。20:45 viral枠は APIキー未設定で失敗継続 |
| rhythm-pop | ✅ 完成済み | 06-22 以降動きなし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降動きなし。未コミット1・リモート未設定 |

---

## 2. youtube-factory

### 2-1. 直近の変更（`git log --oneline -5`）

```
ffe8440 docs: 全プロジェクトのマージ・整理ログを記録
05e1334 chore: 09-07/09-08 の制作指示実行スクリプトを追加
6cb0fd0 data: 09-06〜09-08 の分析xlsxと全進捗レポートを追加
e96aa60 data: 09-08 の分析・チャンネル設定・シリーズリンク・バイラル翻訳待ちを更新
77546c8 docs: 09-06〜09-08 のメモリ更新ログと HANDOFF を反映
```

- **未コミット 2件**（`retention_insights.json` / `success_patterns.json` — PDCA が今まさに書いている生成物）
- **未プッシュ 6件**（`origin/main` より6コミット先行）。マージタスクが GitHub 認証不可で push できていない
- ブランチは `main` のみ。未マージブランチなし

### 2-2. 制作・投稿

| 日付 | 合計 | 公開 | 予約 |
|---|---:|---:|---:|
| 09-05 | 33 | 8 | 25 |
| 09-06 | 30 | 6 | 24 |
| 09-07 | 27 | 6 | 21 |
| **09-08** | **21** | **7** | **14** |

> ※ 上表は `video_publish.db` から同一基準（`published_at` / `scheduled_at` の日付）で再集計した値。前回レポートの「09-07 = 23本（公開6/予約17）」はその後に予約が4本追加され、現在は27本になっている。日次比較は本表の基準で行うこと。
> ⚠️ **減少は止まっていない。むしろ加速している（-3 → -3 → -6）。** 公開本数は 6→7 に増えたが、予約が 21→14 に落ちた。ただし前例どおり **09-08 の予約は今後増える可能性がある**ので、09-09 の実行時に本日の確定値を取り直すこと。
> ログ上のアップロード完了は **39本**（DBの21本より多いのは長尺とショートの対、および clip系/akashic/fake-paper の別経路分）。

**chごとの30日実績（PDCA 09-08 スナップショット）**

| ch | 30日再生 | 登録 net |
|---|---:|---:|
| company-facts | 44,760 | **+30** |
| clip-lab | 42,604 | +2 |
| 2ch-matome | 40,296 | +8 |
| daily-science | 32,585 | +11 |
| clip-kaneko | 23,671 | +4 |
| clip-fukada | 23,664 | +6 |
| akashic-librarian / clip-animal / fake-paper | 取得不能 | OAuth失効 |

### 2-3. autopilot / スケジューラ

- **13ch中12ch が enabled**（`socio-rx` のみ無効。前回から変化なし）
- backend は本日 **3回再起動**され、`restart_and_trigger_20260908.command` は**実行された**。09-08朝の枠移設は APScheduler に反映済み：

| ch | 変更 | 現在の登録枠 |
|---|---|---|
| company-facts | 13:30 → 19:00 | 08:15 / 17:00 / **19:00** ✅ |
| pokemon-lab | 17:30 → 17:00 | 08:30 / **17:00** / 19:00 ✅ |
| yokai-watch | 17:45 → 17:00 | 09:30 / 12:00 / **17:00** ✅（17:45 は消滅） |

- 本日の **Autopilot 失敗は7件**：clip-animal 4（切り抜ける元動画なし）/ clip-lab 2（`ANTHROPIC_API_KEY` 未設定）/ clip-kaneko 1（LLMフック生成失敗）
- ログ上の `ERROR` レベル 0件。DB整合エラーなし

---

## 3. 前回からの差分

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

| 前回# | 内容 | 実測 |
|---|---|---|
| **N1** | **「正体」へのタイトル収斂とクロスch重複ブロック** | 09-07 **114回** → 09-08 **0回**。commit `e4f35f1`（`cross_channel_gate.py` / `theme_dedup.py` / `title_constraints.py`）で解消。**クローズ** |
| **N3** | **未コミット 164件** | → **2件**。マージタスクが5コミットに整理・`.gitignore` に日次生成物を追加。**クローズ** |
| **#9** | **clip-kaneko「全ての元動画が切り抜き済み」** | 09-07 **14回** → 09-08 **0回**。commit `c51c3de` で解消。**クローズ** |
| **#14** | **サムネA/B `channel_avg_ctr` の回帰・悪化** | 42.82〜55.17 → **18件すべて NULL にクリア**。正常な1件のみ 0.0291（`exhausted`）。**書き戻しループは停止。クローズ** |
| **#5** | **Reddit RSS 429** | 09-07 **152回** → 09-08 **0回**。ただし `REDDIT_CLIENT_ID` 設定によるものか単に取得を試みていないだけかは不明 → **観察に格下げ**（下記△） |
| — | **枠移設の反映** | 3枠すべて APScheduler に登録済みを確認（§2-3） |
| — | **前回レポートの誤り訂正** | 前回「OAuth 13ch正常」と書いたが**誤り**。4ch は09-06〜07で更新が止まっており失効している（下記#5） |

### △ 部分解決

- **#3 `channel_metrics` の詰まり** — 09-04 → **09-05 へ1日前進**。ただし 09-05 は **9ch分のみ**（09-03までは12ch）。`video_metrics` は 09-08分 **351行**を取得済みで、**channel_metrics の経路だけが詰まっている**構図は変わらない。3日欠測。

### ❌ 未解決（継続）

| # | 内容 | 継続 | 本日の実測 |
|---|---|---|---|
| 1 | **サムネイル `thumbnails/set` が HTTP 403**（本人確認未了） | **8夜連続・最優先** | 403発生 **163回** / 対象43動画。本日アップの39本中**403を免れたのは9本のみ（23%）** |
| 2 | `ANTHROPIC_API_KEY` 未設定（`backend/.env` 18行目がコメントアウト） | **8夜連続** | Autopilot失敗3件の直接原因。`series_engine` が **5ch（clip-animal / pokemon-lab / clip-lab / company-facts / fake-paper）で「Claude 未応答」** |
| 3 | `channel_metrics` が 09-05 止まり・9chのみ（3日欠測） | 継続（1日前進） | 上記△ |
| 4 | 画像ブリッジのスレッドURL未登録（`threads.json` が `{}`） | 継続・**悪化** | `pending` **57件**（全て本日分）/ `delivered` **0件** / `failed` **235件**。前回の pending 210 は配送されず **failed 側へ落ちた** |
| 5 | **OAuth 4ch が失効**（clip-animal / socio-rx / fake-paper / akashic-librarian） | 継続 | 9ch は本日 23:00 JST に更新成功。4ch は `updated_at` が 09-06〜09-07 で停止。PDCA が「OAuth 未連携」で3ch分析不能 |
| 6 | GCP OAuth 同意画面が「テスト中」 | **期限当日** | project 844705815004。失効は 09-09 前後 |
| 7 | サムネA/B 18件すべて `monitoring`、切替ゼロ | 継続 | 原因は#1 |
| 8 | clip-lab の転換ほぼゼロ | 継続・**悪化** | 30日 **42,604再生で登録+2**（09-07は35,143再生で+1） |
| 9 | clip-animal 実質停止 | 継続 | OAuth失効で分析すら不能。本日 Autopilot 失敗4回（元動画なし）・公開0本。autopilot は enabled のまま |
| 10 | aiseki: Twilio トライアルのまま / DM自動送信の規約リスク | 継続 | 紹介報酬の支払いが電話番号認証依存 |
| 11 | aiseki: Instagram DM ワーカーが1通も送れない | 継続 | `worker/` にログイン済み cookies ファイルが**存在しない**（未ログイン確定） |
| 12 | ai-english-coach: Gitリモート未設定 | 継続・**21日** | `git remote -v` が空 |
| 13 | `~/Documents/Claude/.auto-memory/` が読めない | 継続・**12日連続** | — |
| 14 | aiseki: `migration_referral_guard.sql` が `apply_migrations.command` に未掲載 | 継続・**3日目** | 適用対象は `migration_launch.sql` / `migration_fixed_join_fee.sql` / `migration_launch2.sql` の旧3本のみ |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨 **`require_answer_marker` が効いておらず、かつタイトルを壊している** | 対象6chの本日公開 **36本中21本（58%）** しか答え提示語を含まない。ch差が極端で **daily-science 6/6 に対し pokemon-lab 3/9**。さらに**助詞が破綻したタイトルが公開された**: 「RTX5090**はで**部屋の外から名前を呼ぶのか」「7日間**でずつ**消えたエージェント名簿異常事件」「…3作品で徹底比較**の本当**」。最後の例は `本当の` を語尾に貼り付けた痕跡で、**マーカーを機械的に挿入している**ことを示す。「7日間でずつ」は 09-07 の数字制約（`forbid_digits`）が「1人」を削った跡。**制約を足すたびに日本語が壊れる、という同じ失敗の3回目**。<br>※ 午前中（変更は10:20完了）に生成された分を含むため 58% は過小評価の可能性がある。**09-09 は全数が変更後の生成になるので、そこで確定判定できる** |
| **N2** | **画像依頼書が `failed` 235件に積み上がった** | 前回 `pending` 210件が配送されないまま失敗側へ移動。`delivered` は依然 **0件**。「滞留」ではなく「失敗として捨てられている」状態に変質した |
| **N3** | **`phase4.db` の `schedules` テーブルが空** | 実際の投稿枠は `data/channels/*.json` 由来で APScheduler に登録されており稼働に実害はないが、Phase4 の予約UIからは枠ゼロに見えるはず。二重管理の残骸の可能性 |
| **N4** | **未プッシュが youtube-factory 0→6 / aiseki 2→4** | マージタスクがコミットまで進めたが、サンドボックスに GitHub 認証情報がなく push 未実施。**ローカルにしか無いコミットが増えた** |
| **N5** | **`.git` 内に `*.lock.stale.*` のゴミ参照が残存** | `git branch` が16行の warning を出す。git の動作には影響しないが、youtube-factory / ai-orchestrator / claude-codex-bridge / fanup / oripa / rhythm-pop に残っている。掃除は Mac 側で `find ~/Developer/<repo>/.git -name '*.stale.*' -delete` |

---

## 4. aiseki

**ステータス**: 🟢 進捗あり・人手待ち

```
1538169 2026-09-08 docs: マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加
1d3f26e 2026-09-08 chore: LibreOffice のロックファイルを .gitignore に追加
a33d809 2026-09-06 紹介ボーナスの量産穴を塞ぎ、SNS投稿用の画像素材とマーケ資料の誤りを直す
af5f442 2026-09-05 広告用LPに料金比較・FAQ・構造化データを足す
e37c670 2026-09-05 招待・DM・電話番号まわりの e2e 検証スクリプトを追加する
```

- 本番 `https://aisekimatch.com` は正常応答（タイトル・OGP・構造化メタ確認）。**Vercel デプロイは生きている**
- **作業ツリーはクリーン**（未コミット 2 → 0）
- **未プッシュ 4コミット**（`origin/main` より4先行）← N4
- 未マージブランチなし（`main` のみ）
- **マイグレーション**: `supabase/` に29本。`migration_referral_guard.sql` は**存在するが `apply_migrations.command` の適用ループに入っていない**（旧3本のみ）。本番DBに当たっているか未確認 — **コード側だけ塞いでDB側が無防備な可能性が3日続いている**
- Instagram DM ワーカー: `worker/` に `dm_worker.mjs` / `instagram.mjs` はあるが**ログイン済み cookies が無い**。1通も送れない状態は変わらず

**次にやるべきこと**: ① `migration_referral_guard.sql` の本番適用確認（最優先）→ ② `git push origin main`（4コミット）→ ③ Twilio 本番アップグレード → ④ Instagram ログイン

---

## 5. ai-english-coach

**ステータス**: 🔵 凍結（実装は 08-18 で停止・**21日**）

```
cd2c8c5 2026-09-08 docs: HANDOFF を追加し一時ファイルを .gitignore に追加   ← マージタスクによる自動コミット
a90c4ad 2026-08-18 docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
d1af467 2026-08-18 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf 2026-08-18 refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 2026-08-18 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
```

- **未コミット 0件**（クリーン）
- **Gitリモートが1つも無い**。21日間ローカルのみ＝**消失リスクが全プロジェクト中で最大**
- 進捗: Phase1（テキスト対話 MVP）と LINE Pay 決済基盤まで完了。Vercel は**未セットアップ**。音声課金は未着手

**次にやるべきこと**: **GitHub リモートを作って push する**（それ以外は凍結でよい）

---

## 6. 全進捗サマリ

| プロジェクト | URL | ステータス | 残タスク |
|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 稼働中・要対応 | 12ch autopilot稼働（socio-rx のみ停止）。OAuth 4ch失効・サムネ403が8夜連続。本日21本制作（減少加速） |
| aiseki | https://aisekimatch.com | 🟢 開発中・人手待ち | マイグレーション適用確認 / push 4件 / Twilio本番化 / Instagramログイン |
| fanup | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | 08-31 から停止。トップに サポーター1,248 / 進行中3件 と表示（実データかシード値かは未確認）。集客施策ゼロ |
| oripa | https://oripa-omega.vercel.app | 🟡 Phase1 MVP・決済未着手 | `feat/stripe-checkout` 未マージ9。08-11 から停止 |
| ai-english-coach | （デプロイなし） | 🔵 凍結 | Phase1テキスト版完了・音声課金未着手。**Gitリモート未設定** |
| 切り抜きラボ (clip-lab) | YouTube | 🟡 稼働・転換ほぼゼロ | 30日 42,604再生で登録+2。viral枠が APIキー未設定で毎日失敗 |
| rhythm-pop | （ローカル） | ✅ 完成済み | 06-22 以降動きなし |
| claude-codex-bridge | （ローカル） | ✅ 完成済み | 07-04 以降動きなし |

---

## 7. ユーザー手動待ちタスク一覧

**期限があるもの（今日・明日）**

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開** — https://console.cloud.google.com/auth/audience （project 844705815004）。**失効は09-09前後＝期限当日**。★順序厳守: ①本番公開 → ②13ch再認可
2. 🚨 **YouTube 13ch の電話番号確認**（youtube.com/verify）— サムネ403の唯一の解。8夜連続、本日も39本中30本が403

**詰まりを一撃で解消するもの**

3. **`ANTHROPIC_API_KEY` を有効化** — `backend/.env` 18行目のコメントを外すだけ。clip-lab の viral枠・clip-kaneko のフック生成・全chの `series_engine` が同時に復旧する
4. **失効した4chの再認可**（clip-animal / socio-rx / fake-paper / akashic-librarian）※ 1 を先に済ませること

**消失リスク**

5. **ai-english-coach の GitHub リモート作成と push**（21日間ローカルのみ）
6. **未プッシュの push** — `cd ~/Developer/youtube-factory && git push origin main`（6件）/ `cd ~/Developer/aiseki && git push origin main`（4件）

**aiseki（公開前の必須条件）**

7. **`migration_referral_guard.sql` が本番DBに当たっているか確認**（3日目）
8. **Twilio を本番アップグレード**
9. **Instagram にログイン**（`cd worker && npm run login`）＋ `/admin/dm` から送信先CSV取り込み

**その他**

10. ChatGPT スレッドURLを13ch分登録（`threads.json` が空・failed 235件）
11. `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加（12日連続で読めず）
12. `REDDIT_CLIENT_ID` の設定（本日429は0回だが未設定のまま）
13. oripa の `feat/stripe-checkout` を main へマージするか判断（未マージ9・push済み）
14. **clip-animal を続けるか止めるか判断**（OAuth失効＋素材枯渇で公開0本）
15. `.git` の `*.stale.*` ゴミ掃除（任意）

---

## 8. 次回（09-09）の実行時に確認すること

- **サムネ403が解消したか**（本人確認の実施有無）
- **OAuth 同意画面が本番公開されたか。されていなければ 9ch も失効しているはず** — 最優先で確認
- **N1: 答え提示語の充足率。** 09-09 は全数が変更後の生成になるので **6chで100%に届くか**が判定できる。届かないなら `title_rules` が backend から読まれていない（09-03 に `title_rules` が死に設定だった前例あり）。**同時に、助詞の壊れたタイトルが再発していないかを目視すること**
- **制作本数。09-08 は 21本（減少が -3/-3/-6 と加速）。まず 09-08 の確定値を取り直し、そのうえで 09-09 が21本を上回るか見る**
- **`channel_metrics` が09-05から前進したか。および ch数が9→12に戻ったか**
- **画像ブリッジ `failed` が235件からさらに増えたか**
- **09-11**: `cta_position` A/B の判定日
- **09-12**: 尺の対照実験の評価日。**それまで対照群の尺に触れない**
- **09-13**: 4行目ルール変更の反証日（scp 23.6 / pokemon 22.0 / yokai 25.0 を下回らなければ棄却）
- **09-15**: 答え提示型100%化の反証期限 — (a) 全体の 登録/千再生 が 0.47 を超えるか (b) 2ch-matome が 0.20→0.35 を超えるか (c) 移設3枠が移設前を下回らないか
- **09-19**: yokai-watch の枠移動の影響評価

---

## 9. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-08.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクトへの書き込み・git 操作（push/merge/commit）・設定変更・外部DB接続は**一切していない。読み取りのみ**。
