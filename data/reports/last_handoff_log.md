# Daily Handoff Log

**実行日時**: 2026-09-20 23:10 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-20.md`
**前回**: 2026-09-19 23:20 / **参照した文脈**: `last_handoff_log.md`(09-19)、`last_merge_log.md`(**09-19 22:08 のまま＝本日未更新**)、`.auto-memory/` の 09-10〜09-19・`INDEX.md`・`projects/`、`MEMORY_UPDATE_20260920.md`

> ℹ️ bash 完走。git・sqlite・ログ・キュー・サイト疎通を全て実測。主要12項目を別エージェントで独立再計測 → **不一致 0件**。
> ✅ **6夜連続で最優先だった OAuth が解決。** 同意画面が本番公開され、**稼働6ch＋pokemon-lab の7chが無期限トークン**で再発行。**pokemon-lab 再認可（指揮者の唯一の依頼）も完了。**
> 🆕 **リーチ天井（前回N3）の原因がエンドカードに特定され、本日A/Bが開始。判定 09-27。それまで5chの `short_endcard` を触ってはいけない。**
> 🔴 **scp-lab のキューが 0 件 / socio-rx 通過0件が3日連続。**

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応（期限なし）** | **公開14本**（枠15・失効の瞬間に scp-lab 1枠を落とした）。✅ **OAuth解決・7ch無期限**。🆕 **エンドカードA/B開始（判定09-27）**。🔴 **scp-lab キュー0件**。本日コミット2件・dirty 71・未マージ0・neworigin 同期 |
| aiseki | 🟡 **本日は停止** | 🆕 **09-20 のコミット0件**（前日まで2日連続で稼働）。dirty 0・neworigin 同期。aisekimatch.com 正常 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**12日**。dirty 0。**リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**20日**。未追跡25件。サイト正常 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**40日**。HEAD は `feat/stripe-checkout`（未マージ）。**サイト本文が空（8日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・**OAuth も再認可されなかった**。最終公開 clip-lab/kaneko/fukada **09-09**・clip-animal **09-06**＝**11〜14日**。キュー0件 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 90日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 78日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | `a8974fd`(09-18)・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし |

**本日の公開（JST・`video_id` 実在ベース）**: cf 4 / ds 3 / yokai 3 / scp 2 / socio 1 / 2ch 1 = **14本**
**日別**: 09-14 18 / 09-15 13 / 09-16 14 / 09-17 14 / 09-18 16 / 09-19 15 / **09-20 14**
**発火15回 vs 公開14本** — 差の1件は N2（OAuth 失効の瞬間の `自動公開スキップ`）。

**OAuth（`logs/backend.log` の `♾️ [oauth] ... 無期限で発行されました` で確認）**

| ch | 状態 |
|---|---|
| 2ch-matome / company-facts / daily-science / scp-lab / socio-rx / yokai-watch / **pokemon-lab** | **OK・無期限（7ch）** |
| akashic-librarian / fake-paper / clip-lab / clip-fukada / clip-kaneko / clip-animal | ❌ 失効のまま（6ch）。**本番公開済みなので今やれば無期限になる** |

**登録者（latest.md 09-20 22:30）**: scp-lab **169(-1)** / ds **74(-2)** / cf 44(±0) / yokai **28(-3)** / **pokemon-lab 15（測定再開）** / 2ch 11(±0) / socio-rx 0。**稼働6ch計 326(-6)**。⚠️ **n=1日なので構造的説明を与えない。**

---

## 2. 検出した課題

### ✅ 解決済み（次回「要対応」として報告しないこと）

- **🚨 #1「GCP OAuth 同意画面がテスト中」→ 解決。** 本番公開され7chが無期限化。**09-14 から6夜連続の期限付きブロッカーが消えた。**
- **🔴 #2「pokemon-lab 未再認可」→ 解決。** 指揮者が4日連続で出していた唯一の依頼。**ただし autopilot は OFF のまま（N3）。**
- **前回N3「リーチ天井の原因不明」→ 仮説が1本に絞られ検証が走った。** エンドカード。09-27 判定。**「原因不明」としては報告しない。**
- **aiseki #26「未適用マイグレーションの有無が判定不能」→ 所在が判明。** `supabase/migration_*.sql` のフラット29ファイル。`apply_migrations.command` は3本のみ適用。
- **前回N1「サムネ2MB超」→ 本日は再発なし**（n=1日）。
- **#9「未マージブランチ」→ 3リポジトリとも 0 件。**
- **#17「`auto_optimize_schedule=true` 4ch」→ 半減。** 残は company-facts / socio-rx の2chのみ。

### ❌ 未解決

| # | 内容 | 継続 | 09-20 実測 |
|---|---|---|---|
| 1 | 🔴 **scp-lab のキューが0件** | 🆕 | 枠3/日に対し在庫ゼロ |
| 2 | 🔴 socio-rx のキュー通過0件 | **3日** | 5件中0件通過。09-18 から1件も直っていない |
| 3 | 🔴 OAuth 未再認可の残6ch | 継続 | akashic-librarian / fake-paper / clip系4 |
| 4 | 🔴 `ANTHROPIC_API_KEY` 401 | **9日** | latest.md 全chで「認証エラー」。キーは `backend/.env` 18行目に存在 |
| 5 | 🟠 サムネ403 | 9日 | 14本中11本。成功は daily-science 3本のみ（3日連続同じ分かれ方）。優先度は引き下げ済み |
| 6 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終 **09-17**（`video_metrics` は 09-20）。前回から1日進んだ |
| 7 | 🟠 `threads.json` が空 | **16日** | `{}` / `data/image_requests/threads.json` |
| 8 | 🟠 画像ブリッジ pending 増加 | 継続 | **724**（前回684・**+40/日**）。failed 235 は新規なし |
| 9 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 10 | 🟠 `.git` のゴミ | 横ばい | `tmp_obj_*` **623** / `stale_locks` **88** / `_stale` **34**（前回と同数） |
| 11 | 🟠 回帰テストが測れない | **10日** | サンドボックスに pytest 無し |
| 12 | 🟠 oripa `feat/stripe-checkout` 未マージ | **40日** | HEAD がこのブランチのまま |
| 13 | 🟠 oripa サイト本文が空 | **8日** | 到達するが body が空 |
| 14 | 🟠 ai-english-coach リモート未設定 | 継続 | 凍結12日 |
| 15 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | 継続 | 変化なし |
| 16 | ⚠️ 23時台の cron 並走 | **8日** | `nightly-full-progress` と本タスクが 23:09 で同時 |
| 17 | 🟠 `data/job_queue.json` 20MB | 継続 | 上限・ローテーション無し |
| 18 | ⚪ `data/analytics.db`(0B) / `data/video_status.db`(0B) | 継続 | Mac 側でないと削除不可 |
| 19 | ⚪ 未コミット: fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 / oripa 1 / client-ops 2 | 継続 | 変化なし |
| 20 | ⚪ 二重リモート（origin 4遅れ / neworigin 同期） | 継続 | yf・aiseki とも |

### 🆕 NEW

| # | 内容 |
|---|---|
| **N1** | 🔴 **`daily-merge-all-projects` がまた空振り。** 22:05 に実行済み（`lastRunAt` 09-20 13:05 UTC）なのに **`last_merge_log.md` は 09-19 22:08 のまま**。前回「解決」と報告した件の**再発・3度目**。本日のコミット2件は 10:35 と 18:32 でマージ run の時刻ではない |
| **N2** | 🟠 **OAuth 失効の瞬間に scp-lab の1枠を落とした。** ジョブ `c885d533` はレンダリング完走直後に refresh が落ち `⚠️ 自動公開スキップ`。**生成コストは払って公開だけ失った。`publish_blocked` は 0 件なので、そこだけ見ても気付けない** |
| **N3** | 🔴 **pokemon-lab は再認可されたのに `autopilot.enabled=false` のまま。** キューは21件中12件通過（4.0日分）。指揮者の評価では**成熟動画の40%が1,200再生超＝6ch中いちばん天井が高い**。**ONにするだけで明日から3本/日。今いちばん費用対効果の高い1操作** |
| **N4** | 🆕 **`scripts/token_expiry_alert.py` が新設**（`ad46ca1` 09-19 23:36 → `e89f8aa` 09-20 10:35 で修正）。**通知は送らない設計（終了コード2を返すだけ）なので、呼び出し側の routine に繋がないと鳴らない** |
| **N5** | 🟠 **aiseki が本日ゼロコミット**（09-18・09-19 は稼働）。止めたのか一時的かは判断材料なし |
| **N6** | 🟠 **登録者が3chで減少**（6ch計 332→326）。**n=1日なので構造的説明を与えない。2日続いたら初めて見る** |
| **N7** | ⚠️ **指揮者の本日の成果物3点が未追跡**（`MEMORY_UPDATE_20260920.md` / `reports/youtube_analysis_20260920.xlsx` / `scripts/orch_apply_20260920.py`）。N1 と同根。**A/Bの根拠文書がgitに載らないまま09-27の判定を迎える** |

### 📌 キュー在庫（実消費される `autopilot.theme_queue`）

| ch | 総数 | 通過 | 枠/日 | 残り日数 | 主な違反 |
|---|---:|---:|---:|---:|---|
| 2ch-matome | 23 | 15 | 1 | 15.0 | `forbid_digits` 7 / `forbid_patterns` 2 |
| company-facts | 10 | 9 | 4 | 2.2 | `require_any_of` 1 |
| yokai-watch | 4 | 4 | 3 | 1.3 | — |
| daily-science | 2 | 2 | 3 | **0.7** | — |
| **scp-lab** | **0** | **0** | 3 | **0.0** | — |
| **socio-rx** | 5 | **0** | 2 | **0.0** | `require_any_of` 5 / `min_effective_chars` 3 |
| **合計** | **44** | **30** | 16 | | |

推移: 09-17 **87/32** → 09-18 **61/37** → 09-19 **51/29** → **09-20 44/30**。
18:32 の `85f8288` で company-facts のみ補充（2→9）。**scp-lab と socio-rx は救われていない。**
（参考: pokemon-lab 21/12＝4.0日分あるが autopilot OFF で消費されない）

### 🧪 進行中のA/B（⛔ 09-27 まで触らない）

| 群 | ch | `defaults.short_endcard.enabled` |
|---|---|---|
| OFF | daily-science / yokai-watch / 2ch-matome | **false** |
| 対照ON | scp-lab / company-facts | true |
| （群外） | socio-rx / pokemon-lab | true |

主指標: 完走率(95-100%) が OFF群で 11.5% → **16%以上**へ回復するか。副指標: ループ率(0%) 110%→114%、再生中央値d3、登録/千再生。**対照群を動かすと測定が丸ごと無駄になる。**

---

## 3. ユーザー手動待ちタスク一覧

**⭐ 今いちばん効くもの**

1. ⭐ **pokemon-lab の autopilot を ON**（N3）— OAuth 済み・キュー4日分・6ch中いちばん天井が高い
2. 🔴 **scp-lab のテーマキュー補充**（在庫0・枠3/日）
3. 🔴 **socio-rx のキュー修正**（5件中0件通過・3日連続で同じ5件）
4. **残6ch の OAuth 再認可** — **同意画面はもう本番なので今やれば全部無期限**。akashic-librarian は実力3位
5. 🔴 **`ANTHROPIC_API_KEY` を貼り直す**（`backend/.env` 18行目・9日連続401）

**判断が要るもの**

6. 🆕 **`daily-merge-all-projects` の3度目の空振り（N1）** — タスク定義の見直し or スケジュールずらし
7. 🆕 **`token_expiry_alert.py` を実際に鳴らす配線**（N4）
8. 2ch-matome の `forbid_digits` を緩めるか（7件該当・ただし「数字あり」は 09-17 実測 0.72倍で負）
9. 23時台の cron をずらす（8日連続で並走）
10. `auto_optimize_schedule=true` の残2ch（company-facts / socio-rx）
11. 切り抜き4chを畳むか（全停止11〜14日・キュー0・再認可もなし）
12. fake-paper を止めるか作り直すか
13. 二重リモートを片方に寄せるか（origin が4遅れ）
14. oripa `feat/stripe-checkout` を main へマージするか（40日）
15. サムネ403（電話確認）をいつやるか — 急ぎではない扱いのまま

**⛔ 09-27 まで触ってはいけない**

16. **`defaults.short_endcard.enabled`（5ch）** — 対照群を動かすとA/Bが無駄になる
17. 評価待ち: **09-24** 投稿時刻 / **09-25** 文字数帯3ch / **09-26** 冒頭重複修正 / **09-27 ★本命** エンドカードA/B / **10-02** 2ch-matome エンハンサー停止

**環境の掃除（Mac 側でないと消せない）**

18. `rm -rf .git/stale_locks .git/_stale && find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**623/88/34**）
19. ホストで `pytest backend/tests`（**10日間**未測定）
20. `data/analytics.db`(0B) / `data/video_status.db`(0B) の削除
21. `data/job_queue.json` 20MB の上限・ローテーション要否
22. `git push origin main`（4コミット）or `git remote remove neworigin`（#13 次第）

