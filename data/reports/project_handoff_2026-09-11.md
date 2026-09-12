# 全プロジェクト 引き継ぎレポート — 2026-09-11

**実行日時**: 2026-09-11 23:15 JST（scheduled task: `daily-project-handoff`）
**前回**: 2026-09-10 23:15
**参照した文脈**: `last_handoff_log.md`(09-10)、`last_merge_log.md`(09-11 22:20)、`.auto-memory/INDEX.md`、`.auto-memory/2026-09-11.md`

> ℹ️ 今回も bash が完走。git・sqlite・ログ・スケジューラ・サイト疎通をすべて実測で取得した。

---

## 0. 一行で言うと

**出口（YouTube 公開）が 40時間止まったまま、入口（生成）だけが毎日24本動き続けている。**
09-11 の公開は **0本**。最後の公開は **09-10 07:45 JST**。原因は 09-08 から続く OAuth 全13ch 失効で、
**ユーザーの手作業（GCP の同意画面公開 → 13ch 再認可）以外に解決手段がない。**

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🔴 **出口封鎖（悪化）** | 09-11 の公開 **0本**（09-10 は2本）。最終公開 09-10 07:45 から**約40時間ゼロ**。生成は24本 completed で正常。未 push が **8→17コミットに倍増** |
| aiseki | 🟢 進捗停止・人手待ち | コミット0が **3日連続**（最終 09-08 22:08）。作業ツリークリーン。未 push 4件（4日連続）。https://aisekimatch.com 稼働確認 |
| ai-english-coach | 🔵 凍結 | コード最終変更 08-18＝**24日**停止。未コミット0。**Git リモート未設定のまま** |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から12日変化なし。未コミット25件。サイト稼働（サポーター1,248 / 進行中3件） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11＝**31日**。`feat/stripe-checkout` 未マージのまま。未コミット1 |
| 切り抜きラボ(clip-lab) | 🟡 稼働・**転換ほぼゼロ** | 30日 43,389再生で登録 **+2**（0.046/千）。全ch中ワースト。変化なし |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし。未コミット19件・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし。未コミット1・リモート未設定 |

---

## 2. youtube-factory 詳細

### 2.1 autopilot 状態（実測: `data/channels/*.json`）

| 状態 | ch |
|---|---|
| autopilot = **ON**（12ch） | 2ch-matome / akashic-librarian / clip-animal / clip-fukada / clip-kaneko / clip-lab / company-facts / daily-science / fake-paper / pokemon-lab / scp-lab / yokai-watch |
| autopilot = OFF（1ch） | socio-rx |

⚠️ **clip-animal が ON のまま**（30日で再生17・登録0）。計算資源だけを消費している。

### 2.2 公開状況 — `data/video_publish.db`

| 日 | 公開本数 |
|---|---:|
| 09-03 | 12 |
| 09-04 | 25 |
| 09-05 | 33 |
| 09-06 | 30 |
| 09-07 | 27 |
| 09-08 | 21 |
| 09-09 | 2 |
| 09-10 | 2 |
| **09-11** | **0** |

- 最終公開: **2026-09-10 07:45:22 JST**（`max(published_at)`）。以後 **約40時間ゼロ**。
- DB 内の全690行はすべて `published`。**queued/failed が無いのは「試みてすらいない」から**で、健全の証拠ではない。

### 2.3 生成状況 — `data/job_queue.json`

| 日 | ジョブ数 |
|---|---:|
| 09-06〜09-08 | 各 24 |
| 09-09 | 22 |
| 09-10 | 24 |
| **09-11** | **24** |

- 全602ジョブ: **completed 594 / failed 7 / cancelled 1 / queued 0**。滞留なし。
- failed 7件は 05月〜08月の古いものと 09-09 の再起動由来2件のみ。**09-11 の新規失敗はゼロ**。
- **つまり「作れているが上げていない」が4日目に入った。** 09-09 以降に作った約70本が出口で捨てられている。

### 2.4 OAuth（根本原因）

`data/youtube_tokens.db` 実測（2026-09-11 23:10 JST 時点）— **13ch すべて失効**。トークンの更新時刻も 09-09 以前で止まっており、**再認可は行われていない**。

