# 全プロジェクト 引き継ぎレポート — 2026-09-17（木）

**実行日時**: 2026-09-17 23:25 JST / **タスク**: daily-project-handoff
**前回**: 2026-09-16 23:10
**参照した文脈**: `last_handoff_log.md`(09-16 23:10)、`last_merge_log.md`(09-16 22:09)、`.auto-memory/` の 2026-09-10〜09-17・INDEX.md・projects/

> ℹ️ bash 完走。git・sqlite・ログ・キュー・サイト疎通を全て実測。
> ℹ️ 主要12項目を別エージェントで独立再計測 → **不一致0件**（dirty 件数のみ 67 vs 69。実行時刻差でデータファイルが書き変わったため。実害なし）。
> ⚠️ **本 run の7分前（23:18）に並走 run が `c20c988` をコミットした。** 09-14 から**4日連続**で並走が発生している。並走 run の測定結果は本レポートに取り込み、食い違う数値は §5 で訂正した。
> ⚠️ **本日 `daily-merge-all-projects` は走っていない**（`last_merge_log.md` は 09-16 22:09 のまま）。昨日と違い、**今日のコミットは全て手動/指揮者 run の成果物である。**

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-17 も14本公開（2日連続14本）。枠到達 13/14＝92.9%**。しかし **OAuth 残り2.57日（失効 09-20 12:05）**・**サムネ403が6日連続で本日 9/14本**・**APIキー401**・🆕 **2ch-matome は APScheduler にジョブ自体が存在せず2日連続0本** |
| aiseki | 🟡 **2日連続 停止** | 09-16 の `8a64756` 以降**コミット0**・dirty 0・origin と同期。aisekimatch.com 到達。止まっているのは技術課題ではなく**着手判断**（Twilio本番化／ロゴ／SNS初投稿／営業開始） |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**9日**。dirty 0。**Git リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**17日**。未追跡25件。サイト正常（サポーター1,248・進行中3件が表示） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**37日**。`feat/stripe-checkout` 9先行・0遅れ。**サイト本文が空（5日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・OAuth 全失効。**最終公開 clip-animal 09-06 / 他3ch 09-09**。`clip-animal` のみ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 87日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 75日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働（3日停止） | `6c65baa`(09-15) が最新。origin と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし。未追跡1・リモート未設定 |

---

## 2. youtube-factory 詳細

### 2-1. 本日の公開（`video_publish.db` の `video_id` 実在ベース・JST）

| ch | 枠数(平日) | 公開 | 枠到達 | サムネ403 | 備考 |
|---|---:|---:|:--:|---:|---|
| daily-science | 3 | **4** | ✅ | 0/4 ✅ | 07:30（旧cron）と19:00（新枠）が両方発火した**移行日の重複**。明日は3本の想定 |
| company-facts | 4 | 3 | ❌ 3/4 | 3/3 ❌ | **12:30 枠が `publish_blocked`** |
| scp-lab | 3 | 3 | ✅ | 3/3 ❌ | 公開実績は 13:00 のまま。12:45 は 09-18 に判定 |
| yokai-watch | 3 | 3 | ✅ | 3/3 ❌ | — |
| socio-rx | **1**（20:00 月-金） | 1 | ✅ | 0/1 ✅ | 15:00 枠は**土日のみ**。平日枠は1つだけ |
| 2ch-matome | 3 | **0** | ❌ | — | **2日連続0本。最終公開 09-10＝7日** |
| **合計** | **14** | **14** | **13/14＝92.9%** | **9/14 が403** | 09-16 は 13/13＝100% |

### 2-2. 直近5日の公開本数

| 日 | 09-13 | 09-14 | 09-15 | 09-16 | **09-17** |
|---|---:|---:|---:|---:|---:|
| 本数 | 7 | 18 | 13 | 14 | **14** |

### 2-3. git

```
main ...origin/main [ahead 11]   dirty 67（tracked M 34 / untracked 35）
未マージ: orch-20260911-followup（3先行・60遅れ）
remote: origin(zaki21016) / neworigin(rikoandmakoto-ops ※08-31 に放棄)
```

本日のコミット3件:

| hash | 時刻 | 内容 |
|---|---|---|
| `6b70943` | 12:29 | 指揮者 09-17: 投稿枠・タイトルゲートを09-16スナップショットの実測で更新 |
| `7ebe488` | 12:31 | 09-17 指揮者メモ |
| `c20c988` | 23:18 | 09-17 夜間全進捗メモ（並走 run） |