**aiseki**

23. Twilio 本番アップグレード / `dm_targets` CSV 取り込み / 営業本番の開始判断（先頭 `1000bero_net`・**1日30件・間隔30〜120秒は変えない**）
24. ロゴ生成 → Instagram プロフ写真差し替え / SNS 初投稿（**投稿0件**）
25. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
26. 🆕 **`supabase/migration_*.sql` 29本中、`apply_migrations.command` が当てているのは3本だけ。** 残り26本の適用状況を DB 側で確認するか、スクリプトを実態に合わせる
27. 実機動作確認 / 運営体制（通報対応者・営業許可・本店所在地）

**ai-english-coach**

28. **GitHub リモートの作成と push**（ローカルのみ＝バックアップ無し・**12日**）
29. **LINE Pay 加盟店申込**（審査があるので最優先）/ LINE公式 / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

30. ChatGPT スレッドURLを13ch分登録（`threads.json` が `{}` のまま**16日**）/ 画像ブリッジ pending **724**（+40/日）
31. oripa サイト本文が空（**8日連続**）/ 古物商許可（審査約40日）
32. fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 の整理（任意）
33. rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach は**リモート未設定**（バックアップ無し）

---

## 4. 次回（09-21）に確認すること

- ⭐ **pokemon-lab の autopilot が ON になったか**（なっていれば公開 14→17本/日）
- **scp-lab / socio-rx のキューが補充されたか**（在庫0＋通過0）
- **OAuth 7ch が無期限のままか** — **ここが崩れたら本番公開が効いていない**
- **残6ch が再認可されたか**
- 🆕 **`last_merge_log.md` が更新されたか**（N1・3度目の空振り）
- 🆕 **指揮者の成果物3点がコミットされたか**（N7）
- **`ANTHROPIC_API_KEY` の401が消えたか**（9日連続）
- **公開本数**（今日14本）／**`自動公開スキップ`**（今日1件）／**サムネ2MB超の再発**
- **登録者の減少（N6）が続くか** — **n=1日では判断しない。2日続いたら初めて見る**
- **aiseki が再開したか**（N5）
- **09-24** 投稿時刻 / **09-25** 文字数帯 / **09-26** 冒頭重複 / **09-27 ★** エンドカードA/B

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`publish_blocked` が0でも枠は落ちる。** 本日の scp-lab は `⚠️ 自動公開スキップ (<job_id>): チャンネル '<ch>' — トークン失効のため要再認可` という別経路で1枠失った。**`Autopilot fired` の回数と公開本数を突き合わせ、ズレたら `自動公開スキップ` も grep する。**
- 🆕 **OAuth の再認可は `logs/backend.log` の `♾️ [oauth] <ch>: リフレッシュトークンは無期限で発行されました` で確認できる。** `latest.md` の表より早く確実。
- 🆕 **指揮者の設定変更は独立コミットとは限らない。** 本日のエンドカードA/Bは `85f8288`「company-facts の題材8件をキューへ再投入」に同梱されていた。**コミットメッセージで設定変更の有無を判断せず `git show --stat` でファイルを見る。**
- 🆕 **`data/channels/*.json.bak_*` は `.gitignore`（`data/**/*.bak_*`）で除外される。** バックアップの有無は `git status` では見えない。`ls` すること。
- 🆕 **「走った」と「成果物を出した」は別。** `list_scheduled_tasks` の `lastRunAt` は本日 22:05 を示すが `last_merge_log.md` は更新されていない。**出力ファイルの mtime も必ず見る。**
- 🔴 **`.git/index` を cp して `GIT_INDEX_FILE` に使ってはいけない。** 必ず `export GIT_INDEX_FILE=/tmp/<ユニーク名> && git read-tree HEAD` で作り直す。使うと dirty が二重に見える。
- 🔴 **`Autopilot fired` を `grep -c` で数えない。** 1行に2〜4回まとめて出る。`grep -o ... | sort | uniq -c` を使う。
- **サムネ失敗は403だけではない**（`Media larger than: 2097152` の前例）。**成功本数＝公開本数 −（全失敗の distinct video_id）**。1本につき2行出るので行数で数えない。
- **キュー在庫の実消費は `data/channels/<ch>.json` の `autopilot.theme_queue`。** `data/channels/<ch>/theme_queue.json` は seeds で別物。**どちらか必ず明記する。**
- **枠数は `autopilot.schedule.times` の要素数。** `slots` / `videos_per_day` というキーは無い。
- 🔴 **`title_constraints.check()` の第2引数は「チャンネル JSON 全体」**（`hard_constraints` を渡すと全件 `ok:True`）。`cd backend` してから `from pipeline import title_constraints`。**必ず短い文字列で `ok:False` を確認してから集計する。**
- **カウンタは mtime の分布まで見る。** `failed` 235件は「詰まっている」ではなく「09-08 以降 新規が来ていない」。
- **23時台は他タスクが並走する。** git 系の数値は取得時刻を併記する。
- **公開実績は `data/video_publish.db` の `video_status`**（`data/video_status.db` は0バイト）。ch列は `channel_id`。`published_at` は UTC → `date(datetime(published_at,'+9 hours'))`。
- **analytics は `data/analytics/analytics.db`**（`data/analytics.db` は0バイト）。`sqlite3.connect('file:...?mode=ro', uri=True)` で開く。
- **登録者数と OAuth の生死は `data/reports/latest.md`**（`oauth_tokens.expires_at` で判定しない）。
- **aiseki のマイグレーションは `supabase/migrations/` ではなく `supabase/migration_*.sql` のフラット配置。** 「ディレクトリが無い＝判定不能」と書かない。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は原理的に失敗する。マージ可否は `/tmp` の `git clone -s` で判定。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`video_metrics.views` は直近30日窓。** 同一動画でも日をまたいで減る。「再生が減った」と読まない。
- **比較は必ず公開3日以上の動画で。** d0〜d2 は構造的にほぼ0（指揮者 09-20 実測）。
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。`min_effective_chars` は `UNREPAIRABLE_RULES`。