| ch | expires_at (UTC) | 判定 |
|---|---|---|
| 2ch-matome | 09-09 08:13 | 失効 |
| pokemon-lab | 09-09 14:43 | 失効 |
| company-facts | 09-09 06:55 | 失効 |
| daily-science | 09-08 18:56 | 失効 |
| scp-lab / yokai-watch / clip-lab / clip-kaneko / clip-fukada | 09-08 06:00 | 失効 |
| fake-paper | 09-06 17:20 | 失効 |
| akashic-librarian | 09-06 19:52 | 失効 |
| clip-animal / socio-rx | 09-06 06:00 | 失効 |

- 直近ログ2MB 中に `invalid_grant` が **455回**、自動公開スキップが **30回**。
- `data/reports/latest.md`（09-11 22:30 生成）も13ch全てを「失効・要再認可」と表示。

### 2.5 データ欠測

| テーブル | 最終日 | 欠測 |
|---|---|---|
| `video_metrics` | 2026-09-08 | **4日**（09-09/10/11 が0行） |
| `channel_metrics` | 2026-09-05 | **6日** |

→ 登録者数は `latest.md` でも全ch「—」。**登録者ソースが取得できないため、チャンネル別登録者数は本レポートでも出せない。**
→ 指揮者タスクは4日連続で「同じ 09-08 スナップショットの再解釈」しかできていない。

### 2.6 レンダリング環境（`latest.md` 09-11 22:30 実測）

| 指標 | 実測 | 健全域 | 判定 |
|---|---|---|---|
| 1080x1920 合成1回 | 15ms | < 60ms | ✅ |
| load average / コア | 0.2 | < 2.0 | ✅ |
| swap 使用率 | **91%** | < 50% | 🚨 |
| 空きメモリ | **73MB** | > 512MB | 🚨 |

総合判定 **critical**。ただし前回（swap 96% / 72MB）からわずかに改善。レンダ速度自体は正常域を維持しており、**09-10 に解決した「レンダ150〜800倍遅い」問題の再発はない**。

### 2.7 git

- ブランチ: `main`、**origin/main に対し 16 → 17コミット先行**（前回8 → 倍増）。push は4日連続で失敗中。
  ※ 本タスク実行中（23:15頃）に `nightly-full-progress` が `fca8503`「docs(.auto-memory): 09-11 夜の全進捗を記録し projects/ を新設」を追加したため、計測中に16→17へ増えた。
- 未マージ: **`orch-20260911-followup`**（3コミット）。09-11 22:20 のマージタスクが `data/channels/2ch-matome.json` の `theme_queue` でコンフリクトし、指示どおり強制せず中止。
- 未コミット: 22:30 の PDCA 生成物4件（`data/analytics/retention_insights.json` / `success_patterns.json` / `data/reports/latest.md` / `pdca_history.xlsx`）＋ 同時刻に走った `nightly-full-progress` の `.auto-memory/` 差分。
- `.git` のゴミ: `tmp_obj_*` **約810件**（実測 807 → 本タスク実行中に 816 へ増加。前回550 → **+260以上**）/ `*.stale.*` 68件 / `stale_locks/` 45件 / `_stale/` 8件 / `_stale_junk/` 14件 / `HEAD.lock` 1件。

### 2.8 PDCA で検出された課題の対応状況

| 課題 | 状態 |
|---|---|
| `ANTHROPIC_API_KEY` 未設定 | ❌ **12夜連続**。`backend/.env` 18行目でコメントアウトのまま。本日も9回スキップ |
| 画像ブリッジ | ❌ **悪化**。pending **296件**（前回215 → +81）/ failed 235 / delivered **0** / images 0 / `threads.json` は `{}` |
| `viral_translation_pending` 15件滞留 | ✅ **解消**。ディレクトリごと消えている（09-11 のマージ整理で処理済み） |
| 横断テーマゲート | ⚠️ 本日25回発動（前回24回）。テーマ枯渇の兆候は継続 |
| `logs/backend.log` | ❌ **81MB**（前回79.7MB）。ローテーション未実装 |
| min_effective_chars（09-11 朝の施策） | ⏸ **効果検証不能**。09-11 以降の公開が0本のため、検証は再認可後に持ち越し |

---

## 3. aiseki 詳細

