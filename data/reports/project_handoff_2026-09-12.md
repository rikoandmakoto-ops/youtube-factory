# 全プロジェクト 引き継ぎレポート — 2026-09-12（土）

**実行日時**: 2026-09-12 23:10 JST / **タスク**: daily-project-handoff
**参照した文脈**: `last_handoff_log.md`(09-11 23:15)、`last_merge_log.md`(09-11 22:20)、`.auto-memory/INDEX.md`・`2026-09-10/11/12.md`・`projects/apps.md`
**書き込み**: 本ファイルと `last_handoff_log.md` のみ。**他プロジェクトは読み取りのみ。git 操作・設定変更・外部送信は一切なし。**

---

## 0. 一行で

**config 側の内部矛盾は 09-12 に片付いた。だが出口（アップロード）は 09-10 07:45 を最後に 63時間ゼロのままで、その間に作った45本が丸ごと積み上がっている。**

---

## 1. ステータス一覧

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🔴 **出口封鎖（3日目）** | 公開 09-11=0本 / 09-12=0本。最終公開 `2026-09-10T07:45` から**約63時間ゼロ**。生成は正常（09-11以降45本すべて completed・failed 0）。OAuth 13ch 全失効。未push **17→22コミット** |
| aiseki | 🟢 進捗停止・人手待ち | 最終コミット 09-08 22:08 から**4日連続コミット0**。作業ツリーはクリーン。未push 4件（5日連続）。https://aisekimatch.com 稼働確認 |
| ai-english-coach | 🔵 凍結 | コード最終変更 08-18＝**25日**停止（09-08 のコミットは docs のみ）。未コミット0。**Gitリモート未設定のまま（25日）** |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から**12日**変化なし。未コミット25件。サイト稼働確認 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11＝**32日**。`feat/stripe-checkout` に居たまま未マージ。未コミット1 |
| 切り抜きラボ(clip-lab) | 🟡 稼働・転換ほぼゼロ | 30日窓（〜09-05）で 42,604再生に対し登録**+2**（0.047/千）。clip-animal は同窓で**再生17・登録0**なのに autopilot ON |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし。未コミット19件・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし。未コミット1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | 09-08 `b9b84d1`。未コミット4・origin と同期済み。Vercel Cron 30分ごと |

### URL と疎通結果（今回実測）

| プロジェクト | URL | 疎通 | 補足 |
|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | ✅ 200 | `/login` へリダイレクト。管理パネルは生きている |
| aiseki | https://aisekimatch.com | ✅ 200 | タイトル・OGP 正常 |
| fanup | https://fanup-rouge.vercel.app | ✅ 200 | サポーター1,248 / 進行中3 / 達成8 を表示 |
| oripa | https://oripa-omega.vercel.app | ⚠️ **未確認** | 本文が空で返り、追加パスは provenance 制限で取得不可。次回 URL を明示して再確認する |
| ai-english-coach | （未デプロイ） | — | Phase 1 テキスト版のみ。LINE / Vercel は人手待ち |
| 切り抜きラボ（clip-lab） | YouTube ch | — | 下の §2-3 の表を参照 |
| rhythm-pop | （未デプロイ） | — | 完成済み・リモート未設定 |
| claude-codex-bridge | （ローカルskill） | — | 完成済み・リモート未設定 |

---

## 2. youtube-factory（詳細）

### 2-1. 直近の変更（`git log --oneline -5`）

```
88d1a18 09-12 データ更新: チャンネル設定・分析/PDCAメモリ・トレンド・レポート・制作トリガ
7b226a3 台本: 各チャンネルの新規シナリオとアーカイブを追加（9ch分）
964c926 レポート追加: 09-12 指揮者レポート(xlsx 5シート)と .auto-memory の学びを記録
64f919b 指揮者 09-12: 切り抜き3chへゲート付与し、キュー補充をtitle_constraintsに通す
32197ee fix: 09-11 の5件を構造で潰す — title_gate / patch_channel_file / title_lexicon / topic_only
```

