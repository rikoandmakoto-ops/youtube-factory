# 全プロジェクト引き継ぎレポート — 2026-09-19

**実行日時**: 2026-09-19 23:20 JST / **前回**: 2026-09-18 23:20
**参照した文脈**: `last_handoff_log.md`(09-18) / `last_merge_log.md`(**09-19 22:08 に更新された**) / `.auto-memory/` の 09-10〜09-18・INDEX.md・`projects/` / `MEMORY_UPDATE_20260919.md`

> ✅ **前回の最優先6件のうち4件が解決。** マージ run の空振り・未コミット82件・未push・未マージブランチが全て片付いた。
> 🚨 **残る最大の期限は OAuth。全6chが残り 0.56日（明日 09-20 12:05 失効）。今夜が最後の猶予。**
> 🔄 **本日の指揮者がサムネ403の優先度を自ら下げた**（サムネ起因の再生は総再生の 0.48% と実測）。方針転換なので、前回まで「最優先」としていた扱いを変更する。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応（期限1件）** | **公開15本・fired 15回＝取りこぼし0・publish_blocked 0件**。**本日14コミット・dirty 4・neworigin へ push 済み**。🚨 **OAuth 残0.56日**。🆕 サムネ失敗に**403以外の新種**（容量超過）。🆕 **ゲート通過キューが 37→29 と2日連続減、company-facts 0.5日分・socio-rx 0件** |
| aiseki | 🟢 **稼働（2日連続）** | 09-19 も6コミット（営業DMレポート・マーケ方針・アフィリエイト座組）。**dirty 0・push 済み**。aisekimatch.com 正常 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**11日**。dirty 0。**リモート未設定＝バックアップ無し（継続）** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**19日**。未追跡25件。サイト正常（サポーター1,248 / 進行中3件のデモデータ表示） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**39日**。HEAD は `feat/stripe-checkout`（main に9先行）。**サイト本文が空（7日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・OAuth 全失効。最終公開 clip-lab/kaneko/fukada **09-09**・clip-animal **09-06**＝**10〜13日**。`theme_queue` 0件。`clip-animal` のみ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 89日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 77日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | `a8974fd`(09-18)。origin と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし・未追跡1 |

---

## 2. youtube-factory

### 2-1. 公開実績（`data/video_publish.db` の `video_status`・JST）

**本日15本**: company-facts 4 / daily-science 3 / scp-lab 3 / yokai-watch 3 / socio-rx 1 / 2ch-matome 1

| 日(JST) | 09-13 | 09-14 | 09-15 | 09-16 | 09-17 | 09-18 | **09-19** |
|---|---:|---:|---:|---:|---:|---:|---:|
| 公開本数 | 7 | 18 | 13 | 14 | 14 | 16 | **15** |

- **`Autopilot fired` 15回 ＝ 公開15本 ＝ `upload_done` 15件。取りこぼし0。**
- **`publish_blocked` 0件（2日連続）。** タイトルゲートもファクト整合も本日は止めていない。
- 2ch-matome は2日連続で公開（8日間停止から復帰後、継続中）。

### 2-2. 直近の変更（`git log --oneline -5`）

```
2a8bc67 23:12 chore: 09-19 のパイプライン生成物と分析結果を取り込む
0f6f2c8 22:09 chore(reports): 09-19 のマージ実行ログを更新
422c3b6 22:07 chore(gitignore): .__deltest を無視
fa9cdd7 22:07 docs: 09-19 指揮者メモ・Mac実行スクリプト・分析xlsx を追加
2982c19 22:07 chore(trends): 09-19 の Google/YouTube トレンド取得結果を追加
```

**本日のコミットは計14件**（00:08〜00:13 の6件は 09-18 ぶんの積み残し、22:07〜23:12 の8件が本日ぶん）。

### 2-3. git の状態

| 項目 | 09-18 | **09-19** |
|---|---|---|
| 未コミット | **82** | **4**（`.auto-memory/` の自動メモのみ） |
| 未マージブランチ | `orch-20260911-followup`（8日） | **なし（ブランチ削除済み）** |
| push | **11件未push** | **neworigin/main と一致（0/0）**。origin は1遅れ |

> ⚠️ `origin`(zaki21016) が1コミット遅れています。実体は `neworigin`(rikoandmakoto-ops) 側で同期が取れているので実害はありませんが、**2つのリモートが分岐したままなのは変わっていません**。恒久的に片方へ寄せるかは判断待ち（下の #13）。