- **開発進捗**: 最終コミット `1538169`（09-08 22:08）「マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加」。**09-09/10/11 の3日間コミットゼロ**。
- **直近5コミット**:
  ```
  1538169 docs: マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加
  1d3f26e chore: LibreOffice のロックファイルを .gitignore に追加
  a33d809 紹介ボーナスの量産穴を塞ぎ、SNS投稿用の画像素材とマーケ資料の誤りを直す
  af5f442 広告用LPに料金比較・FAQ・構造化データを足す
  e37c670 招待・DM・電話番号まわりの e2e 検証スクリプトを追加する
  ```
- **未マージブランチ**: なし（`main` のみ）。
- **未コミット変更**: 0件（クリーン）。
- **未 push**: **4コミット**（4日連続で滞留）。
- **未適用マイグレーション**: **該当なし**。`supabase/` 配下に20個の `migration_*.sql` があるが、HANDOFF.md 上ではすべて適用済み扱い。前回から変化なし。残るのは `apply_migrations.command` への未登録のみ（低優先）。
- **Vercel デプロイ**: https://aisekimatch.com は 200 で応答、OG/構造化データ含め正常配信を確認。
- **公開前の残タスク**（HANDOFF.md §5・人手が必要なもののみ）: 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）/ live での実課金テスト1回 / Instagram DM ワーカーのログイン / Twilio 本番アップグレード / `dm_targets` の CSV 取り込み / SNS アカウント開設 / サインアップの CAPTCHA。

---

## 4. ai-english-coach 詳細

- **開発進捗**: **凍結**。コード（`*.ts`/`*.tsx`/`*.js`/`*.json`）の最終変更は **2026-08-18 22:14** — **24日間停止**。以後の `cd2c8c5` はドキュメント追加のみ。
- **直近5コミット**:
  ```
  cd2c8c5 docs: HANDOFF を追加し一時ファイルを .gitignore に追加
  a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
  d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
  99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
  eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
  ```
- **未コミット変更**: 0件（クリーン）。
- **ブランチ**: `main` / `_locktest`。`_locktest` は main に取り込み済みで実害なし。
- ❌ **Git リモート未設定（24日）** — `git remote -v` が空。**ローカルにしか存在しない**。
- Phase 1（テキスト版）は実装完了。残りは環境構築（LINE公式アカウント・LINE Pay加盟店申込・Supabase・Vercel・OpenAI キー・Webhook 疎通）と実機確認で、**すべてユーザーの手作業**。音声課金は Phase 2 として未着手。

---

## 5. 全進捗サマリ

| プロジェクト | URL | ステータス |
|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🔴 稼働中だが**公開停止4日目**。autopilot 12ch ON / 1ch OFF（socio-rx）。**登録者数は OAuth 失効のため取得不能**（09-08 スナップショットの登録/千: scp-lab 0.791 / company-facts 0.715 / akashic 0.570 / daily-science 0.467 / yokai-watch 0.463 / pokemon-lab 0.272 / clip-fukada 0.211 / 2ch-matome 0.199 / clip-kaneko 0.169 / clip-lab 0.024 / fake-paper 0.000） |
| aiseki | https://aisekimatch.com | 🟢 サイト稼働。開発は09-08で停止。残タスクは実機確認・運営体制・実課金テスト・Instagram/Twilio |
| fanup | https://fanup-rouge.vercel.app | 🟡 MVP完了・**集客未着手**。サイト稼働（サポーター1,248 / 進行中3件 / 達成8ch）。08-31 以降コード変更なし |
| oripa | https://oripa-omega.vercel.app | 🟡 Phase 1 MVP・**決済未着手**。応答はあるがクライアント描画で本文取得不可。`feat/stripe-checkout` が31日未マージ |
| ai-english-coach | （未デプロイ） | 🔵 Phase 1 テキスト版完了・**音声課金未着手**。24日凍結・Git リモート未設定 |
| 切り抜きラボ (clip-lab) | youtube-factory 内 | 🟡 稼働中。30日 43,389再生 / 登録 **+2**（0.046/千）。他の切り抜き2chは clip-kaneko 23,671再生+6 / clip-fukada 23,664再生+6。**clip-animal は30日で再生17・登録0（実質停止）** |
| rhythm-pop | — | ✅ 完成済み。06-22 以降変化なし。未コミット19件・リモート未設定 |
| claude-codex-bridge | — | ✅ 完成済み。07-04 以降変化なし。未コミット1件・リモート未設定 |

---

