# Daily Handoff Log

**実行日時**: 2026-09-17 23:25 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-17.md`
**前回**: 2026-09-16 23:10 / **参照した文脈**: `last_handoff_log.md`(09-16)、`last_merge_log.md`(09-16 22:09)、`.auto-memory/` の 2026-09-10〜09-17・INDEX.md・projects/

> ℹ️ bash 完走。git・sqlite・ログ・キュー・サイト疎通を全て実測。
> ℹ️ 主要12項目を別エージェントで独立再計測 → **不一致0件**（dirty 件数のみ 67 vs 69＝実行時刻差。実害なし）。
> ⚠️ **本 run の7分前（23:18）に並走 run が `c20c988` をコミット。09-14 から4日連続の並走。** 並走 run の測定は本レポートに取り込み、食い違う数値は訂正した。
> ⚠️ **本日 `daily-merge-all-projects` は走っていない**（`last_merge_log.md` は 09-16 22:09 のまま）。今日のコミット3件は全て指揮者 run の成果物。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-17 も14本公開（2日連続）。枠到達 13/14＝92.9%**。**OAuth 残り2.57日**・**サムネ403が6日連続で9/14本**・**APIキー401**・🆕 **2ch-matome は APScheduler にジョブ自体が無く2日連続0本**・🆕 **未使用キューの63%が規約違反で実効在庫1.2日** |
| aiseki | 🟡 **2日連続 停止** | 09-16 `8a64756` 以降コミット0・dirty 0・origin と同期。aisekimatch.com 到達。止まっているのは技術課題ではなく**着手判断** |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**9日**。dirty 0。**リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**17日**。未追跡25件。サイト正常 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**37日**。`feat/stripe-checkout` 9先行・0遅れ。**サイト本文が空（5日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・OAuth 全失効。最終公開 09-06〜09-09。`clip-animal` のみ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 87日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 75日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働（3日停止） | `6c65baa`(09-15) が最新。origin と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし。未追跡1・リモート未設定 |

**本日の公開（`video_id` 実在ベース・JST）**: ds 4（07:30旧cron＋新枠の重複／明日は3本想定）/ cf 3（12:30 が publish_blocked）/ scp 3 / yokai 3 / socio 1（平日枠は1つ）/ 2ch-matome **0** = **14本・枠到達 13/14**

---

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **N3「socio-rx のサムネがパス未指定」→ 解決。** 本日 `サムネイルパス未指定` 0件・403も無し。成功は daily-science 4 + socio-rx 1 で 09-16 と同じ2ch。
- **#5 / N6「`channel_metrics` が日付だけ前進し中身が空」→ 解決。** 最終日 09-13→**09-14**、views も非ゼロ（cf 4,283 / ds 2,723 / yokai 1,325 / scp 1,108 / socio 382 / 2ch 2）。※3日遅れは継続。
- **`video_metrics` は 09-17 当日分まで取得済み**（9,968行）。
- **N2「mdg=2 の効果」→ 2日連続で再現。** scp-lab 3/3。**未使用キュー87件の `max_digit_groups` 違反は0件＝もう問題ではない。**
- **N8「`orch-20260911-followup` の扱い」→ 判断材料が確定。** 遅れ 56→**60**。マージの価値はほぼ消えた。

### ❌ 未解決

| # | 内容 | 継続 | 09-17 の実測 |
|---|---|---|---|
| 1 | 🔴 GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 2.57日。失効 `2026-09-20 12:05`** |
| 2 | 🔴 サムネ403 | **6日** | 本日14本中 **9本**（cf 3 / scp 3 / yokai 3）。成功は ds 4 + socio 1 |
| 3 | 🔴 `ANTHROPIC_API_KEY` 401 | 継続 | `latest.md` 全chに「ANTHROPIC_API_KEY が無効（認証エラー）」 |
| 4 | 🔴 OAuth 未再認可の残7ch | 継続 | 全件 `Token has been expired or revoked.` |
| 5 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終日 09-14（中身は改善） |
| 6 | 🟠 画像ブリッジ `threads.json` が空 | **13日** | `{}` / 最終更新 09-04 |
| 7 | 🟠 画像ブリッジ pending 増加 | 継続 | **602**（前回558・**+44/日**）。failed 235 据え置き |
| 8 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 9 | 🟠 `orch-20260911-followup` 未マージ | **7日** | **3先行・60遅れ** |
| 10 | 🟠 `logs/backend.log` ローテーション未実装 | 継続 | **88,688,939 B**（+1,024,254/日） |
| 11 | 🟠 `.git` のゴミ | 継続 | `tmp_obj_*` **366**（前回321）／`stale_locks` 86 ／`index.lock`・`HEAD.lock` 各1 |
| 12 | 🟠 回帰テストが測れない | **7日** | サンドボックスに pytest 無し |
| 13 | 🟠 oripa `feat/stripe-checkout` 未マージ | **37日** | 9先行・0遅れ |
| 14 | 🟠 ai-english-coach: リモート未設定 | 継続 | `git remote -v` 空 |
| 15 | ⚪ fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 1 / ai-orchestrator 1 | 継続 | 変化なし |
| 16 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | **3日** | 2日連続コミット0 |
| 17 | 🟠 oripa サイト本文が空 | **5日** | 到達するが body が空 |
| 18 | ⚪ clip-animal の `hard_constraints` 未設定 | 継続 | 停止中は無害。再開した瞬間に検査が丸ごとスキップ |
| 19 | 🟠 未push コミット | 継続 | **8 → 11 に増加** |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🔴 **2ch-matome は「発火しない」のではなく APScheduler にジョブが登録されていない** | ログ末尾3MBに `Autopilot fired for 2ch-matome` **0回**、`Autopilot scheduled for 2ch-matome` **0回**（他5chは scheduled 12〜96回）。`2ch-matome.json` の reload 行は出ている＝**読まれているが cron が貼られていない。** 最終公開は 09-10＝**7日** |
| **N2** | 🔴 **cron 貼り直しの修正コードは書かれたが、コミットも再起動もされていない** | `backend/api_channel_autopilot.py` / `backend/channels/channel_manager.py` に `_on_channel_config_reloaded()` / `_autopilot_fingerprint()` が実装済み（**未コミット**）。ログに `Application startup complete` は1件も無い＝**稼働系に1バイトも載っていない。** 09-12 の `title_gate_ok` と同型の「実装≠稼働」 |
| **N3** | 🔴 **`publish_blocked` はタイトルゲート由来だけではない（初確認）** | 本日の1件は cf 12:30 枠で理由は `数値の矛盾: 伊藤忠商事 の 残業 13.9→34.1時間`＝**ファクト台帳整合チェック**。タイトル系（ゲート緩和）とファクト系（台本・台帳修正）で**打ち手が全く違う** |
| **N4** | 🔴 **未使用キューの63%（87件中55件）が規約違反。ボトルネックは `min_effective_chars`（20字下限）** | 規則別 延べ67件: **min_eff 35 / require_any_of 16 / forbid_digits 10 / forbid_patterns 6**。**mdg違反0件。** socio-rx 11/11全滅・cf 11/14・yokai 8/12・ds 8/10。`min_effective_chars` は `UNREPAIRABLE_RULES`＝機械修復されない |
| **N5** | 🔴 **午前に採用した「なぜ／のか」型が20字下限と正面衝突** | yokai「なぜ二口女の話は飢饉の年に生まれたのか」＝実効**19字**で違反。ds「なぜ手をぶつけた後にさすってしまうのか」も19字。**`require_any_of` を緩めても、同じ文字列が2つ目の壁に当たる。規則は AND で効く** |
| **N6** | 🔴 **実効キュー在庫は約1.2日** | 名目3.3〜4.7日だが違反44件を引くと稼働5chで即使えるのは**17件**。**09-19 前後に枯れる** |
| **N7** | ⚠️ **socio-rx の枠が backend の `auto_optimize_schedule` で自動変更された** | 19:15 に `current slot underperforms recommended by 100.0% — auto-applying recommendation`。slot1 が**土日15:00**へ、top-level `days_of_week` が **`[0,1,2]`（月〜水）**に。今は slot 側が勝つので無害だが、**UI/API から schedule を編集した瞬間に月〜水だけに落ちる**（cf は `[3,4,5]`）。**枠が勝手に変わる ch が2つある** |
| **N8** | ⚠️ **daily-science の本日4本は移行日の重複であって増産ではない** | 07:30（旧cron）と19:00（新枠）が両方発火。**明日は3本に戻る想定** |
| **N9** | ℹ️ **本日 `daily-merge-all-projects` が走っていない** | `last_merge_log.md` は 09-16 22:09 のまま。**スケジュールが生きているか確認が要る** |
| **N10** | ℹ️ **登録者** | scp-lab **167**(+1) / daily-science **75**(+1) / company-facts 42(±0) / yokai-watch 29(±0) / 2ch-matome 9(±0) / socio-rx 0。**残7chは測定不能** |
| **N11** | ⚠️ **並走 run が4日連続。本日は同一スナップショットで Phase3 が二重実行された** | マーカーファイル方式は「先に走った方が置く」前提が守られず機能せず。**スケジュール側で1本に寄せるしかない** |

### ⚠️ 前夜メモとの数値の食い違い（本レポートで訂正）

| 項目 | 09-17 夜間メモ | **実測** | 根拠 |
|---|---|---|---|
| サムネ403の連続日数 | 7日連続 | **6日連続** | 09-16 handoff が「5日連続」。+1で6日 |
| `backend.log` の増加ペース | +5.1MB/日 | **+1.02MB/日** | 87,664,685(09-16) → 88,688,939(09-17) |

---

## 3. ユーザー手動待ちタスク一覧

**🚨 今すぐ（09-18〜09-19 に必ず）— この順番で**

1. 🆕 🚨 **backend を再起動する**（`restart_and_trigger_20260917.command`）— **N2 の修正コードを載せる。これをやらないと 2ch-matome は3日目も0本で、09-23 の判定材料が取れない。** 再起動前に未コミットの `backend/api_channel_autopilot.py` / `backend/channels/channel_manager.py` をコミットすること。
2. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / `console.cloud.google.com/auth/audience`）— **失効 `2026-09-20 12:05`。残り2.57日。同意画面を先に公開してから再認可。**
3. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch`（`youtube.com/verify`）**6日連続で最優先のまま。**
4. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに貼り直す**（`backend/.env` 18行目）
5. 🆕 🚨 **キューの規約違反44件への対処を決める**（N4/N5）— 20字下限を19字へ下げるか、補充側の生成を長さを満たす形に変えるか。**実効在庫は約1.2日。**
   ⚠️ 20字下限は 09-11 に n=330 の逆U字で入れた**実績根拠のある規則**。mdg のように単純に外すのは誤り。**生成側で長さを満たすほうが筋が良い。**