### 2-4. 本日の指揮者の成果（`MEMORY_UPDATE_20260919.md`）

1. 🔄 **サムネの優先度を下げた。** `impressions × CTR` 由来の再生は総再生の **0.48%**（6ch合計 1,427 / 296,090）。Shorts フィードのインプレッションは API が返さないため、**これがサムネの効きうる上限**。403 の解消は「手が空いたときで良い」へ変更。
2. 🔴 **リーチの天井が 08-19 に降りて、原因を外しても戻っていない。** 尺を26〜36秒に揃えた対照で、維持率が 54.6% → 41.0% と13.6pt低下し、**1,200再生超が 35% → 0%**（3週間で1本も出ていない）。原因とされたエンハンサーを 08-31 に全停止した後も回復せず。**指揮者はこれを現時点の最大の未解決問題と申し送っている。**
3. **台本の冒頭が定型化していた（本日修正）。** daily-science は2行目の重複率62%（「えっ、それ昨日あった／やった！」で55%）。原因は `voice_style.tone` に書いた**例示文がそのまま台詞としてコピーされていた**こと。scp-lab は1行目24%。
4. **2ch-matome だけ `script_enhancers` が未設定（＝13モジュール全有効）のまま3週間放置**されていた。他5chと同一設定に揃えた。判定 10-02。

### 2-5. PDCA で検出された課題の対応状況

| 前回の課題 | 状態 |
|---|---|
| N1 `daily-merge` 空振り2日連続 | ✅ **解決**。09-19 22:05 実行 → 22:08 に `last_merge_log.md` 更新・6コミット |
| N2 指揮者 run の成果が全て未コミット | ✅ **解決**。00:08 に `a3e1e0d`（読み上げ速度 8.9→6.95 再校正）ほか6件がコミットされ稼働系に載った |
| #19 未push | ✅ **解決**（neworigin 0/0） |
| #9 `orch-20260911-followup` 未マージ | ✅ **解決**（マージ run の所見どおりブランチ削除） |
| N4 socio-rx キュー全滅 | ❌ **未解決。6件全件が規約違反のまま（変化なし）。本日は1本公開できたが在庫はゼロ** |
| N5 2ch-matome の `forbid_digits` 違反 | ❌ 未解決。24件中 **9件違反（うち `forbid_digits` 8件）**。ただし枠が1/日なので実効15日分あり急を要さない |
| N3 サムネ403 | 🔄 **優先度が下がった**（上記 2-4-1）。実測は 15本中 **11本が403** |

---

## 3. 前回からの差分

### ✅ 解決済み（要対応として扱わない）

- **`daily-merge-all-projects` の空振り** → 解決。6コミット＋ブランチ整理まで完走。
- **未コミット82件** → 解決。dirty 4（自動メモのみ）。
- **未push 11件** → 解決（neworigin）。
- **`orch-20260911-followup` 未マージ（8日）** → 解決（削除）。
- **aiseki の worker 未コミット9件** → 解決（dirty 0・push 済み）。
- **画像ブリッジ `failed` 235件** → 🆕 **全件が 09-08 の mtime で、新規発生はしていない**（単発バッチの滞留であって進行中の障害ではない）。要対応の格を下げる。

### ❌ 未解決（継続）