- **未コミット10件**（23:18 時点）:
  - 22:34 の PDCA 出力4件 — `data/analytics/retention_insights.json` / `success_patterns.json` / `data/reports/latest.md` / `pdca_history.xlsx`
  - 23:1x に**別タスクが更新した** `.auto-memory` 4件 — `2026-09-12.md` / `INDEX.md` / `projects/apps.md` / `projects/youtube_channels.md`（本タスク開始時の 23:10 にはクリーンだった）
  - 本タスクの出力2件 — `data/reports/last_handoff_log.md` / `project_handoff_2026-09-12.md`
  - いずれも成果物。次回マージタスクでコミット対象。
- **未マージブランチ**: `orch-20260911-followup`（09-11 から継続。`data/channels/2ch-matome.json` の `theme_queue` でコンフリクト。判断待ち）
- **未 push**: **22コミット**（origin/main に対し先行。09-11 は17件）

### 2-2. autopilot と公開状況

| ch | autopilot | ゲート | キュー | ゲート適合 |
|---|:--:|:--:|--:|--:|
| 2ch-matome | ON | ✅ | 18 | 16 (89%) |
| akashic-librarian | ON | ✅ | 12 | 12 (100%) |
| clip-animal | ON | ❌未設定 | 14 | — |
| clip-fukada | ON | ✅ | 32 | 29 (91%) |
| clip-kaneko | ON | ✅ | 38 | 34 (89%) |
| clip-lab | ON | ✅ | 33 | 29 (88%) |
| company-facts | ON | ✅ | 19 | **0 (0%)** |
| daily-science | ON | ✅ | 14 | **0 (0%)** |
| fake-paper | ON | ✅ | 10 | 10 (100%) |
| pokemon-lab | ON | ✅ | 16 | 7 (44%) |
| scp-lab | ON | ✅ | 10 | 9 (90%) |
| socio-rx | OFF（休止） | ❌未設定 | 13 | — |
| yokai-watch | ON | ✅ | 27 | 9 (33%) |
| **計** | 12ch稼働 | 11ch | **256** | **155 (60.5%)** |

**日別公開本数（`data/video_publish.db`）**

| 日 | 本数 |
|---|---:|
| 09-12 | **0** |
| 09-11 | **0** |
| 09-10 | 2 |
| 09-09 | 2 |
| 09-08 | 21 |
| 09-07 | 27 |
| 09-06 | 30 |

- 生成側は健全: 09-11以降の45ジョブが**全件 completed**（新規 failed 0）。キュー全体 623件中 completed 615 / failed 7（全て旧いもの）/ **queued 0**。
- 失敗理由はすべて `自動公開スキップ — トークン失効のため要再認可`（`logs/backend.log` 末尾3MB窓で45件。**ログ行に日付が無いため日次件数ではなく窓内件数**）。
- サムネ `thumbnails/set` の403は**検出0件だが、公開が0なので呼ばれていないだけ＝判定不能**（09-11 と同じ扱い）。

### 2-3. 認証・データ

- **OAuth 13ch 全失効**。`expires_at` は最新でも **09-09 23:43 JST**（約71時間前）、`updated_at` は全件 `expires_at + 8h` のまま＝**リフレッシュ成功歴ゼロ**。PDCA レポートも13ch全て「失効／Token has been expired or revoked.」。
- **`video_metrics` は 09-08 が最後**（09-09〜09-12 の4日分が0行）。
- **`channel_metrics` は 09-05 が最後**（7日欠測）。**登録者数が出せない**ため、下の30日窓は **08-10〜09-05** の実測。

**30日窓（`channel_metrics` 実測・〜09-05）の ch別 登録/千**

| ch | 再生 | 登録 | 登録/千 |
|---|---:|---:|---:|
| scp-lab | 34,284 | +37 | **1.079** |
| company-facts | 44,757 | +35 | 0.782 |
| akashic-librarian | 5,259 | +4 | 0.761 |
| daily-science | 29,578 | +21 | 0.710 |
| yokai-watch | 31,140 | +16 | 0.514 |
| pokemon-lab | 32,536 | +11 | 0.338 |
| 2ch-matome | 40,291 | +13 | 0.323 |
| clip-fukada | 23,664 | +6 | 0.254 |
| clip-kaneko | 23,671 | +6 | 0.253 |
| fake-paper | 7,030 | +1 | 0.142 |
| clip-lab | 42,604 | +2 | **0.047** |
| clip-animal | 17 | 0 | 0.000 |
| **合計** | **314,831** | **+152** | **0.483** |