### 2-4. OAuth

| 区分 | ch数 | 内容 |
|---|---:|---|
| 🔴 失効 | **7** | clip-animal / fake-paper / akashic-librarian / clip-fukada / clip-kaneko / clip-lab / pokemon-lab（全件 `Token has been expired or revoked.`） |
| ⚠️ 警告 | **6** | 稼働6ch すべて **残り 2.56〜2.57日**。**失効 2026-09-20 12:05** |

### 2-5. 登録者と至上指標（`data/reports/latest.md`・直近30日窓）

| ch | 登録者 | 前日比 | 人/1000再生 | 前日比 |
|---|---:|---:|---:|---:|
| scp-lab | **167** | +1 | 0.7877 | -0.037 |
| daily-science | **75** | +1 | 0.6617 | -0.006 |
| company-facts | 42 | ±0 | 0.5735 | -0.028 |
| yokai-watch | 29 | ±0 | 0.7393 | -0.021 |
| 2ch-matome | 9 | ±0 | 0.1931 | +0.011 |
| socio-rx | 0 | ±0 | 0.0 | — |

> ⚠️ **この「人/1000再生」は直近30日窓。** 指揮者メモの「登録/千」は直近50本ローリング窓で**別の数字**（09-17 は scp 0.792 / yokai 0.720 / ds 0.653 / cf 0.558 / 2ch 0.188）。**前日比で並べて比較しないこと。**

### 2-6. テーマキュー在庫

| ch | queue | 平日枠 | 名目在庫 | **規約違反** | 実効在庫 |
|---|---:|---:|---:|---:|---:|
| company-facts | 14 | 4 | 3.5日 | 11 | **0.8日** |
| daily-science | 10 | 3 | 3.3日 | 8 | **0.7日** |
| scp-lab | 14 | 3 | 4.7日 | 6 | 2.7日 |
| yokai-watch | 12 | 3 | 4.0日 | 8 | 1.3日 |
| socio-rx | 11 | 1 | 11日 | **11（全滅）** | **0日** |
| 2ch-matome | 26 | 3 | 8.7日 | 11 | （発火せず無意味） |
| **稼働5ch 計** | **61** | **14** | — | **44** | **約1.2日** |

（違反件数は並走 run が `title_constraints.check()` を全数適用した結果。**規則別の延べは67件だが本数は55件**＝1件が複数規則に当たる）

---

## 3. 前回（09-16）から解決したもの

**次回このレポートを書く人へ: 以下を「要対応」として再報告しないこと。**

- ✅ **N3「socio-rx のサムネがパス未指定」→ 解決。** 09-17 は socio-rx の `サムネイルパス未指定` が0件、403も無し。**サムネ成功は daily-science 4 + socio-rx 1 で、09-16 と同じ2ch。**
- ✅ **#5 / N6「`channel_metrics` が日付だけ前進し中身が空」→ 解決。** 最終日が 09-13 → **09-14 へ前進し、views も非ゼロ**（cf 4,283 / ds 2,723 / yokai 1,325 / scp 1,108 / socio 382 / 2ch 2）。※3日遅れは継続。
- ✅ **`video_metrics` は 09-17 当日分まで入っている**（9,968行）。
- ✅ **N2「mdg=2 の効果」→ 2日連続で再現。** scp-lab は 09-16・09-17 とも 3/3 到達。**未使用キュー87件の `max_digit_groups` 違反は0件**＝もう問題ではない。
- ✅ **前回 N8「`orch-20260911-followup` は破棄か cherry-pick が妥当」→ 判断材料が確定。** 遅れが 56 → **60** に拡大。マージの価値はほぼ消えた。

---

## 4. 未解決（継続）

