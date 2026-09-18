# 全プロジェクト 引き継ぎレポート — 2026-09-18（金）

**実行**: `daily-project-handoff`（スケジュール実行 / 承認者不在）
**前回**: 2026-09-17 23:25
**参照した文脈**: `last_handoff_log.md`(09-17)、`last_merge_log.md`(**09-16 22:09 のまま**)、`.auto-memory/` の 09-10〜09-17・INDEX.md、`MEMORY_UPDATE_20260918.md`

> ℹ️ bash 完走。git・sqlite・ログ・キュー・サイト疎通を全て実測。
> ℹ️ 主要13項目を別エージェントで独立再計測 → **不一致0件**。副次的に2件の新事実を検出（`data/job_queue.json` 19.9MB / `theme_queue` に `used` キーが無い）。
> ✅ **前回の最優先3件のうち2件が解決した。** backend 再起動（N2）と push（#19）が実行され、**2ch-matome が8日ぶりに公開を再開**した。
> ⚠️ **本日のコミットは0件。** 指揮者 run の成果（読み上げ速度の再校正など）が全て未コミットで、dirty 82件が滞留している。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-18 は16本公開（過去最多・取りこぼし0・publish_blocked 0件）**。2ch-matome 復活・ログローテ実装・push 完了。**残る最大の期限は OAuth 失効まで1.56日**、🆕 **サムネ403が13/16に悪化（成功は daily-science のみ）**、🆕 **本日コミット0でマージ run も空振り** |
| aiseki | 🟢 **再始動（3日ぶり）** | 09-18 に Instagram worker / DM レポート / launchd を実装。**ただし全て未コミット（dirty 9）**。aisekimatch.com 正常 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**10日**。dirty 0。**リモート未設定＝バックアップ無し**（継続） |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**18日**。未追跡25件。サイト正常（サポーター1,248／進行中3件の表示） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**38日**。HEAD が `feat/stripe-checkout`（main に9先行・0遅れ）。**サイト本文が空（6日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・OAuth 全失効。最終公開 09-06〜09-08＝**10〜12日**。`clip-animal` のみ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 88日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 76日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | `a8974fd`(09-18) が最新。origin と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし。未追跡1・リモート未設定 |

**本日の公開（`video_id` 実在ベース・JST）**: cf 4 / ds 3 / scp 3 / yokai 3 / **2ch-matome 2** / socio 1 = **16本**
`Autopilot fired` 16回 = 公開16本で**完全一致**。`この枠は公開を止めました` **0件**。

---

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **N1/N2「2ch-matome は APScheduler にジョブが無い」「cron 貼り直しの修正が未コミット・未再起動」→ 両方 解決。**
  コミット `3e47dcd` で `_on_channel_config_reloaded()` / `_autopilot_fingerprint()` が入り、backend も再起動された（`Application startup complete` ×1）。
  **`Autopilot scheduled for 2ch-matome` が 8回**出て、**fired 2回・公開2本**（07:30 / 17:30）。最終公開 09-10 から**8日ぶり**。
- **#19「未push コミット11件」→ 解決。** `git rev-list --left-right --count origin/main...HEAD` が **`0 0`**。ホスト側で push 済み。
- **#10「`logs/backend.log` ローテーション未実装」→ 解決。** `scripts/rotate_backend_log.sh` + launchd `com.youtube-factory.logrotate`（毎日04:30・20MB超で copytruncate・7世代）。
  **88.7MB → 1.21MB**。`backend.log.20260917_233726.gz`(6.8MB) が生成済み。
- **N4/N5「未使用キューの63%が規約違反・20字下限と『なぜ／のか』型が衝突」→ 大幅改善。**
  「なぜ〜のか」型に限り `min_effective_chars` を 20→**15字**へ緩和（一律引き下げは逆U字の実測と矛盾するため却下、という判断も併せて記録されている）。
  **違反 55/87(63%) → 24/61(39%)**、`min_effective_chars` 違反は **35 → 12件**。