> ⚠️ この表は `channel_metrics`（〜09-05）基準。`.auto-memory` にある 0.423 / 0.461 等は `video_metrics`（〜09-08）基準で**窓もソースも違う**ので直接比較しないこと。倍率を引用するときは必ず**窓・ソース・ch構成**を書く。

### 2-4. PDCA で検出された課題の対応状況

| 09-12 昼の対処 | 23:10 時点の生存 |
|---|---|
| 切り抜き3ch（clip-lab / fukada / kaneko）へ `hard_constraints` 新規付与 | ✅ 生存。3ch とも `is_enforced()` が True |
| company-facts のキューから絵文字除去 | ✅ 生存。19件に絵文字違反0（残る不合格は全て `min_effective_chars`） |
| `min_effective_chars=20` の8ch適用（09-11） | ✅ **全ch生存**（適用から約33時間・自動runが16:15〜20:15 に config を書いた後も残存）→ **config 上書き事故は止まったと確定してよい** |
| キュー補充を `title_constraints` に通す（`_annotate_title_gate`） | ⚠️ **ディスク上では確認できず**（下の N5） |

---

## 3. aiseki（詳細）

- **git**: main のみ。最終コミット `1538169`（09-08 22:08）。**未コミット0・未マージブランチなし**。origin/main に対し**4コミット先行（push 未完・5日連続）**。
- **直近5件**: マーケ資料（DMテンプレ・SNS・競合分析）追加 / LibreOffice ロックを .gitignore / 紹介ボーナスの量産穴を塞ぐ / 広告LPに料金比較・FAQ・構造化データ / 招待・DM・電話番号の e2e 検証スクリプト。
- **マイグレーション**: `supabase/*.sql` の最新は `migration_referral_guard.sql`（**09-06**）。09-11 の確認以降に**新規 SQL は増えていない**ため、未適用分の新規発生はなし（適用可否は Supabase 側でしか確認できないのでサンドボックスからは判定不能）。
- **デプロイ**: https://aisekimatch.com が 200 で応答（タイトル・OGP 正常）。
- **公開前ブロッカー（HANDOFF.md 準拠・変化なし）**: Twilio トライアル / Instagram `sessionid` 未取得でDMワーカーが流れない / 実機確認・運営体制（通報対応者・営業許可・本店所在地）未確定 / Stripe は live 有効だが実課金テスト未実施。

---

## 4. ai-english-coach（詳細）

- **git**: main（他に `_locktest`。main に取り込み済みでマージ不要）。最終コミット `cd2c8c5`（09-08 22:08、**docs: HANDOFF 追加のみ**）。**実コードの最終変更は 08-18＝25日停止**。
- **未コミット0**。
- **`git remote -v` が空（25日）** — ローカルにしか存在しない。バックアップ不在のリスクが継続。
- Phase 1（テキスト版）完了。音声・課金は未着手。LINE公式 / LINE Pay / Supabase / Vercel / OpenAIキー / Webhook 疎通がすべて人手待ち。

---

## 5. 前回（09-11）からの差分

### ✅ 解決を確認（次回「要対応」として報告しないこと）

- **config 上書き事故** → **クローズ。** 09-11 は適用11分後に消えたが、今回は約33時間・自動run 4回を挟んでも8ch全てで `min_effective_chars=20` が生存。`patch_channel_file` への書き込み集約（`32197ee`）が効いている。
- **切り抜き3chのゲート未設定** → 解決（09-12 に付与、生存確認）。残る未設定は clip-animal と socio-rx（休止ch）。
- **company-facts のキュー全件不合格（絵文字による自滅）** → 解決。絵文字違反は0件。
- **生成パイプラインの失敗** → 該当なし。09-11以降45ジョブ全件 completed・queued 0。
- **`.git/index.lock` による git 停止** → 実害なし（`git log`/`status` は通る）。ただしファイル自体は再び残存（下の N4）。
- **レンダ速度・`job_queue.json` の永続化破壊** → 再発なし。

### ⚠️ 前回レポートの記載を訂正

- 09-11 レポートで「**`viral_translation_pending` に15件滞留 → 解決（ディレクトリ消滅）**」と書いたのは**誤り**。ディレクトリは存在し、**現在17件**（08-31〜09-12、+1/日で微増）。`ANTHROPIC_API_KEY` 未設定が原因なので、**未解決として扱うのが正しい**。

### ❌ 継続（未解決）