| # | 内容 | 継続 | 09-19 実測 |
|---|---|---|---|
| 1 | 🚨 GCP OAuth 同意画面が「テスト中」 | **期限当日** | **残り 0.56日。失効 `2026-09-20 12:05`。明日の昼で全6chが止まる** |
| 2 | 🔴 OAuth 未再認可の残7ch | 継続 | 全件失効。**pokemon-lab は9日停止** |
| 3 | 🔴 サムネ403 | 8日 | 15本中**11本**。成功は daily-science 3本のみ。🔄 優先度は指揮者が引き下げ |
| 4 | 🔴 `ANTHROPIC_API_KEY` 401 | 継続 | latest.md の全chで「Claude分析: スキップ（認証エラー）」 |
| 5 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終 **09-16**（`video_metrics` は 09-19 まで） |
| 6 | 🟠 `threads.json` が空 | **15日** | `[]` / パスは `data/image_requests/threads.json`（09-04 から変化なし） |
| 7 | 🟠 画像ブリッジ pending 増加 | 継続 | **684**（前回643・**+41/日**）。failed 235 は据え置き・新規なし |
| 8 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 9 | 🟠 `.git` のゴミ | 悪化 | `tmp_obj_*` **623**（前回375）/ `stale_locks` **88** / `_stale` **34** |
| 10 | 🟠 回帰テストが測れない | **9日** | サンドボックスに pytest 無し |
| 11 | 🟠 oripa `feat/stripe-checkout` 未マージ | **39日** | 9先行・0遅れ |
| 12 | 🟠 oripa サイト本文が空 | **7日** | 到達するが body が空 |
| 13 | 🟠 ai-english-coach リモート未設定 | 継続 | 凍結11日・バックアップ無し |
| 14 | ⚪ fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 / oripa 1 / client-ops 2 | 継続 | 変化なし |
| 15 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | 継続 | 開発は進んだがこの3件は未着手 |
| 16 | ⚠️ 23時台の cron 3本が同一 `0 23 * * *` | 継続 | `nightly-full-progress` / `daily-project-handoff` / `vercel-migration-reminder`。jitter 541/572/580s のみで分散 |
| 17 | ⚠️ `auto_optimize_schedule=true` が4ch | 継続 | company-facts / socio-rx / akashic-librarian / fake-paper |
| 18 | 🟠 `data/job_queue.json` 20MB | 継続 | 上限・ローテーション無し |
| 19 | ⚪ `data/analytics.db`(0B) / `data/video_status.db`(0B) | 継続 | Mac 側でないと削除できない |
| 20 | ⚪ clip-animal の `hard_constraints` 未設定 | 継続 | 停止中は無害 |

### 🆕 NEW

| # | 内容 |
|---|---|
| **N1** | 🔴 **サムネ失敗に403以外の新種が出た。** company-facts の `29kiOFtatn8` は 403 ではなく **`Media larger than: 2097152`（2MB 超）**。403を直しても別経路で落ちる。**本日の実質的なサムネ成功は 15本中3本（daily-science のみ）。** 前回まで「403の本数」だけを数えていたので、この経路は見えていなかった |
| **N2** | 🔄 **サムネ方針が転換した。** 指揮者が imp×CTR 由来の再生を実測し **0.48%** と判定、優先度を最下位へ。**前回まで「最優先」としていた扱いはここで終了**。ザキ様の `/verify` 電話確認も「急ぎではない」に変更 |
| **N3** | 🔴 **リーチの天井（08-19〜）が最大の未解決問題として申し送られた。** 3週間・5回の改訂で動かず、per-video の PDCA では届かない。次の一手は company-facts 型（facts_overlay・尺40〜80秒）の1chへの移植A/B。**ただし 09-25／09-26 の追跡が出るまで交絡させない** |
| **N4** | 🟠 **ゲート通過キューが2日連続で減少（37→29）。総数も 61→51。** ch別の残り日数: **company-facts 0.5日 / scp-lab 0.7日 / daily-science 1.3日 / yokai-watch 2.0日 / socio-rx 0.0日 / 2ch-matome 15日**。消化15本/日に対し **09-21 前後に上位3chが枯れる見込みは前回から変わらず** |
| **N5** | 🔴 **指揮者は「テーマキューは seeds 27〜33件で不足なし」と判断したが、実消費される `autopilot.theme_queue` のゲート通過は29件。** 09-18 のメモに「キュー在庫には2系統ある」と明記した直後に、**同じ取り違えが再発している**。seeds（9〜22件）と theme_queue（3〜24件）は別物 |
| **N6** | 🟢 **`failed` 235件は新規発生していない**（全件 09-08 の mtime）。8日間「235件据え置き」と書き続けたが、据え置きの意味は「詰まって増えていない」であって障害の継続ではなかった |
| **N7** | ⚠️ **本 run の最中（23:12）に `nightly-full-progress` が並走してコミット＋push した。** youtube-factory の HEAD が `0f6f2c8`→`2a8bc67`、aiseki が `7053d29`→`c92949a` へ動いた。**本レポートの git 数値は 23:17 時点の値**。今回は害なし（#16 の cron 衝突の帰結） |
| **N8** | ℹ️ **登録者**: scp-lab **170(+3)** / daily-science **76(+1)** / company-facts **44(+1)** / yokai-watch **31(+2)** / 2ch-matome 11(±0) / socio-rx 0。**6ch合計 332。残7chは測定不能（OAuth 失効）** |

### 📌 キュー在庫（実消費される `autopilot.theme_queue`）