| # | 内容 | 継続 | 09-17 の実測 |
|---|---|---|---|
| 1 | 🔴 GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 2.57日。失効 `2026-09-20 12:05`** |
| 2 | 🔴 サムネ403 | **6日** | 本日14本中 **9本が403**（company-facts 3 / scp-lab 3 / yokai-watch 3）。成功は daily-science 4 + socio-rx 1 |
| 3 | 🔴 `ANTHROPIC_API_KEY` 401 | 継続 | `latest.md` に「ANTHROPIC_API_KEY が無効（認証エラー）」が全ch分。**貼り直し要** |
| 4 | 🔴 OAuth 未再認可の残7ch | 継続 | 変化なし |
| 5 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終日 09-14（中身は非ゼロで改善） |
| 6 | 🟠 画像ブリッジ `threads.json` が空 | **13日** | `{}` / 最終更新 09-04 |
| 7 | 🟠 画像ブリッジ pending 増加 | 継続 | **602**（前回558・**+44/日**）。failed 235 据え置き |
| 8 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし（08-31〜09-12） |
| 9 | 🟠 `orch-20260911-followup` 未マージ | **7日** | **3先行・60遅れ**（前回 3/56） |
| 10 | 🟠 `logs/backend.log` ローテーション未実装 | 継続 | **88,688,939 B**（+1,024,254/日） |
| 11 | 🟠 `.git` のゴミ | 継続 | `tmp_obj_*` **366**（前回321）／ `stale_locks` 86 ／ `index.lock`・`HEAD.lock` 各1 ／ `_stale*` ほか8ディレクトリ |
| 12 | 🟠 回帰テストが測れない | **7日** | サンドボックスに pytest 無し |
| 13 | 🟠 oripa `feat/stripe-checkout` 未マージ | **37日** | 9先行・0遅れ |
| 14 | 🟠 ai-english-coach: Git リモート未設定 | 継続 | `git remote -v` 空 |
| 15 | ⚪ fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 / ai-orchestrator 未追跡1 | 継続 | 変化なし |
| 16 | 🟠 aiseki: Twilio トライアル / SNS未投稿 / ロゴ未作成 | **3日** | HANDOFF §38 に「投稿は0件のまま」。**2日連続コミット0** |
| 17 | 🟠 oripa サイト本文が空 | **5日** | 到達するが body が空 |
| 18 | ⚪ clip-animal の `hard_constraints` 未設定 | 継続 | 停止中は無害。再開した瞬間に検査が丸ごとスキップされる |
| 19 | 🟠 未push コミット | 継続 | **8 → 11 に増加** |

---