## 6. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **前回N4「`viral_translation_pending` に翻訳依頼書が15件滞留」→ 解決。** ディレクトリごと消えている。
- **前回N5「`.git/index.lock` が残存」→ 解消。** `index.lock` は無くなった（現在残るのは `HEAD.lock` 1件のみ）。
- **09-10 に解決した「レンダ150〜800倍遅い」→ 再発なし。** 合成1回 15ms・load 0.2 で健全域を維持。
- **`job_queue.json` の永続化破壊 → 再発なし。** queued 0・09-11 の新規失敗0。
- **aiseki の未適用マイグレーション → 引き続き該当なし。**
- **`.auto-memory` が読めない問題 → クローズ済み**（repo 内に移設済み・今回も正常に読めた）。

### ❌ 未解決（継続）

| # | 内容 | 継続日数 | 09-11 の実測 |
|---|---|---|---|
| 1 | **GCP OAuth 同意画面が「テスト中」**（project 844705815004） | 期限超過 | 未対応。全失効の根本原因 |
| 2 | **YouTube 13ch の再認可** | **4日** | 13ch すべて `invalid_grant`。トークン更新時刻は 09-09 以前のまま |
| 3 | `ANTHROPIC_API_KEY` 未設定（`backend/.env` 18行目） | **12夜連続** | 本日9回スキップ。clip-lab バイラル枠 / clip-kaneko フック / PDCA の Claude 分析が全停止 |
| 4 | `video_metrics` の欠測 | **4日** | 最終 09-08 |
| 5 | `channel_metrics` の欠測 | **6日** | 最終 09-05。登録者数が出せない |
| 6 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` のまま。delivered 0 / images 0 |
| 7 | clip-lab の転換ほぼゼロ | 継続 | 30日 43,389再生で登録+2 |
| 8 | clip-animal 実質停止なのに autopilot ON | 継続 | 30日で再生17・登録0 |
| 9 | aiseki: Twilio トライアル / Instagram DM ワーカー未ログイン | 継続 | 変化なし |
| 10 | ai-english-coach: Git リモート未設定 | **24日** | `git remote -v` が空 |
| 11 | fanup 25件 / rhythm-pop 19件 の未コミット | 継続 | 変化なし |
| 12 | oripa `feat/stripe-checkout` 未マージ | **31日** | 変化なし |
| 13 | `logs/backend.log` のローテーション未実装 | 継続 | 81MB |
| 14 | 横断テーマゲートの多発（テーマ枯渇の兆候） | 継続 | 本日25回（前回24回） |
| 15 | サムネイル `thumbnails/set` の HTTP 403 | **判定保留** | 直近ログでの検出**0件**。ただし**公開自体が0本でサムネ設定が一度も呼ばれていない**ため、解決とは言えない。再認可後に再測すること |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨🚨 **公開が完全にゼロになった（09-11: 0本）** | 09-09=2 / 09-10=2 と細々続いていた公開が本日ついて0。最終公開 `2026-09-10T07:45:22`（`video_publish.db`）から**約40時間ゼロ**。09-08 の21本と比べて壊滅 |
| **N2** | 🚨 **未 push が 8 → 17コミットに倍増** | 09-11 のマージタスクが6コミット＋ログ1、夜の進捗タスクが1を積んだが push は認証不可で失敗。**4日連続**。ローカルのみに17コミット分の成果がある＝消失リスクが倍増 |
| **N3** | ⚠️ **画像ブリッジ pending が 215 → 296（+81／日）** | delivered は依然0。滞留が加速している |
| **N4** | ⚠️ **`.git/objects` の `tmp_obj_*` が 550 → 約810（+260以上）** | 中断した git 操作のゴミ。サンドボックスからは `unlink` 不可のため増え続ける一方（本タスクの数分間でも 807→816 に増えた） |
| **N5** | ⚠️ **マージがコンフリクトで中断したまま**（`orch-20260911-followup`） | 09-11 22:20 のマージタスクが `data/channels/2ch-matome.json` の `theme_queue` で衝突。強制せず中止。**手動判断待ち** |
| **N6** | ℹ️ **生成24本／公開0本の非対称が定常化** | 09-09 以降に作った約70本が未公開。レンダとストレージのコストだけが積み上がっている。**再認可までは autopilot を絞る判断もありうる** |

---

## 7. ユーザー手動待ちタスク一覧

### 🚨 今すぐ（09-12 朝）— この順番で

1. 🚨🚨 **GCP OAuth 同意画面を「テスト中」→「本番」に公開**
   （https://console.cloud.google.com/auth/audience / project `844705815004`）
   ※ **必ずこれを先に。** 逆順だと再認可しても7日後にまた全滅する。
2. 🚨🚨 **YouTube 13ch を再認可**（ダッシュボード → チャンネル設定 →「YouTube 連携」）
3. 🚨 **push（消失リスク・4日連続失敗）** — ホストの端末で:
   ```bash
   cd ~/Developer/youtube-factory && git push origin main   # 17コミット
   cd ~/Developer/aiseki          && git push origin main   # 4コミット
   ```
4. 🚨 `backend/.env` 18行目の `ANTHROPIC_API_KEY` を有効化（**12夜連続**）

### ⚠️ 判断が要るもの

5. **`orch-20260911-followup` のマージ方針**（N5）。
   followup 側の改題対象テーマは main 側で消費済みのため、マージ後に main 側（エントリ削除済みの状態）を採用するのが妥当に見える。rationale の文面差分は followup 側が新しい。
6. **再認可までの間、autopilot を絞るか**（N6）。生成24本／公開0本が4日続いている。
7. **clip-animal を続けるか止めるか**（30日で再生17・登録0なのに autopilot ON）。
8. **切り抜き3ch の縮小判断**（登録/千 0.046 vs ゆっくり系 0.4〜0.8）※データ復旧後。
9. **oripa `feat/stripe-checkout` を main へマージするか**（31日放置）。

### 📦 環境の掃除（Mac 側でないと消せない）

10. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
11. `.git/objects/*/tmp_obj_*` **約810件** / `*.stale.*` 68件 / `stale_locks/` 45件 / `_stale/` 8件 / `_stale_junk/` 14件
12. `logs/backend.log` **81MB** のローテーション設定

### 🔧 aiseki（公開前）

13. Instagram のログイン（`cd worker && npm run login`）
14. Twilio の本番アップグレード（紹介報酬の支払いが依存）
15. `dm_targets` の CSV 取り込み（`/admin/dm`・0件）
16. SNS アカウント（@aisekimatch）の開設
17. live で1回購入してポイント増加を確認
18. サインアップの CAPTCHA 実装
19. ⚠️ `apply_migrations.command` に Supabase の DB パスワードが平文で2箇所
20. 実機での動作確認（`LAUNCH.md` §5）/ 運営体制（通報対応者・営業許可・本店所在地）の確定

### 🔧 ai-english-coach

21. **GitHub リモートの作成と push**（**24日**ローカルのみ）
22. LINE 公式アカウント / LINE Pay 加盟店申込 / Supabase / Vercel / OpenAI キー / Webhook 疎通

### その他

23. ChatGPT スレッドURLを13ch分登録
24. `REDDIT_CLIENT_ID` の設定
25. 画像ブリッジ pending **296** / failed 235 の処理方針
26. fanup 25件 / rhythm-pop 19件 の未コミット整理（任意）

---

## 8. 次回（09-12）の実行時に確認すること

- **再認可されたか**（`youtube_tokens.db` の `updated_at` が 09-12 以降になっているか）
- **公開本数が戻ったか**（09-11 は **0本** / 09-10 は2本 / 09-08 は21本）
- **`video_metrics` に 09-09 以降の行が入ったか**（現在 09-08 止まり・4日欠測）
- **`channel_metrics` が 09-05 から進んだか**（6日欠測）
- **push が通ったか**（youtube-factory 17 / aiseki 4）
- **サムネ403の再発件数**（今回は公開0のため判定不能）
- **レンダ速度が健全域を維持しているか**（09-10 に解決したばかりなので再発監視）
- **画像ブリッジ pending が減ったか**（296件・+81/日で加速中）
- **`min_effective_chars` の効果検証**（09-11 以降の公開分が出てから。実効20字未満の本数が減ったか／25-29字帯の比率／登録/千）
- **09-15**: 答え提示型100%化の反証期限 / **09-16**: 「実は」出現率 / **09-19**: yokai-watch 枠移動 / **09-20**: 09-09 施策の評価
  → ⚠️ **全てデータ復旧が前提。09-12 中に復旧しないと 09-15 の判定は不能になる。**

---

## 9. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-11.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

**他プロジェクトへの書き込み・git 操作（push/merge/commit）・設定変更・外部送信は一切していない。読み取りのみ。**