| # | 内容 | 継続日数 | 09-12 23:10 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」（project 844705815004） | 期限超過 | 未対応。全失効の根本原因 |
| 2 | YouTube 13ch の再認可 | **5日** | 13ch すべて失効。`updated_at` は 09-10 07:43 が最新 |
| 3 | `ANTHROPIC_API_KEY` 未設定（`backend/.env` 18行目） | **13夜連続** | コメントアウトのまま |
| 4 | `video_metrics` の欠測 | **4日** | 最終 09-08 |
| 5 | `channel_metrics` の欠測 | **7日** | 最終 09-05。登録者数が出せない |
| 6 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 / images 0 |
| 7 | clip-lab の転換ほぼゼロ | 継続 | 42,604再生で登録+2（0.047/千） |
| 8 | clip-animal 実質停止なのに autopilot ON | 継続 | 30日窓で再生17・登録0。**ゲートも未設定** |
| 9 | aiseki: Twilio トライアル / Instagram DM ワーカー未ログイン | 継続 | 変化なし |
| 10 | ai-english-coach: Gitリモート未設定 | **25日** | `git remote -v` が空 |
| 11 | fanup 25件 / rhythm-pop 19件 の未コミット | 継続 | 変化なし |
| 12 | oripa `feat/stripe-checkout` 未マージ | **32日** | 変化なし |
| 13 | `logs/backend.log` のローテーション未実装 | 継続 | **82,740,449 バイト（≒79MiB／82.7MB）**。⚠️ 過去ログの「81MB」「79MB」は単位（MiB/MB）が混在しているので、**今後はバイト数で記録すること** |
| 14 | 横断テーマゲートの多発 | 継続 | 末尾3MB窓で50件（※下の N8 の注記参照） |
| 15 | サムネ `thumbnails/set` の403 | 判定保留 | 公開0のため判定不能（3日連続で保留） |
| 16 | `orch-20260911-followup` のマージコンフリクト | **2日** | 未解決のまま |
| 17 | `test_fixes_20260912.py` の赤4件 | 継続 | 09-12 昼時点で未修正（本タスクでは pytest 未実行） |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨🚨 **公開ゼロが3日連続（09-10 の2本が最後）** | 最終公開 `2026-09-10T07:45:22` から**約63時間**。09-11=0 / 09-12=0。09-06 は30本だった |
| **N2** | 🚨 **未 push が 17 → 22コミットに増加** | 4日連続 push 失敗。増分は 09-12 の指揮者コミット5件。消失リスクが積み上がる一方 |
| **N3** | 🚨 **09-11以降に作った45本が全て未公開のまま滞留** | 09-11以降のジョブ45件が**全件 completed**。09-09〜09-12 のジョブは計91件で、同期間の公開は4本＝**未公開はおよそ87本規模**（ジョブ数ベースの概算）。再認可の瞬間に一気に流れる／あるいは鮮度を失う |
| **N4** | ⚠️ **画像ブリッジ pending が 296 → 370（+74/日）** | delivered 依然0・failed 235 で据え置き。滞留が加速継続 |
| **N5** | ⚠️ **`title_gate_ok` の印が `data/channels/*.json` に1件も無い（256件中0件）** | 09-12 昼のコミット `64f919b` **時点でも0件**。つまり今日の退行ではなく、**印が最初からディスクに残らない実装**。指揮者が「補充の何割が落ちたか」を毎日観測する当初の目的が果たせていない |
| **N6** | ⚠️ **キュー不合格74件・違反76件のうち58件（76%）が `min_effective_chars`。うち32件は18〜19字＝あと1〜2字** | ゲート適用229件中 不合格74件。違反内訳は `min_effective_chars` 58 / `banned_words` 11 / `require_any_of` 7。company-facts 0/19・daily-science 0/14・yokai-watch 9/27 が全滅〜低位。例「なぜ寒いと尿意が近くなるのか」14字 /「ワークマンが客層を入れ替えた本当の理由」19字。**下限20字そのものは 09-11 の実測（25-29字が頂点）に沿っており、直すべきは生成側のプロンプト**（機械 repair は禁止＝09-12 実測で日本語が壊れる） |
| **N7** | ⚠️ **`tmp_obj_*` が 810 → 997、`stale_locks/` が 45 → 61 に増加** | サンドボックスから unlink 不可のため増える一方。`.git/index.lock` も再び残存 |
| **N8** | ℹ️ **横断テーマゲートの発動が 25 → 50件（参考値）** | ⚠️ **数え方の注意**: `横断` を含むログ行に日付が入っていないため**日次では数えられない**。今回は `backend.log` 末尾3MB窓（09-11〜の範囲）で50件。前回の「25回」と同一方法である確証が無いので、**倍増と断定せず観測値として置く**。テーマ枯渇の兆候ではあるが、公開0で新規実績が無いため**今は対処せず観測にとどめる**（鉄則どおり） |