## 5. 🆕 NEW（今回はじめて検出／前回から質的に変わったもの）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🔴 **2ch-matome は「発火しない」のではなく、APScheduler に**ジョブが登録されていない** | ログ末尾3MBに `Autopilot fired for 2ch-matome` **0回**、`Autopilot scheduled for 2ch-matome` **0回**。他5chは scheduled 12〜96回・fired 3〜12回。前回は「未発火」までだったが、今回**ジョブ自体の不在**を特定した。`2ch-matome.json` の reload 行は出ているので、**ファイルは読まれているが cron が貼られていない。** |
| **N2** | 🔴 **cron 貼り直しの修正コードは書かれたが、コミットも再起動もされていない** | `backend/api_channel_autopilot.py` / `backend/channels/channel_manager.py` に `_on_channel_config_reloaded()` / `_autopilot_fingerprint()` が実装済み（未コミット・dirty に存在）。**ログに `Application startup complete` は1件も無い＝稼働系に1バイトも載っていない。** 09-12 の `title_gate_ok` と同じ「実装≠稼働」の再演。**検証は再起動後に 2ch-matome が発火するかで行う。** |
| **N3** | 🔴 **`publish_blocked` はタイトルゲート由来だけではない（初確認）** | 本日の1件は company-facts 12:30 枠で、理由は **`数値の矛盾: 伊藤忠商事 の 残業 13.9→34.1時間`**＝**ファクト台帳（`fact_ledger`）整合チェック**。タイトル系（ゲート緩和で対処）とファクト系（台本・台帳の修正で対処）で**打ち手がまったく違う。** |
| **N4** | 🔴 **未使用キューの63%（87件中55件）が規約違反。ボトルネックは `min_effective_chars`（20字下限）** | 規則別 延べ67件のうち **min_eff 35 / require_any_of 16 / forbid_digits 10 / forbid_patterns 6**。**mdg違反は0件。** `min_effective_chars` は `UNREPAIRABLE_RULES`＝機械修復されず、再生成2回で直らなければ枠を捨てる。**socio-rx はキュー11件が全滅・company-facts 11/14・yokai 8/12・ds 8/10。** |
| **N5** | 🔴 **午前に採用した「なぜ／のか」型が、20字下限と正面衝突している** | 実例: yokai-watch「なぜ二口女の話は飢饉の年に生まれたのか」＝実効**19字**で1字足りず違反。daily-science「なぜ手をぶつけた後にさすってしまうのか」も19字。**午前に `require_any_of` を緩めて1つ目の壁を外したが、同じ文字列が2つ目の壁に当たっている。規則は AND で効く。** |
| **N6** | 🔴 **実効キュー在庫は約1.2日しかない** | 名目 3.3〜4.7日だが、違反44件を引くと稼働5chで**即使えるのは17件＝約1.2日**。**「4日ある」は楽観。09-19 前後に枯れる。** |
| **N7** | ⚠️ **socio-rx の投稿枠が backend の `auto_optimize_schedule` によって自動変更された** | 本日19:15 のログに `current slot underperforms recommended by 100.0% — auto-applying recommendation`。結果、**slot1 が「土日 15:00」に、top-level `days_of_week` が `[0,1,2]`（月〜水）に**なった。slot 側の指定が勝っているので今は無害だが、**UI/API から schedule を編集した瞬間に top-level が採用されて月〜水だけに落ちる**（company-facts と同じ地雷。cf は `[3,4,5]`）。**指揮者が知らないところで枠構成が変わる ch が2つある。** |
| **N8** | ⚠️ **daily-science が本日4本公開したのは移行日の重複であって増産ではない** | 07:30（旧cron）と 19:00（新枠）が両方発火。**明日は3本に戻る想定。「daily-science が増えた」と読まない。** |
| **N9** | ℹ️ **本日 `daily-merge-all-projects` が走っていない** | `last_merge_log.md` は 09-16 22:09 のまま。未push が 8→11 に増えたのは指揮者 run の3コミットぶん。**マージタスクのスケジュールが生きているか確認が要る。** |
| **N10** | ℹ️ **登録者が2ch動いた** | scp-lab **167**(+1) / daily-science **75**(+1) / company-facts 42(±0) / yokai-watch 29(±0) / 2ch-matome 9(±0) / socio-rx 0。**残7chは測定不能。** |
| **N11** | ⚠️ **並走 run が4日連続。本日は同一スナップショットで Phase3 が二重実行された** | 09-17 12:29 の指揮者 run と、それ以前に走った並走 run が両方 config を変更。マーカーファイル方式（`reports/orch_config_changes_YYYYMMDD.json`）は「先に走った方が置く」前提が守られず機能しなかった。**スケジュール側で1本に寄せるしかない。** |

### 前夜メモとの数値の食い違い（本レポートで訂正したもの）

| 項目 | 09-17 夜間メモ | **本レポートの実測** | 根拠 |
|---|---|---|---|
| サムネ403の連続日数 | 7日連続 | **6日連続** | 09-16 の handoff ログが「5日連続」。+1日で6日 |
| `backend.log` の増加ペース | +5.1MB/日 | **+1.02MB/日** | 87,664,685(09-16) → 88,688,939(09-17) |

---

## 6. ユーザー手動待ちタスク一覧

### 🚨 今すぐ（09-18〜09-19 に必ず）— この順番で

1. 🚨 **backend を再起動する**（`restart_and_trigger_20260917.command`）
   → **N2 の修正コードを載せる。これをやらないと 2ch-matome は3日目も0本で、09-23 の判定材料が永久に取れない。** 再起動前に、未コミットの `backend/api_channel_autopilot.py` / `backend/channels/channel_manager.py` をコミットしておくこと。
2. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / `console.cloud.google.com/auth/audience`）
   → **失効 `2026-09-20 12:05`。残り2.57日。同意画面を先に公開してから再認可すること。**
3. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch`（`youtube.com/verify`）**6日連続で最優先のまま。**
4. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに貼り直す**（`backend/.env` 18行目）
5. 🆕 🚨 **キューの規約違反44件への対処を決める**（N4/N5）— 20字下限を19字へ下げるか、補充側の生成を長さを満たす形に変えるか。**実効在庫は約1.2日しか無い。**
   ⚠️ 20字下限は 09-11 に n=330 の逆U字（25-29字が頂点）で入れた**実績根拠のある規則**。mdg のように単純に外すのは誤り。**生成側で長さを満たすほうが筋が良い。**
6. **`cd ~/Developer/youtube-factory && git push origin main`**（**11コミット**未送信）

### 判断が要るもの

7. 🆕 **`auto_optimize_schedule=true` の2ch（company-facts / socio-rx）を、このまま backend の自動最適化に任せるか**（N7）— 任せるなら指揮者は枠を触らない、止めるならフラグを false にする。**今は「指揮者が触らない」と「backend が勝手に変える」が併存している。**
8. 🆕 **ファクト台帳の矛盾をどう直すか**（N3）— 伊藤忠商事の残業時間が `fact_ledger` 内で 13.9 と 34.1 に分裂している。
9. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。akashic-librarian は実力3位）
10. 切り抜き4chを畳むか（全停止・最終公開 09-06〜09-09・キュー111件が死蔵）
11. fake-paper を止めるか作り直すか（OFF・キュー3件）
12. **`orch-20260911-followup` は破棄か cherry-pick が妥当**（3先行・**60遅れ**・7日放置。マージの価値はほぼ消えた）
13. oripa `feat/stripe-checkout` を main へマージするか（9先行・0遅れ・**37日**放置）
14. **company-facts の枠 4→3 差し戻し**（09-21 に判定）
15. **いいね率 vs 維持率のどちらを先行指標にするか**（09-21 に独立コホートで本判定。**09-16 に維持率も 5/5→4/5 に落ちたので、どちらにも乗り換える根拠は現時点で無い**）
16. 🆕 **並走 run を1本に寄せる**（N11）— 4日連続。マーカーファイル方式では止まらない。

### 環境の掃除（Mac 側でないと消せない）

17. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
18. `rm -rf .git/stale_locks .git/_stale* .git/_locksink .git/_trash_consolidated .git/_scratch_delme .git/_writetest`（86件＋8ディレクトリ）
19. `find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**366件**）
20. `logs/backend.log` **88.7MB**（+1.02MB/日）のローテーション
21. ホストで `pytest backend/tests` を1回流す（**7日間**測れていない）
22. **`neworigin` リモートを削除してよい**（`git remote remove neworigin`）— 08-31 で放棄
23. 🆕 **`daily-merge-all-projects` のスケジュールが生きているか確認**（N9・本日実行されていない）

### aiseki（公開前・**3日間1つも動いていない**）

24. **Twilio 本番アップグレード** ／ `dm_targets` の CSV 取り込み（**実在確認＋非公開判定を入れる**）／ 営業本番の開始判断（先頭 `1000bero_net`・1日30件/間隔30〜120秒は変えない）
25. **ChatGPT でのロゴ生成 → Instagram プロフ写真の差し替え**、**SNS 初投稿**（素材 `sns_assets/`・文面 `sns_posts.md`・投稿0件）
26. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
27. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

### ai-english-coach

28. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝**バックアップ無し**）
29. LINE Pay 加盟店申込（**審査があるので最優先**）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

### その他

30. **ChatGPT スレッドURLを13ch分登録**（`threads.json` が `{}` のまま**13日**）／画像ブリッジ pending **602**（+44/日）・failed 235 の処理方針
31. oripa サイトの本文が空（**5日連続**）— ビルドかルーティングの確認
32. ⚠️ **oripa の最長リードタイムは古物商許可（審査約40日）。** 着手が遅れるほど開業日がそのまま後ろへ動く
33. fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 / ai-orchestrator 未追跡1 の整理（任意）
34. **rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach はリモート未設定**（バックアップ無し）。GitHub へ退避

---

## 7. 次回（09-18）の実行時に確認すること

- **🚨 OAuth の残日数**（今日 2.57日 → 明日 1.57日のはず。**失効は 09-20 12:05**）
- 🆕 **backend が再起動されたか**（`Application startup complete` がログに出るか）。**出ていれば N1/N2 の検証が可能になる**
- 🆕 **2ch-matome に `Autopilot scheduled for 2ch-matome` が出るか。** 出なければ修正コードが不十分ということ
- **サムネ403が company-facts / scp-lab / yokai-watch で止まったか**（成功しているのが2日連続で daily-science と socio-rx だけ＝**アカウント単位説**の3日目の再現を見る）
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数と枠到達率**（09-17 は 13/14＝92.9%。**daily-science は3本に戻る想定**）
- 🆕 **キューの規約違反件数**（今日 87件中55件。**補充が入っても違反のままなら在庫は増えない**）
- 🆕 **scp-lab の 12:45 枠が実際に 12:45 で発火したか**（今日は 13:00 のままだった）
- **キュー実効在庫**（今日 約1.2日。**補充が無ければ 09-19 に枯れる**）
- **`channel_metrics` の遅れが縮まったか**（今日 09-14＝3日遅れ）
- **画像ブリッジ pending**（602 → +44/日の傾きが続くか）
- **09-20**: OAuth 失効日 / **09-21**: 09-14 枠・型変更の本判定、company-facts 枠 4→3、いいね率 vs 維持率 / **09-23**: 2ch-matome 再開の評価期日 / **09-24**: 09-17 の枠変更2件・「のか」追加・キュー並べ替えの評価

