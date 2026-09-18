# Daily Handoff Log

**実行日時**: 2026-09-18 23:20 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-18.md`
**前回**: 2026-09-17 23:25 / **参照した文脈**: `last_handoff_log.md`(09-17)、`last_merge_log.md`(**09-16 22:09 のまま**)、`.auto-memory/` の 09-10〜09-17・INDEX.md、`MEMORY_UPDATE_20260918.md`

> ℹ️ bash 完走。git・sqlite・ログ・キュー・サイト疎通を全て実測。主要13項目を別エージェントで独立再計測 → **不一致0件**。
> ✅ **前回の最優先3件のうち2件が解決**（backend 再起動 / push）。**2ch-matome が8日ぶりに公開再開し、本日は過去最多の16本公開。**
> ⚠️ **本日のコミットは0件。** 指揮者 run の成果が全て未コミットで dirty 82件が滞留。マージ run も2日連続で空振り。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **16本公開（過去最多・fired=公開で取りこぼし0・publish_blocked 0件）**。2ch-matome 復活・ログローテ実装・push 完了。**OAuth 残り1.56日**、🆕 **サムネ403が13/16に悪化（成功は ds のみ）**、🆕 **本日コミット0・マージ run 空振り2日連続** |
| aiseki | 🟢 **再始動（3日ぶり）** | 09-18 に Instagram worker / DM レポート / launchd を実装。**全て未コミット（dirty 9）**。aisekimatch.com 正常 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**10日**。dirty 0。**リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**18日**。未追跡25件。サイト正常 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**38日**。HEAD は `feat/stripe-checkout`（main に9先行・0遅れ）。**サイト本文が空（6日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・OAuth 全失効。最終公開 09-06〜09-08＝**10〜12日**。`theme_queue` は0件。`clip-animal` のみ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 88日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 76日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | `a8974fd`(09-18)。origin と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし |

**本日の公開（JST・`video_id` 実在ベース）**: cf 4 / ds 3 / scp 3 / yokai 3 / **2ch-matome 2** / socio 1 = **16本**（09-17 は14本）

---

## 2. 検出した課題

### ✅ 解決済み（次回「要対応」として報告しないこと）

- **N1/N2「2ch-matome に APScheduler ジョブが無い」「cron 貼り直しが未コミット・未再起動」→ 両方解決。** `3e47dcd` コミット＋再起動（`Application startup complete` ×1）。`Autopilot scheduled for 2ch-matome` 8回・fired 2回・**公開2本**（8日ぶり）。
- **#19「未push コミット11件」→ 解決。** `origin/main...HEAD` = **`0 0`**。
- **#10「`backend.log` ローテーション未実装」→ 解決。** `scripts/rotate_backend_log.sh` + launchd（毎日04:30・20MB超・7世代）。**88.7MB → 1.21MB**。
- **N4/N5「未使用キューの63%が規約違反・20字下限と『なぜ／のか』型の衝突」→ 大幅改善。** 「なぜ〜のか」型のみ下限 20→**15字**。**違反 55/87(63%) → 24/61(39%)**、`min_effective_chars` 違反 35→**12**。
- **N3「ファクト整合違反による publish_blocked」→ 本日は再発なし**（本日 publish_blocked 0件、`fact_ledger/company-facts.json` 55行追記済み）。
- **N9「daily-merge のスケジュールが生きているか」→ スケジュールは生きている**（09-18 22:05 実行）。**ただし中身が空振り＝新課題 🆕N1 へ。**
- **「socio-rx サムネのパス未指定」→ コード側は修正済み**（403 は別問題・未解決）。

### ❌ 未解決

| # | 内容 | 継続 | 09-18 実測 |
|---|---|---|---|
| 1 | 🔴 GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 1.56日。失効 `2026-09-20 12:05`。夜間 run はあと1回** |
| 2 | 🔴 サムネ403 | **7日・悪化** | 16本中**13本失敗**（cf4/scp3/yokai3/2ch2/socio1）。**成功は ds 3本のみ** |
| 3 | 🔴 `ANTHROPIC_API_KEY` 401 | 継続 | 全chで「認証エラー」 |
| 4 | 🔴 OAuth 未再認可の残7ch | 継続 | 全件 `Token has been expired or revoked.` |
| 5 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終 **09-15**（`video_metrics` は 09-18 まで） |
| 6 | 🟠 `threads.json` が空 | **14日** | `{}` / 最終更新 09-04 |
| 7 | 🟠 画像ブリッジ pending 増加 | 継続 | **643**（前回602・**+41/日**）。failed 235 据え置き |
| 8 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 9 | 🟠 `orch-20260911-followup` 未マージ | **8日** | 3先行・**61遅れ** |
| 10 | 🟠 `.git` のゴミ | 悪化 | `tmp_obj_*` **375** / `stale_locks` **88** / `index.lock` 1 |
| 11 | 🟠 回帰テストが測れない | **8日** | サンドボックスに pytest 無し |
| 12 | 🟠 oripa `feat/stripe-checkout` 未マージ | **38日** | 9先行・0遅れ |
| 13 | 🟠 ai-english-coach リモート未設定 | 継続 | 凍結10日 |
| 14 | ⚪ fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 | 継続 | 変化なし |
| 15 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | 継続 | 作業は再開したがこの3件は未着手 |
| 16 | 🟠 oripa サイト本文が空 | **6日** | 到達するが body が空 |
| 17 | ⚪ clip-animal の `hard_constraints` 未設定 | 継続 | 停止中は無害 |
| 18 | ⚠️ `auto_optimize_schedule` による枠の自動書き換え | 継続 | socio-rx `[0,1,2]` のまま。**company-facts が `[3,4,5]`→`[1,4,5]` に変化** |

### 🆕 NEW

| # | 内容 |
|---|---|
| **N1** | 🔴 **`daily-merge-all-projects` は起動しているのに成果ゼロ・2日連続空振り。** スケジュールは生きている（09-18 22:05 実行）が、**`last_merge_log.md` は 09-16 のまま・09-18 のコミット0件・dirty 82件**。ログが無いので落ちた場所が追えない |
| **N2** | 🔴 **本日の指揮者 run の成果が全て未コミット。** `MEMORY_UPDATE_20260918.md` に ①読み上げ速度 `VOICEVOX_CHARS_PER_SEC` **8.9→6.95 再校正**（設計26秒が実測27〜35秒だった）②**33秒超が明確な負け群**（yokai 2.92倍 / ds 2.71倍）で文字数帯を引き下げ ③「15〜25%の崖」対策を5回改訂して効果ゼロと判定し打ち切り ―― **いずれもコミットされていない** |
| **N3** | 🔴 **サムネ403が「daily-science のみ成功」に収束。socio-rx が成功→失敗に転落。** 09-17 は ds4+socio1 成功、09-18 は ds3 のみ。**アカウント単位説を支持する方向だが、socio-rx が1日で裏返った理由は未説明** |
| **N4** | 🔴 **socio-rx は未使用キュー6件が全件規約違反＝実効在庫ゼロ。** `require_any_of` 6 / `min_effective_chars` 4 / `forbid_patterns` 3。**補充しないと明日から枠を落とす** |
| **N5** | 🟠 **2ch-matome の違反主因は `forbid_digits` 8件。** 未使用24件中9件違反。**題材が構造的に数字を含む**（09-15 の scp-lab mdg と同型）。8日止まっていたので前回まで見えなかった |
| **N6** | ⚠️ **`auto_optimize_schedule=true` は4ch**（company-facts / socio-rx / **akashic-librarian** / **fake-paper**）。前回「2ch」は稼働chだけを数えていた |
| **N7** | 🟠 **`data/job_queue.json` が 19.9MB（未追跡）。** ローテーションも上限も無い。実害は未確認だが観測項目に立てる |
| **N8** | ⚠️ **並走 run の原因が特定できた。** `nightly-full-progress` / `daily-project-handoff` / `vercel-migration-reminder` の3本が**同じ `0 23 * * *`** で登録され jitter(541/572/580s)だけで散っている。**cron をずらす以外に直らない** |
| **N9** | ℹ️ **`theme_queue` の要素に `used` キーが無い。「未使用件数」は実は「全件」。** キーは `id`/`title`/`angle` のみで消化済みが引けていない |
| **N10** | ℹ️ **登録者**: scp-lab 167(±0) / ds 75(±0) / cf **43(+1)** / yokai 29(±0) / **2ch-matome 11(+2)** / socio-rx 0。残7chは測定不能 |

### 📌 キュー在庫（3段）

| 段 | 09-17 | **09-18** |
|---|---:|---:|
| 総数（稼働6ch） | 87 | **61** |
| 公開可能ch分 | 61 | **61**（全ch公開可能に） |
| ゲート通過分 | 32 | **37** |

ch別通過在庫: 2ch 15 / yokai 7 / ds 7 / scp 5 / cf 3 / **socio-rx 0**。
消化 **16本/日** → **約2.3日ぶん。補充が無ければ 09-21 前後に枯れる。**

---

## 3. ユーザー手動待ちタスク一覧

**🚨 今すぐ（09-19 中に必ず）**

1. 🚨 **GCP OAuth 同意画面を「本番」へ公開**（project `844705815004`）— **失効 09-20 12:05・残り1.56日**
2. 🚨 **YouTube Studio でアカウント確認（電話番号）** — 対象が3ch→**5ch に拡大**（cf / scp / yokai / 2ch-matome / socio-rx）
3. 🚨 **`ANTHROPIC_API_KEY` を貼り直す**（`backend/.env` 18行目）
4. 🆕 🚨 **dirty 82件をコミット**（本日の再校正が1バイトも残っていない）
5. 🆕 🚨 **socio-rx のキュー補充**（6件全滅・実効在庫ゼロ）
6. 🆕 **`daily-merge-all-projects` の空振り原因を見る**

**判断が要るもの**

7. 🆕 2ch-matome の `forbid_digits` を緩めるか（⚠️ ただし「数字あり」は 09-17 実測で 0.72倍で負。外すなら根拠を測ってから）
8. 🆕 **23時台の cron 3本をずらす**（マーカー方式は5日連続で機能せず）
9. 🆕 サムネ403の切り分け（socio-rx が1日で裏返った理由）
10. `auto_optimize_schedule=true` の4ch を自動最適化に任せるか
11. 残7chの OAuth 再認可をどこまでやるか（akashic-librarian は実力3位）
12. 切り抜き4chを畳むか（全停止10〜12日・キュー0件）
13. fake-paper を止めるか作り直すか
14. `orch-20260911-followup` は破棄か cherry-pick（3先行・61遅れ・8日）
15. oripa `feat/stripe-checkout` を main へマージするか（38日）
16. company-facts の枠 4→3 差し戻し（09-21 判定。本日も4本公開）
17. いいね率 vs 維持率のどちらを先行指標にするか（09-21 本判定）

**環境の掃除（Mac 側でないと消せない）**

18. `rm -f .git/*.lock .git/refs/heads/*.lock`（`index.lock` 1件）
19. `rm -rf .git/stale_locks .git/_stale* .git/_locksink .git/_trash_consolidated .git/_scratch_delme .git/_writetest`（**88件**＋8ディレクトリ）
20. `find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**375件**）
21. ホストで `pytest backend/tests`（**8日間**未測定。今日 `shorts_length_guard.py` を触っているので必須）
22. `git remote remove neworigin`
23. 🆕 `data/analytics.db`(0B) / `data/video_status.db`(0B) の空ファイルを確認・削除
24. 🆕 `data/job_queue.json` 19.9MB の上限・ローテーション要否

**aiseki（09-18 再始動）**

25. 🆕 worker の未コミット9件をコミット（`instagram.mjs` / `dm_report.mjs` / `launchd/` / `marketing_見直し案_20260918.md`）
26. Twilio 本番アップグレード / `dm_targets` CSV 取り込み（実在確認＋非公開判定）/ 営業本番の開始判断（先頭 `1000bero_net`・1日30件・間隔30〜120秒は変えない）
27. ロゴ生成 → Instagram プロフ写真差し替え / SNS 初投稿（投稿0件）
28. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
29. 実機動作確認 / 運営体制（通報対応者・営業許可・本店所在地）

**ai-english-coach**

30. **GitHub リモートの作成と push**（09-08 以降ローカルのみ＝バックアップ無し・10日）
31. LINE Pay 加盟店申込（審査があるので最優先）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

32. ChatGPT スレッドURLを13ch分登録（`threads.json` が `{}` のまま**14日**）/ 画像ブリッジ pending **643**・failed 235 の処理方針
33. oripa サイト本文が空（**6日連続**）
34. ⚠️ oripa の最長リードタイムは古物商許可（審査約40日）
35. fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 の整理（任意）
36. rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach は**リモート未設定**（バックアップ無し）

---

## 4. 次回（09-19）に確認すること

- 🚨 **OAuth が公開されたか**（未対応なら次の夜間 run 時には既に失効の可能性）
- 🆕 **コミットされたか**（本日 dirty 82・コミット0）。**再校正が稼働系に載ったか**（「実装≠稼働」の3例目にしない）
- 🆕 **`daily-merge-all-projects` が `last_merge_log.md` を書いたか**
- **サムネ403が止まったか**（今日13/16・成功は ds のみ。**socio-rx が戻るか**）
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数**（今日16本・取りこぼし0）。**2ch-matome が2日連続で出るか**
- 🆕 **socio-rx が1本でも公開できたか**（キュー全滅のまま補充が無ければ0本）
- 🆕 **2ch-matome の `forbid_digits` 違反8件が減ったか**
- **キューのゲート通過分**（今日37件・16本/日 → **09-21 前後に枯れる**）
- **`channel_metrics` の遅れ**（今日 09-15＝3日遅れ）／**画像ブリッジ pending**（643・+41/日）／🆕 **`job_queue.json` のサイズ**（19.9MB）
- **09-20**: OAuth 失効日 / **09-21**: 枠・型変更の本判定、cf 枠4→3、いいね率 vs 維持率 / **09-23**: 2ch-matome 再開の評価（**09-18 再開なのでここから5日**） / **09-24**: 09-17 の変更2件・「のか」追加・「なぜ／のか」の独立コホート再測

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`title_constraints.check()` の第2引数は「チャンネル JSON 全体」であって `hard_constraints` ではない。** `hard_constraints` を渡すと規則が1つも見つからず**全件 `ok:True`**（2文字の「短い」すら通る）。本日これを踏んで「違反0件」と出した。**必ず違反するはずの文字列を1本流して `ok:False` を確認してから集計する。**
- 🆕 🔴 **`theme_queue` の要素に `used` キーは存在しない**（`id`/`title`/`angle` のみ）。「未使用」は実質「全件」。在庫を語るときはこの限界を明記するか公開実績と突き合わせる。
- 🆕 **`min_effective_chars` には例外がある。** `なぜ.{2,}の(?:か|？)` に一致すると下限が 20→**15字**。「19字だから違反」と手で判定しない。必ず `check()` を通す。
- 🆕 **`Autopilot fired` の合計と当日公開本数を突き合わせる。** 一致していれば「発火したが公開されなかった枠」は無いと即断できる。ズレたときだけ `publish_blocked` を読みに行く。
- 🆕 **スケジュールの生死は `list_scheduled_tasks` の `lastRunAt` で見る。ログの有無で判断しない。** 09-17 に「スケジュールが死んでいるか」と書いたが、実際は生きていて中身が空振りだった。**対処がまったく違う。**
- 🆕 **並走 run は cron を見れば事前に分かる。** 23時台に3本が同じ `0 23 * * *` で登録され jitter だけで散っている。マーカーファイルでは避けられない。
- 🆕 **ローテーション導入後、`backend.log` は当日ぶんしか無い。** 前日以前は `logs/backend.log.*.gz` を展開する。**「ログに無い＝起きていない」は当日についてしか言えない。**
- 🔴 **`Autopilot fired` が0でも「発火に失敗した」とは限らない。`Autopilot scheduled for <ch>` も0ならジョブが登録されていない。** 原因が全く違う。
- 🔴 **`publish_blocked` は理由の種別まで読む。** 直前行の `⛔ publish_blocked:` を見る。タイトル系（ゲート緩和）とファクト系（台本・台帳修正）で打ち手が違う。
- **キュー在庫は「総数／公開可能ch分／ゲート通過分」の3段で書く。**
- **`autopilot.schedule.times` の各 slot は `days_of_week` を持ち top-level とは別。slot 側が勝つ。**
- **`auto_optimize_schedule=true` の ch（現在4ch）は backend が枠を勝手に書き換える。** 前日差分が指揮者の変更とは限らない。`current slot underperforms recommended by` をログで探す。
- **`logs/backend.log` の tail は毎回ユニークな一時ファイル名にする。** `/tmp/bl.txt` や `/tmp/rc/` は使わない。
- **ログ内イベントの新旧は「今日の既知 `video_id` の出現位置」を基準に判定する**（行頭にタイムスタンプが無い）。
- 🔴 **`git status` の前に必ず `cp .git/index /tmp/<ユニーク名> && export GIT_INDEX_FILE=/tmp/<ユニーク名>`。** 空の `GIT_INDEX_FILE` を指すと**全追跡ファイルが `D` に見える。**
- **サムネの失敗は403だけではない。** `サムネイル設定失敗` は初回＋retry で行数が2倍になるので **distinct な video_id で数える。**
- **公開実績は `data/video_publish.db` の `video_status`。** `data/video_status.db` は**0バイトの空ファイル**。間違えないこと。
- **`video_status.published_at` は UTC（`Z`）。** +9h してから日付を切る。公開の真偽は `video_id` の有無。
- **analytics DB は `data/analytics/analytics.db`・日付カラムは `date`。** `data/analytics.db` も0バイトの空ファイル。
- **`video_metrics.views` は直近30日窓。** 同一動画でも日をまたいで減る。「再生が減った」と読まない。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。**登録者数も latest.md が唯一のソース。**
- **`latest.md` の「人/1000再生」は直近30日窓、指揮者の「登録/千」は直近50本ローリング窓。別の数字。**
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。`min_effective_chars` は `UNREPAIRABLE_RULES`。
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-18.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクトは**読み取りのみ**。