- **N3「`publish_blocked` にファクト整合違反が出た」→ 本日は再発なし。** `data/fact_ledger/company-facts.json` が55行追記され、**本日の publish_blocked は0件**。
- **N9「`daily-merge-all-projects` のスケジュールが生きているか」→ スケジュールは生きている。** 09-18 22:05 に実行済み（`lastRunAt` 2026-09-18T13:05Z）。**ただし成果ゼロ＝別の問題として下の 🆕N1 に立てた。**
- **「socio-rx のサムネがパス未指定」→ コード側は修正済み**（monologue 分岐が `generate_short_thumbnail` を呼ぶようになった）。**ただし403は別問題で未解決**（下記 #2）。

### ❌ 未解決

| # | 内容 | 継続 | 09-18 の実測 |
|---|---|---|---|
| 1 | 🔴 GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 1.56日。失効 `2026-09-20 12:05`。あと1回の夜間 run しか猶予が無い** |
| 2 | 🔴 サムネ403 | **7日**・**悪化** | 16本中 **13本失敗**（cf 4 / scp 3 / yokai 3 / 2ch 2 / socio 1）。**成功は daily-science 3本のみ** |
| 3 | 🔴 `ANTHROPIC_API_KEY` 401 | 継続 | `latest.md` 全chに「ANTHROPIC_API_KEY が無効（認証エラー）」 |
| 4 | 🔴 OAuth 未再認可の残7ch | 継続 | 全件 `Token has been expired or revoked.` |
| 5 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終日 **09-15**（`video_metrics` は 09-18 まで取得済み・10,223行） |
| 6 | 🟠 画像ブリッジ `threads.json` が空 | **14日** | `{}` / 最終更新 09-04 17:04 |
| 7 | 🟠 画像ブリッジ pending 増加 | 継続 | **643**（前回602・**+41/日**）。failed 235 据え置き（09-08 で停止） |
| 8 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 9 | 🟠 `orch-20260911-followup` 未マージ | **8日** | **3先行・61遅れ**（遅れ 60→61） |
| 10 | 🟠 `.git` のゴミ | **悪化** | `tmp_obj_*` **375**（前回366）／`stale_locks` **88**（前回86）／`index.lock` 1（09-18 10:10 の残骸） |
| 11 | 🟠 回帰テストが測れない | **8日** | サンドボックスに pytest 無し |
| 12 | 🟠 oripa `feat/stripe-checkout` 未マージ | **38日** | 9先行・0遅れ |
| 13 | 🟠 ai-english-coach: リモート未設定 | 継続 | `git remote -v` 空。凍結10日 |
| 14 | ⚪ fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 1 / ai-orchestrator 1 | 継続 | 変化なし |
| 15 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | 継続 | **作業は再開した**が、この3件自体は未着手のまま |
| 16 | 🟠 oripa サイト本文が空 | **6日** | 到達するが body が空 |
| 17 | ⚪ clip-animal の `hard_constraints` 未設定 | 継続 | 停止中は無害。再開した瞬間に検査が丸ごとスキップ |
| 18 | ⚠️ `auto_optimize_schedule` による枠の自動書き換え | 継続 | socio-rx の top-level `days_of_week` は `[0,1,2]` のまま。**company-facts は `[3,4,5]` → `[1,4,5]` に変わった**（また動いた） |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🔴 **`daily-merge-all-projects` は起動しているのに成果がゼロ。2日連続の空振り。** | スケジュールは生きていて 09-17・09-18 とも実行済み（`lastRunAt` 09-18T13:05Z）。しかし **`last_merge_log.md` は 09-16 22:10 のまま**、**09-18 のコミットは0件**、dirty は **82件**（tracked 43 / untracked 41）。前回「スケジュールが死んでいるか」を疑ったが、**死んでいるのはスケジュールではなくタスクの中身。** ログすら書かれていないので、どこで落ちているかがレポートから追えない |
| **N2** | 🔴 **本日の指揮者 run の成果が全て未コミット。** | `MEMORY_UPDATE_20260918.md`(10:20) に大きな発見が3件記録されている ―― ①読み上げ速度 `VOICEVOX_CHARS_PER_SEC` が **8.9 → 6.95 に再校正**（1.28倍の過大評価で、設計26秒が実測27〜35秒になっていた）②**33秒超が明確な負け群**（yokai 2.92倍 / ds 2.71倍）で文字数帯を引き下げ ③「15〜25%の崖」対策を**5回改訂して効果ゼロと判定し打ち切り**。**いずれもコミットされていない。**`backend/pipeline/shorts_length_guard.py` が dirty のまま |
| **N3** | 🔴 **サムネ403が「daily-science のみ成功」に収束した。socio-rx が成功→失敗に転落。** | 09-17 は成功 ds 4 + socio 1、09-18 は **成功 ds 3 のみ**。失敗13本は5ch全てにまたがる。**アカウント単位説を支持する方向だが、socio-rx が1日で裏返った理由は説明できていない。** 403 の本文は全件 `The authenticated user doesn't have permissions to upload and set custom video thumbnails.`（1件だけ初回が `The thumbnail can't be set for the specified video.`） |
| **N4** | 🔴 **socio-rx は未使用キュー6件が全件規約違反＝実効在庫ゼロ。** | 違反内訳 `require_any_of` 6 / `min_effective_chars` 4 / `forbid_patterns` 3（末尾疑問符）。「水泳が心に与える影響とは？」「解雇の心理学: どう向き合うべきか？」など、**答え提示語なし＋末尾疑問符＋短い**の三重違反。**補充しない限り socio-rx は明日から枠を落とす** |
| **N5** | 🟠 **2ch-matome の違反主因は `forbid_digits` 8件。復活した途端に顕在化した。** | 未使用24件中9件が違反、うち8件が数字。「なぜ合コンの帰り道は**3**人だけ無言になるのか」等。**この ch のテーマ生成は構造的に数字を入れる**（09-15 の scp-lab `max_digit_groups` と同型の衝突）。8日止まっていたので前回まで見えなかった |
| **N6** | ⚠️ **`auto_optimize_schedule=true` は4ch。前回「2ch」は稼働chだけを数えていた。** | company-facts / socio-rx に加えて **akashic-librarian / fake-paper** も true。現在OFFなので無害だが、**再開した瞬間に枠が勝手に動く ch が2つ増える** |
| **N7** | 🟠 **`data/job_queue.json` が 19.9MB（未追跡）。** | `.gitignore` 対象で追跡外。中身は `{version, jobs}`。ローテーションも上限も無いので backend.log と同じ経路で膨らむ可能性がある。**今は実害が確認できていないので観測項目として立てる** |
| **N8** | ⚠️ **並走 run の原因が特定できた。23時台に3つのタスクが同時に登録されている。** | `nightly-full-progress`(cron 23:00・jitter 541s→23:09)、`daily-project-handoff`(23:00・jitter 572s→23:09)、`vercel-migration-reminder`(23:00・jitter 580s→23:09)。**本日は nightly-full-progress の30秒後に本タスクが起動した。**「マーカーファイルで避ける」ではなく**cron をずらすのが正しい対処**（例: nightly 22:30 / handoff 23:10 / vercel 23:40） |
| **N9** | ℹ️ **`theme_queue` の要素に `used` キーが存在しない。「未使用件数」は実は「全件」。** | キーは `['id','title','angle']` のみ。**消化済みかどうかはこの JSON では判別できない。** 過去レポートの「未使用87件」も同じ数え方なので前日比較は成立するが、**「在庫」という語の意味が実態と違う。** 実際の在庫判定は公開実績（本日16本消化）と突き合わせるしかない |
| **N10** | ℹ️ **登録者** | scp-lab **167**(±0) / daily-science **75**(±0) / company-facts **43**(+1) / yokai-watch **29**(±0) / **2ch-matome 11(+2)** / socio-rx 0。**残7chは測定不能。** 2ch-matome は公開再開日に +2 |