---

## 8. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`Autopilot fired` が0でも「発火に失敗した」とは限らない。`Autopilot scheduled for <ch>` も0なら、ジョブがそもそも登録されていない。** 前者は「登録されたが動かなかった」、後者は「登録すらされていない」で原因が全く違う。**2ch-matome は後者だった。**
- 🆕 🔴 **`publish_blocked` は理由の種別まで読む。** `⛔ この枠は公開を止めました` を grep するだけで終わらせず、直前行の `⛔ publish_blocked:` を見る。**タイトル規約違反とファクト整合違反（`数値の矛盾:`）で打ち手がまったく違う。**
- 🆕 **キュー在庫を日数で語るときは規約違反件数を引く。** 名目 87件でも、違反55件と発火しない ch の26件を除くと**実際に使えるのは17件**。「4日ある」は楽観。
- 🆕 **`autopilot.schedule.times` の各 slot は `days_of_week` を持ち、top-level の `days_of_week` とは別。** socio-rx は top-level `[0,1,2]` だが slot0 は `[1,2,3,4,5]`。**slot 側が勝つ。** 「平日に何枠あるか」は slot 側を見ること（socio-rx の平日枠は **1つ**であって2つではない）。
- 🆕 **`auto_optimize_schedule=true` の ch（company-facts / socio-rx）は backend が枠を勝手に書き換える。** 前日との差分が指揮者の変更とは限らない。`current slot underperforms recommended by` をログで探す。
- 🔴 **`git status` の前に必ず `cp .git/index /tmp/x && export GIT_INDEX_FILE=/tmp/x` する。** 空の `GIT_INDEX_FILE` を新規に指すと**全追跡ファイルが `D`（削除）に見える**。
- **`publish_blocked` の grep 文字列は `この枠は公開を止めました` だけで引く。** `⛔ この枠は公開を止めました` では0件になる。
- 🆕 **`logs/backend.log` の tail は毎回ユニークな一時ファイル名にする。** `/tmp/bl.txt` のような固定名は前回実行の残骸が権限エラーで上書きできず、**古い内容を読んで集計が丸ごとずれる**（本日実際に踏んだ）。`/tmp/rc/` も同様に使わない。
- 🆕 **ログ内のイベントの新旧は「今日の既知 `video_id` の出現位置」を基準に判定する。** 行頭にタイムスタンプが無いため、位置より前にあるものは過去日。本日 `publish_blocked` 2件のうち **scp-lab の1件は 09-15 の残骸**だった（今日は company-facts の1件のみ）。
- **サムネの失敗は403だけではない。** `ℹ️ サムネイルパス未指定` は**試行すらしていない**別の失敗。
- **`latest.md` の「人/1000再生」は直近30日窓、指揮者の「登録/千」は直近50本ローリング窓。別の数字。前日比で並べてはいけない。**
- **`autopilot.enabled` を JSON 直書きで true にしても発火しない**（`_save_autopilot()` → `_refresh_channel_job()` の経路だけが cron を貼り直す）。**「ONにした」を「動き出した」と書かない。**
- **`title_constraints.check()` は「素のタイトル」に当てる。** 公開済みタイトルにはハッシュタグが付き `max_chars` で全滅する。
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。機械修復してよいのは絵文字除去だけ。**`min_effective_chars` は `UNREPAIRABLE_RULES`＝修復対象外。**
- **analytics DB は `data/analytics/analytics.db`・日付カラムは `date`。**
- **`video_metrics` の views は直近30日窓。** 同一動画でも日をまたいで**減る**。「再生が減った」と読まない。
- **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。公開の真偽は `video_id` の有無。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。

---

## 9. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-17.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform / ai-orchestrator）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