---

## 6. 次にやるべきこと

### youtube-factory

1. 🚨🚨 **GCP OAuth 同意画面を「テスト中」→「本番」に公開**（project 844705815004 / https://console.cloud.google.com/auth/audience）。**必ずこれを先に。** 逆順だと再認可しても7日でまた全滅する。
2. 🚨🚨 **YouTube 13ch を再認可**（ダッシュボード → チャンネル設定 →「YouTube 連携」）。これが直るまで指揮者タスクは同じ 09-08 データの再解釈しかできず、09-15 の反証期限も判定不能になる。
3. 🚨 **push**（4日連続失敗・**22コミット**）: `cd ~/Developer/youtube-factory && git push origin main`
4. 🚨 `backend/.env` 18行目の `ANTHROPIC_API_KEY` を有効化（13夜連続）。切り抜き系の「作れていない枠」と viral 17件の滞留がこれ1行で止まっている。
5. 再認可後に**約87本規模の未公開在庫をどう流すか**決める（一気に出すか、日次上限を保つか）。
6. N6 の対処は**生成プロンプト側**で（機械 repair は禁止。09-12 実測で日本語が壊れる）。
7. `orch-20260911-followup` のマージ方針決定（main 側＝エントリ削除済みの採用が妥当に見える）。
8. `logs/backend.log`（82,740,449 バイト ≒79MiB）のローテーション。

### aiseki

9. `cd ~/Developer/aiseki && git push origin main`（4コミット・5日連続）
10. Instagram ログイン（`cd worker && npm run login`）/ Twilio 本番アップグレード / `dm_targets` の CSV 取り込み / SNSアカウント開設 / live で1回購入して確認 / サインアップの CAPTCHA
11. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（09-11 から継続）

### ai-english-coach

12. GitHub リモートの作成と push（**25日ローカルのみ**）
13. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通

### 環境の掃除（Mac 側でないと消せない）

14. `rm -f .git/*.lock .git/refs/heads/*.lock`
15. `tmp_obj_*` **997件** / `stale_locks/` **61** / `_stale/` / `_stale_junk/`

### 判断が要るもの

16. clip-animal を続けるか止めるか（30日窓で再生17・登録0。ゲートも未設定）
17. 切り抜き3chの縮小判断（0.047〜0.254/千 vs ゆっくり系 0.32〜1.08）※データ復旧後
18. oripa `feat/stripe-checkout` を main へマージするか（32日放置）
19. fanup 25件 / rhythm-pop 19件 の未コミット整理（任意）
20. ChatGPT スレッドURLの13ch分登録 / `REDDIT_CLIENT_ID` / 画像ブリッジ pending 370・failed 235 の処理方針

---

## 7. 次回（09-13）の実行時に確認すること

- **再認可されたか**（`youtube_tokens.db` の `updated_at` が 09-12 以降か）
- **公開本数が戻ったか**（09-11・09-12 は0本。09-06 は30本）
- **`video_metrics` に 09-09 以降の行が入ったか**（4日欠測）／**`channel_metrics` が 09-05 から進んだか**（7日欠測）
- **push が通ったか**（youtube-factory 22 / aiseki 4）
- **サムネ403の再発件数**（3日連続で判定保留）
- **画像ブリッジ pending が減ったか**（370件・+74/日で加速中）
- **キューのゲート適合率**（今回 60.5%＝155/256。**昼の 33.3%＝33/99 とは母集団が違うので直接比較しない**）
- **09-15**: 答え提示型100%化の反証期限 / **09-16**: 「実は」出現率 / **09-19**: yokai-watch 枠移動 / **09-20**: 09-09 施策の評価
  → ⚠️ **全てデータ復旧が前提。09-13 中に復旧しないと 09-15 の判定は不能になる。**