| ch | 総数 | ゲート通過 | 枠/日 | 残り日数 | 主な違反 |
|---|---:|---:|---:|---:|---|
| 2ch-matome | 24 | 15 | 1 | 15.0 | `forbid_digits` 8 |
| yokai-watch | 7 | 6 | 3 | 2.0 | `min_effective_chars` 1 |
| daily-science | 5 | 4 | 3 | 1.3 | `require_any_of` 1 |
| scp-lab | 3 | 2 | 3 | **0.7** | `require_any_of` 1 |
| company-facts | 6 | 2 | 4 | **0.5** | `min_effective_chars` 3 |
| socio-rx | 6 | **0** | 2 | **0.0** | `require_any_of` 6 |
| **合計** | **51** | **29** | 16 | — | |

09-17 **87/32** → 09-18 **61/37** → 09-19 **51/29**。

---

## 4. 他プロジェクト

### aiseki（https://aisekimatch.com — 正常）

- **直近の変更**: `c92949a` アフィリエイトの座組と送信文面 / `7053d29` 同（課金トリガー版）/ `5be9e44` マーケ方針を東京ターゲットへ見直し / `a4480ab` DMスレッド失敗時もスクショを残す / `5e25227` 営業DMのデイリーレポート
- **git**: dirty 0・neworigin と同期（origin は1遅れ）・未マージブランチなし
- **マイグレーション**: `supabase/migrations` ディレクトリが見つからず。**未適用マイグレーションの有無は判定不能**（このリポジトリではマイグレーションを別経路で当てている可能性。`apply_migrations.command` の存在と整合）
- **Vercel**: 本番サイトが正常応答するため**デプロイは生きている**。デプロイ履歴はサンドボックスから参照不可
- **進捗**: 営業DMのデイリーレポートが 09-18・09-19 と2日ぶん生成されている（`worker/reports/`）。launchd 登録済みで 09:00 に自動実行
- **残**: Twilio 本番アップグレード / `dm_targets` CSV 取り込み / 営業本番の開始判断 / ロゴ生成→Instagram プロフ写真差し替え / SNS 投稿0件

### ai-english-coach

- **直近の変更**: なし（`cd2c8c5` 09-08 が最終・**11日**）
- **git**: dirty 0 / **リモート未設定**
- **進捗**: Phase 1 のテキスト版は実装完了（`lib/coach.ts` / `billing.ts` / `linepay.ts` / `supabase.ts` / `usage.ts` / `line.ts` / `ai/index.ts`、マイグレーション2本）。**次の着手順は HANDOFF §7 に記載済み**で、先頭は **LINE Pay 加盟店申込（審査待ちが出るため最優先）**
- **ブロッカーは全てユーザー操作**（外部サービスの申込・発行）。コード側に手待ちは無い

---

## 5. 全進捗サマリ

| プロジェクト | URL | ステータス | 数値 |
|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 稼働6ch・要対応1件 | 登録者 **scp-lab 170 / daily-science 76 / company-facts 44 / yokai-watch 31 / 2ch-matome 11 / socio-rx 0**（計332）。autopilot ON=6ch・OFF=7ch。本日15本公開 |
| aiseki | https://aisekimatch.com | 🟢 開発継続 | サイト正常。残: Twilio本番 / 営業本番の開始判断 / ロゴ / SNS投稿0件 / 運営体制 |
| fanup | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | サイト正常（デモデータ表示中）。19日停止 |
| oripa | https://oripa-omega.vercel.app | 🟡 Phase1 MVP・決済未着手 | **本文が空（7日）**。39日停止。最長リードタイムは古物商許可（約40日） |
| ai-english-coach | （未デプロイ） | 🔵 Phase1 テキスト版完了・音声課金未着手 | 11日停止。リモート未設定 |
| 切り抜きラボ | （clip 4ch） | 🔴 全停止 | OAuth 全失効・autopilot 全OFF・キュー0件。最終公開 09-06〜09-09 |
| rhythm-pop | — | ✅ 完成済み | 89日変化なし・リモート未設定 |
| claude-codex-bridge | — | ✅ 完成済み | 77日変化なし・リモート未設定 |

---

## 6. ユーザー手動待ちタスク一覧

### 🚨 今すぐ（09-20 12:05 が期限）

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / https://console.cloud.google.com/auth/audience）
   — **残り 0.56日。明日 12:05 に稼働6ch が全て止まります。これを逃すと 09-13 と同じ「5日間公開ゼロ」が再発します。**