6. **`cd ~/Developer/youtube-factory && git push origin main`**（**11コミット**未送信）

**判断が要るもの**

7. 🆕 **`auto_optimize_schedule=true` の2ch（company-facts / socio-rx）を自動最適化に任せるか**（N7）— 今は「指揮者が触らない」と「backend が勝手に変える」が併存している
8. 🆕 **ファクト台帳の矛盾をどう直すか**（N3）— 伊藤忠商事の残業時間が 13.9 と 34.1 に分裂
9. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。akashic-librarian は実力3位）
10. 切り抜き4chを畳むか（全停止・キュー111件が死蔵）
11. fake-paper を止めるか作り直すか（OFF・キュー3件）
12. **`orch-20260911-followup` は破棄か cherry-pick**（3先行・**60遅れ**・7日放置）
13. oripa `feat/stripe-checkout` を main へマージするか（9先行・0遅れ・**37日**放置）
14. **company-facts の枠 4→3 差し戻し**（09-21 に判定）
15. **いいね率 vs 維持率のどちらを先行指標にするか**（09-21 本判定。**09-16 に維持率も 5/5→4/5 に落ちたので、どちらにも乗り換える根拠は現時点で無い**）
16. 🆕 **並走 run を1本に寄せる**（N11・4日連続）

**環境の掃除（Mac 側でないと消せない）**

17. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
18. `rm -rf .git/stale_locks .git/_stale* .git/_locksink .git/_trash_consolidated .git/_scratch_delme .git/_writetest`（86件＋8ディレクトリ）
19. `find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**366件**）
20. `logs/backend.log` **88.7MB**（+1.02MB/日）のローテーション
21. ホストで `pytest backend/tests` を1回流す（**7日間**測れていない）
22. **`neworigin` リモートを削除してよい**（`git remote remove neworigin`）
23. 🆕 **`daily-merge-all-projects` のスケジュールが生きているか確認**（N9）

**aiseki（公開前・3日間1つも動いていない）**

24. **Twilio 本番アップグレード** ／ `dm_targets` の CSV 取り込み（**実在確認＋非公開判定を入れる**）／ 営業本番の開始判断（先頭 `1000bero_net`・1日30件/間隔30〜120秒は変えない）
25. **ChatGPT でのロゴ生成 → Instagram プロフ写真の差し替え**、**SNS 初投稿**（素材 `sns_assets/`・文面 `sns_posts.md`・投稿0件）
26. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
27. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

28. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝**バックアップ無し**）
29. LINE Pay 加盟店申込（**審査があるので最優先**）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

30. **ChatGPT スレッドURLを13ch分登録**（`threads.json` が `{}` のまま**13日**）／画像ブリッジ pending **602**（+44/日）・failed 235 の処理方針
31. oripa サイトの本文が空（**5日連続**）— ビルドかルーティングの確認
32. ⚠️ **oripa の最長リードタイムは古物商許可（審査約40日）。** 着手が遅れるほど開業日がそのまま後ろへ動く
33. fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 1 / ai-orchestrator 1 の整理（任意）
34. **rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach はリモート未設定**（バックアップ無し）。GitHub へ退避

---

## 4. 次回（09-18）の実行時に確認すること

- **🚨 OAuth の残日数**（今日 2.57日 → 明日 1.57日のはず。**失効は 09-20 12:05**）
- 🆕 **backend が再起動されたか**（`Application startup complete` がログに出るか）
- 🆕 **`Autopilot scheduled for 2ch-matome` が出るか。** 出なければ修正コードが不十分
- **サムネ403が cf / scp / yokai で止まったか**（成功が2日連続で ds と socio だけ＝**アカウント単位説**の3日目の再現を見る）
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数と枠到達率**（09-17 は 13/14＝92.9%。**daily-science は3本に戻る想定**）
- 🆕 **キューの規約違反件数**（今日 87件中55件。**補充が入っても違反のままなら在庫は増えない**）
- 🆕 **scp-lab の 12:45 枠が実際に 12:45 で発火したか**（今日は 13:00 のままだった）
- **キュー実効在庫**（今日 約1.2日。**補充が無ければ 09-19 に枯れる**）
- **`channel_metrics` の遅れが縮まったか**（今日 09-14＝3日遅れ）
- **画像ブリッジ pending**（602 → +44/日の傾きが続くか）
- **09-20**: OAuth 失効日 / **09-21**: 09-14 枠・型変更の本判定、cf 枠 4→3、いいね率 vs 維持率 / **09-23**: 2ch-matome 再開の評価期日 / **09-24**: 09-17 の枠変更2件・「のか」追加・キュー並べ替えの評価

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`Autopilot fired` が0でも「発火に失敗した」とは限らない。`Autopilot scheduled for <ch>` も0なら、ジョブがそもそも登録されていない。** 前者は「登録されたが動かなかった」、後者は「登録すらされていない」で原因が全く違う。**2ch-matome は後者だった。**
- 🆕 🔴 **`publish_blocked` は理由の種別まで読む。** `この枠は公開を止めました` の grep で終わらせず、直前行の `⛔ publish_blocked:` を見る。**タイトル規約違反とファクト整合違反（`数値の矛盾:`）で打ち手がまったく違う。**
- 🆕 **キュー在庫を日数で語るときは規約違反件数を引く。** 名目87件でも、違反55件と発火しない ch の26件を除くと使えるのは17件。「4日ある」は楽観。
- 🆕 **`autopilot.schedule.times` の各 slot は `days_of_week` を持ち、top-level とは別。slot 側が勝つ。** socio-rx は top-level `[0,1,2]` だが slot0 は `[1,2,3,4,5]`。**平日枠は1つであって2つではない。**
- 🆕 **`auto_optimize_schedule=true` の ch（company-facts / socio-rx）は backend が枠を勝手に書き換える。** 前日との差分が指揮者の変更とは限らない。`current slot underperforms recommended by` をログで探す。
- 🆕 **`logs/backend.log` の tail は毎回ユニークな一時ファイル名にする。** `/tmp/bl.txt` のような固定名は前回実行の残骸が権限エラーで上書きできず、**古い内容を読んで集計が丸ごとずれる**（本日実際に踏んだ）。`/tmp/rc/` も同様に使わない。
- 🆕 **ログ内のイベントの新旧は「今日の既知 `video_id` の出現位置」を基準に判定する。** 行頭にタイムスタンプが無い。本日 `publish_blocked` 2件のうち **scp-lab の1件は 09-15 の残骸**で、今日は company-facts の1件のみだった。
- 🔴 **`git status` の前に必ず `cp .git/index /tmp/x && export GIT_INDEX_FILE=/tmp/x` する。** 空の `GIT_INDEX_FILE` を新規に指すと**全追跡ファイルが `D`（削除）に見える。**
- **`publish_blocked` の grep 文字列は `この枠は公開を止めました` だけで引く。** `⛔ この枠は公開を止めました` では0件。
- **サムネの失敗は403だけではない。** `ℹ️ サムネイルパス未指定` は試行すらしていない別の失敗。
- **`latest.md` の「人/1000再生」は直近30日窓、指揮者の「登録/千」は直近50本ローリング窓。別の数字。前日比で並べてはいけない。**
- **`autopilot.enabled` を JSON 直書きで true にしても発火しない**（cron を貼り直すのは `_save_autopilot()` → `_refresh_channel_job()` の経路だけ）。**「ONにした」を「動き出した」と書かない。**
- **`title_constraints.check()` は「素のタイトル」に当てる。** 公開済みタイトルにはハッシュタグが付き `max_chars` で全滅する。
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。機械修復してよいのは絵文字除去だけ。**`min_effective_chars` は `UNREPAIRABLE_RULES`＝修復対象外。**
- **analytics DB は `data/analytics/analytics.db`・日付カラムは `date`。**
- **`video_metrics` の views は直近30日窓。** 同一動画でも日をまたいで**減る**。「再生が減った」と読まない。
- **ch あたり直近50本の固定窓なので、総再生の前日比は意味が無い。**
- **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。公開の真偽は `video_id` の有無。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。
- **`data/reports/latest.md` が登録者数の唯一のソース。** OAuth が生きている ch しか値が入らない。
- **views のラグは約2日。**
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- ⚠️ **夜間は並走 run と重なる。** 09-17 は 23:18 に別 run が `c20c988` をコミットした7分後に本タスクが走った。**他 run のコミットを「手作業の進捗」と読み違えないこと。**

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-17.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform / ai-orchestrator）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