### 📌 キュー在庫（3段で書く・09-17 の鉄則に従う）

| 段 | 09-17 | **09-18** |
|---|---:|---:|
| 総数（稼働6ch） | 87 | **61** |
| うち公開可能 ch 分 | 61（2ch-matome 除外） | **61**（除外なし＝全ch公開可能に） |
| うちゲート通過分 | 32 | **37** |

消化は **16本/日**。**ゲート通過分 37件 ÷ 16 ≒ 2.3日**。補充が無ければ **09-21 前後に枯れる**。
ch別の通過在庫: 2ch-matome 15 / yokai 7 / ds 7 / scp 5 / cf 3 / **socio-rx 0**。

---

## 3. ユーザー手動待ちタスク一覧

**🚨 今すぐ（09-19 中に必ず）— この順番で**

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / `console.cloud.google.com/auth/audience`）
   **失効 `2026-09-20 12:05`・残り1.56日。夜間 run はあと1回しか回らない。同意画面を先に公開してから再認可。**
2. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch`（`youtube.com/verify`）
   **7日連続で最優先のまま。今日は 2ch-matome / socio-rx も403に加わったので対象は5chに増えた。**
3. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに貼り直す**（`backend/.env` 18行目）
4. 🆕 🚨 **dirty 82件をコミットする。** 本日の指揮者 run の成果（読み上げ速度の再校正 8.9→6.95、文字数帯の引き下げ、崖対策の打ち切り）が1バイトも残っていない。
   `cd ~/Developer/youtube-factory && git add -A && git commit`
5. 🆕 🚨 **socio-rx のキューを補充する（N4）。** 6件全てが規約違反で**実効在庫ゼロ**。明日から枠を落とす。
6. 🆕 **`daily-merge-all-projects` が空振りしている原因を見る（N1）。** 2日連続で起動はしているのにログもコミットも無い。

**判断が要るもの**

7. 🆕 **2ch-matome の `forbid_digits` をどうするか（N5）。** この ch の題材は構造的に数字を含む。**09-16 の scp-lab（mdg=1→2）と同じ判断が要る。**
   ⚠️ ただし 09-17 の実測で「数字あり」は **0.72倍で負**（ch内一致は 1/3ch と弱い）。**外すなら根拠を測ってから。**
8. 🆕 **23時台の cron を3本ともずらす（N8）。** マーカーファイル方式は5日連続で機能していない。**スケジュール側でしか直らない。**
9. 🆕 **サムネ403の切り分け（N3）。** socio-rx が1日で成功→失敗に転落した。**アカウント確認だけで説明できるか、別の要因があるかを見る。**
10. **`auto_optimize_schedule=true` の4ch を自動最適化に任せるか（N6）。** company-facts の `days_of_week` がまた動いた（`[3,4,5]`→`[1,4,5]`）
11. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。akashic-librarian は実力3位）
12. 切り抜き4chを畳むか（全停止10〜12日・`theme_queue` は0件）
13. fake-paper を止めるか作り直すか（OFF・キュー2件）
14. **`orch-20260911-followup` は破棄か cherry-pick**（3先行・**61遅れ**・8日放置）
15. oripa `feat/stripe-checkout` を main へマージするか（9先行・0遅れ・**38日**放置）
16. **company-facts の枠 4→3 差し戻し**（09-21 に判定。本日も4本公開している）
17. **いいね率 vs 維持率のどちらを先行指標にするか**（09-21 本判定）

**環境の掃除（Mac 側でないと消せない）**

18. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`（`index.lock` 1件・09-18 10:10 の残骸）
19. `rm -rf .git/stale_locks .git/_stale* .git/_locksink .git/_trash_consolidated .git/_scratch_delme .git/_writetest`（**88件**＋8ディレクトリ）
20. `find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**375件**）
21. ホストで `pytest backend/tests` を1回流す（**8日間**測れていない。**特に今日は `shorts_length_guard.py` を触っているので必須**）
22. **`neworigin` リモートを削除してよい**（`git remote remove neworigin`）
23. 🆕 `data/analytics.db`(0B) と `data/video_status.db`(0B) は実体と別の空ファイル。**パス指定ミスで作られた疑いがある**ので中身を確認して削除してよい
24. 🆕 `data/job_queue.json` が 19.9MB（N7）。上限・ローテーションの要否を判断

**aiseki（09-18 に再始動）**

25. 🆕 **worker の未コミット分をコミットする**（`worker/instagram.mjs` / `dm_report.mjs` / `launchd/` / `marketing_見直し案_20260918.md` の9件）
26. **Twilio 本番アップグレード** ／ `dm_targets` の CSV 取り込み（**実在確認＋非公開判定を入れる**）／ 営業本番の開始判断（先頭 `1000bero_net`・1日30件/間隔30〜120秒は変えない）
27. **ChatGPT でのロゴ生成 → Instagram プロフ写真の差し替え**、**SNS 初投稿**（素材 `sns_assets/`・文面 `sns_posts.md`・投稿0件）
28. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
29. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

30. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝**バックアップ無し**・10日）
31. LINE Pay 加盟店申込（**審査があるので最優先**）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

32. **ChatGPT スレッドURLを13ch分登録**（`threads.json` が `{}` のまま**14日**）／画像ブリッジ pending **643**（+41/日）・failed 235 の処理方針
33. oripa サイトの本文が空（**6日連続**）— ビルドかルーティングの確認
34. ⚠️ **oripa の最長リードタイムは古物商許可（審査約40日）。** 着手が遅れるほど開業日がそのまま後ろへ動く
35. fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 1 / ai-orchestrator 1 の整理（任意）
36. **rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach はリモート未設定**（バックアップ無し）。GitHub へ退避

---

## 4. 次回（09-19）の実行時に確認すること

- **🚨 OAuth が公開されたか。** 未対応なら**残り0.5日程度**で、次の夜間 run のときには既に失効している可能性が高い
- 🆕 **コミットされたか**（本日 dirty 82・コミット0）。**`shorts_length_guard.py` の再校正が稼働系に載ったか**（「実装≠稼働」の3例目にしないこと）
- 🆕 **`daily-merge-all-projects` が `last_merge_log.md` を書いたか**（09-16 から止まっている）
- **サムネ403が止まったか。** 今日は13/16で成功は daily-science のみ。**socio-rx が戻るかを見る**
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数**（09-18 は16本・fired=公開で取りこぼし0・publish_blocked 0）。**2ch-matome が2日連続で出るか**
- 🆕 **socio-rx が1本でも公開できたか**（キュー6件全滅のまま補充が無ければ0本になる）
- 🆕 **2ch-matome の `forbid_digits` 違反8件が減ったか**
- **キューのゲート通過分**（今日37件・消化16本/日 → **09-21 前後に枯れる**）
- **`channel_metrics` の遅れが縮まったか**（今日 09-15＝3日遅れ）
- **画像ブリッジ pending**（643 → +41/日の傾きが続くか）
- 🆕 **`data/job_queue.json` のサイズ**（今日 19.9MB）
- **09-20**: OAuth 失効日 / **09-21**: 09-14 枠・型変更の本判定、cf 枠 4→3、いいね率 vs 維持率 / **09-23**: 2ch-matome 再開の評価期日（**09-18 に再開したので、ここから5日**） / **09-24**: 09-17 の枠変更2件・「のか」追加・キュー並べ替えの評価、および「なぜ／のか」の独立コホート再測

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`title_constraints.check()` の第2引数は「チャンネル JSON 全体」であって `hard_constraints` ではない（2026-09-18 追加）。** シグネチャは `check(title, channel_dict)`。`hard_constraints` を渡すと**規則が1つも見つからず全件 `ok:True` になる**（「短い」という2文字のタイトルすら通る）。本日これを最初に踏んで「違反0件」と出した。**サニティチェックとして、必ず違反するはずの文字列（例: `"短い"`）を1本流して `ok:False` が返ることを確認してから集計する。**
- 🆕 🔴 **`theme_queue` の要素に `used` キーは存在しない（2026-09-18 追加）。** キーは `id` / `title` / `angle` のみ。**「未使用」という集計は実質「全件」であって、消化済みを引けていない。** 在庫を語るときはこの限界を明記するか、公開実績と突き合わせること。
- 🆕 **`Autopilot fired` の合計と当日の公開本数を突き合わせる（2026-09-18 追加）。** 本日は 16 = 16 で一致した。**一致していれば「発火したが公開されなかった枠」は無い**と即断できる。ズレたときだけ `publish_blocked` を読みに行けばよい。
- 🆕 **スケジュールの生死は `list_scheduled_tasks` の `lastRunAt` で見る。ログの有無で判断しない（2026-09-18 追加）。** 09-17 に「`daily-merge-all-projects` のスケジュールが死んでいるか」と書いたが、**スケジュールは生きていて中身が空振りしていた**。この2つは対処がまったく違う。
- 🆕 **並走 run は cron を見れば事前に分かる（2026-09-18 追加）。** 23時台に `nightly-full-progress` / `daily-project-handoff` / `vercel-migration-reminder` の3本が同じ `0 23 * * *` で登録され、jitter だけで散っている（541s / 572s / 580s）。**マーカーファイルでは避けられない。**
- 🔴 **`Autopilot fired` が0でも「発火に失敗した」とは限らない。`Autopilot scheduled for <ch>` も0なら、ジョブがそもそも登録されていない。** 09-17 の 2ch-matome は後者だった（09-18 に解決）。
- 🔴 **`publish_blocked` は理由の種別まで読む。** `この枠は公開を止めました` の grep で終わらせず、直前行の `⛔ publish_blocked:` を見る。タイトル規約違反（ゲート緩和）とファクト整合違反（`数値の矛盾:`／台本・台帳修正）で打ち手がまったく違う。
- 🆕 **キュー在庫は「総数／公開可能ch分／ゲート通過分」の3段で書く。** 本日は 61 / 61 / 37。
- **`autopilot.schedule.times` の各 slot は `days_of_week` を持ち、top-level とは別。slot 側が勝つ。**
- **`auto_optimize_schedule=true` の ch は backend が枠を勝手に書き換える。** 現在 4ch（company-facts / socio-rx / akashic-librarian / fake-paper）。前日との差分が指揮者の変更とは限らない。`current slot underperforms recommended by` をログで探す。
- **`logs/backend.log` の tail は毎回ユニークな一時ファイル名にする。** `/tmp/bl.txt` や `/tmp/rc/` のような固定名は使わない。
  - 🆕 **ローテーションが入ったので `backend.log` は当日ぶんしか無い（2026-09-18 追加）。** 前日以前を見るには `logs/backend.log.*.gz` を展開する。**「ログに無い＝起きていない」は、ローテ以降は当日についてしか言えない。**
- **ログ内のイベントの新旧は「今日の既知 `video_id` の出現位置」を基準に判定する。** 行頭にタイムスタンプが無い。
- 🔴 **`git status` の前に必ず `cp .git/index /tmp/<ユニーク名> && export GIT_INDEX_FILE=/tmp/<ユニーク名>` する。** 空の `GIT_INDEX_FILE` を新規に指すと**全追跡ファイルが `D`（削除）に見える。**
- **サムネの失敗は403だけではない。** `ℹ️ サムネイルパス未指定` は試行すらしていない別の失敗（本日0件）。`サムネイル設定失敗` の行数は初回＋retry で2倍になるので、**distinct な video_id で数える。**
- **`latest.md` の「人/1000再生」は直近30日窓、指揮者の「登録/千」は直近50本ローリング窓。別の数字。前日比で並べてはいけない。**
- **`autopilot.enabled` を JSON 直書きで true にしても発火しない**（cron を貼り直すのは `_save_autopilot()` → `_refresh_channel_job()` の経路だけ）。**ただし 09-17 の `_on_channel_config_reloaded()` で、ディスク再読み込み時に指紋が変われば貼り直されるようになった。**
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。**`min_effective_chars` は `UNREPAIRABLE_RULES`＝修復対象外。**
- 🆕 **`min_effective_chars` には例外がある（2026-09-18 追加）。** `_WHY_PATTERN_RE = なぜ.{2,}の(?:か|？)` に一致すると下限が 20→**15字**に緩む。**「19字だから違反」と手で判定しない。必ず `check()` を通す。**
- **analytics DB は `data/analytics/analytics.db`・日付カラムは `date`。** 公開実績は **`data/video_publish.db` の `video_status`**（`data/video_status.db` は0バイトの空ファイル。**間違えないこと**）。
- **`video_metrics` の views は直近30日窓。** 同一動画でも日をまたいで**減る**。「再生が減った」と読まない。
- **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。公開の真偽は `video_id` の有無。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。
- **`data/reports/latest.md` が登録者数の唯一のソース。** OAuth が生きている ch しか値が入らない。
- **views のラグは約2日。**
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-18.md`（新規・本ファイル）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform / ai-orchestrator）は**読み取りのみ**。