2. 🚨 **`ANTHROPIC_API_KEY` を貼り直す**（`backend/.env` 18行目）— キー自体が無効（108字の値が入った上での401）
3. **pokemon-lab の OAuth 再認可** — 指揮者が**唯一の依頼**として3日連続で出している。成熟動画の42%が1,200再生超で**6ch中いちばん天井が高い**。手順は `restart_and_trigger_20260919.command`
4. **socio-rx のキュー補充**（6件全滅・実効在庫ゼロ・2日連続）／**company-facts（0.5日分）と scp-lab（0.7日分）も補充**

### 判断が要るもの

5. 🆕 **サムネ403を本当に後回しにしてよいか**（指揮者は 0.48% を根拠に優先度を下げた。ただしこれは Shorts フィードのインプレッションが API から取れないことを前提にした上限推定）
6. 🆕 **サムネの2MB制限**（N1）— 403 とは別に容量で落ちている。生成側のリサイズを入れるか
7. 🆕 **リーチ天井（N3）の次の一手** — company-facts 型（facts_overlay・尺40〜80秒）を1chへ移植する A/B を始めるか。**開始は 09-26 以降（交絡回避）**
8. 2ch-matome の `forbid_digits` を緩めるか（「数字あり」は 09-17 実測で 0.72倍で負。外すなら根拠を測ってから）
9. **23時台の cron 3本をずらす**（今夜も並走した＝N7）
10. `auto_optimize_schedule=true` の4ch を自動最適化に任せるか
11. 残7chの OAuth 再認可をどこまでやるか（akashic-librarian は登録/千 0.727 で実力3位）
12. 切り抜き4chを畳むか（全停止10〜13日・キュー0件）
13. **`origin` と `neworigin` の二重リモートを片方に寄せるか**（origin が1遅れ）
14. fake-paper を止めるか作り直すか
15. oripa `feat/stripe-checkout` を main へマージするか（39日）
16. **09-25** 09-18 の文字数帯引き下げ3ch の判定 / **09-26** 本日の冒頭重複修正の判定 / **10-02** 2ch-matome のエンハンサー停止の判定

### 環境の掃除（Mac 側でないと消せない）

17. `rm -rf .git/stale_locks .git/_stale && find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（`tmp_obj_*` **623** / `stale_locks` 88 / `_stale` 34）
18. ホストで `pytest backend/tests`（**9日間**未測定）
19. `git remote remove neworigin`（または origin を外す。#13 の判断次第）
20. `data/analytics.db`(0B) / `data/video_status.db`(0B) の削除
21. `data/job_queue.json` 20MB の上限・ローテーション要否

### aiseki

22. Twilio 本番アップグレード / `dm_targets` CSV 取り込み（実在確認＋非公開判定）/ 営業本番の開始判断（先頭 `1000bero_net`・**1日30件・間隔30〜120秒は変えない**）
23. ロゴ生成 → Instagram プロフ写真差し替え / SNS 初投稿（**投稿0件**）
24. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
25. 実機動作確認 / 運営体制（通報対応者・営業許可・本店所在地）

### ai-english-coach

26. **GitHub リモートの作成と push**（09-08 以降ローカルのみ＝**バックアップ無し・11日**）
27. **LINE Pay 加盟店申込**（審査があるので最優先）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

### その他

28. ChatGPT スレッドURLを13ch分登録（`data/image_requests/threads.json` が `[]` のまま**15日**）/ 画像ブリッジ pending **684**（+41/日）の処理方針
29. oripa サイト本文が空（**7日連続**）/ 古物商許可（審査約40日）
30. fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 の整理（任意）
31. rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach は**リモート未設定**（バックアップ無し）

---

## 7. 次回（09-20）に確認すること

- 🚨 **OAuth が公開されたか。されていなければ 12:05 以降の公開は全滅しているはず** — `video_status` の 09-20 分が0本かどうかで即座に分かる
- **pokemon-lab が再認可されたか**（指揮者の唯一の依頼・3日連続）
- **キューが補充されたか** — company-facts / scp-lab / socio-rx は**本日の在庫では明日の枠を埋められない**
- **サムネの2MB超（N1）が再発したか**
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数**（今日15本・取りこぼし0）／`publish_blocked`（2日連続0件）
- **`channel_metrics` の遅れ**（今日 09-16＝3日遅れ）／**画像ブリッジ pending**（684・+41/日）
- **23時台の並走**（今夜は 23:12 に `nightly-full-progress` が割り込んだ）
- **09-25**: 文字数帯引き下げ3ch の判定 / **09-26**: 冒頭重複修正の判定・リーチ天井の続き / **10-02**: 2ch-matome エンハンサー停止の判定

---

## 8. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`.git/index` を cp して `GIT_INDEX_FILE` に使ってはいけない。** マージ run が `/tmp` の別インデックスでコミットしているため、`.git/index` は古いまま。これを使うと**本日コミット済みのファイルが「staged deletion」＋「untracked」で二重に出て、dirty が 101件に見える**（実際は4件）。**必ず `export GIT_INDEX_FILE=/tmp/<ユニーク名> && git read-tree HEAD` でインデックスを作り直すこと。** 本日これを踏みかけた。
- 🆕 🔴 **`Autopilot fired for <ch> at YYYY-MM-DD HH:MM:SS JST` には行内にタイムスタンプが埋まっている。** 09-14 以降「ログ行に行頭タイムスタンプが無いので位置で日付を切る」と書き続けていたが、**この行に限っては正確な日付で切れる**。位置基準の推定は不要。
- 🆕 🔴 **`Autopilot fired` を `grep -c` で数えてはいけない。** 1行に2〜4回まとめて出ることがあり、**行数20 vs 出現回数31** と大きくずれる。`grep -o ... | sort | uniq -c` を使う。
- 🆕 **サムネ失敗は403だけではない**（N1）。`Media larger than: 2097152` も同じ「サムネイル設定失敗」行に出る。**403 の件数＝失敗件数ではない。** 成功本数は「公開本数 − 全失敗 distinct video_id」で出すこと。
- 🆕 **キュー在庫の2系統を再度取り違えた**（N5）。実消費は `data/channels/<ch>.json` の **`autopilot.theme_queue`**。`data/channels/<ch>/theme_queue.json` は seeds で別物。**在庫を語るときは必ずどちらか明記する。**
- 🆕 **`failed` のようなカウンタは mtime の分布まで見る。** 235件が8日間動かなかったのは「詰まっている」ではなく「09-08 の単発バッチ以降、新規が発生していない」だった。**「据え置き＝障害継続」と読まない。**
- 🆕 **23時台は他タスクが並走する。** 本 run 中（23:12）に `nightly-full-progress` がコミット＋push し、youtube-factory と aiseki の HEAD が動いた。**git 系の数値は必ず取得時刻を併記すること。**
- 🔴 **`title_constraints.check()` の第2引数は「チャンネル JSON 全体」。** `hard_constraints` を渡すと全件 `ok:True` になる。モジュールは `backend/pipeline/title_constraints.py` で、`cd backend` して `from pipeline import title_constraints`（`jp_wordmatch` を解決するため）。**必ず違反するはずの短い文字列で `ok:False` を確認してから集計する。**
- 🔴 **公開実績は `data/video_publish.db` の `video_status`。** `data/video_status.db` は0バイト。`published_at` は UTC なので `date(datetime(published_at,'+9 hours'))`。
- 🔴 **analytics は `data/analytics/analytics.db`。** `data/analytics.db` は0バイト。`sqlite3.connect('file:...?mode=ro', uri=True)` で開く（存在しないパスに空DBを作ってしまい、このマウントでは消せない）。
- **`theme_queue` の要素に `used` キーは無い。** 「未使用件数」は実質「全件」。
- **`min_effective_chars` には例外がある**（`なぜ.{2,}の(?:か|？)` に一致すると 20→15字）。手で判定せず `check()` を通す。
- **スケジュールの生死は `list_scheduled_tasks` の `lastRunAt` で見る。** ログの有無で判断しない。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は原理的に失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`video_metrics.views` は直近30日窓。** 同一動画でも日をまたいで減る。「再生が減った」と読まない。
- **登録者数と OAuth の生死は `data/reports/latest.md` が唯一のソース**（`oauth_tokens.expires_at` では判定しない）。

---

### 検証について

本レポートの主要12項目（HEAD・dirty・push 状態・公開本数とch別内訳・fired 回数・publish_blocked・サムネ403のdistinct数・キューのゲート通過数・OAuth 残日数・analytics の最終日・pending/failed 件数・登録者数・他リポジトリの git 状態）を**別エージェントで独立に再計測**しました。

- **不一致 1件**: 並走した `nightly-full-progress` により、計測中に youtube-factory と aiseki の HEAD が進んだ（N7）。本レポートは **23:17 時点**の値に揃えてあります。
- **独立計測で新たに判明**: サムネの2MB超（N1）、`failed` 235件の mtime が全件 09-08（N6）、`Autopilot fired` 行のタイムスタンプ埋め込み。
- それ以外の項目は一致しました。
