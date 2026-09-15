# Daily Handoff Log

**実行日時**: 2026-09-15 23:20 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-15.md`
**前回**: 2026-09-14 23:25 / **参照した文脈**: `last_handoff_log.md`(09-14)、`last_merge_log.md`(09-15 00:12)、`.auto-memory/` の 2026-09-10〜09-15・INDEX.md・projects/

> ℹ️ bash 完走。git・sqlite・ログ・キューのゲート判定・サイト疎通を全て実測。
> ℹ️ 全数値を別エージェントで独立再計測して突合。**2件の誤りを発見して訂正した**（`subscribers_gained` の「全ch0」/ `theme_queue` の「全13ch 0件」）。
> ⚠️ **本 run の6分前（23:16）に別タスク `nightly-full-progress` が youtube-factory の夜間分析を commit していた。** 数値は独立に出して完全一致。本レポートは差分と全プロジェクト横断に絞った。
> ℹ️ サイト疎通は `web_fetch`。4サイトすべて 200。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-15 も13本公開**（3日で38本）。**`publish_blocked` が初めて実際に公開を止めた**（scp-lab 13:00・設計どおり）。ただし **OAuth 失効が `2026-09-20 12:05:39` と確定**・**サムネ403が3chで4日連続**・**APIキー401** |
| aiseki | 🟢 **正常・進捗継続** | コミット0だが **Instagram プロフィール整備を完了**（HANDOFF §38・未コミット1件）。未適用マイグレーション0。aisekimatch.com 200 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**7日**。未コミット0。**Git リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**15日**変化なし。未追跡25件。**origin/main と同期済みを今回初めて実測**。サイト200 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**35日**。`feat/stripe-checkout` は main比 **9先行・0遅れ**、origin にも push 済み。**サイト200だが本文が空**（3日連続） |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | 4ch autopilot OFF・OAuth全失効。`clip-animal` だけ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし（85日）。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし（73日）。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | 09-15 に3コミット（`6c65baa` 02:06・intake-fb を launchd 登録） |

---

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **N3「ゲートは検知しても止めない穴」→ 解決。** `8403e2f`(09-15 00:03) の `publish_blocked` で **scp-lab 13:00 枠が実際に停止**。**09-15 公開13本は素タイトルの `check()` が全件 `ok:true`**（09-14 は18本中3本が `ok:false` のまま公開）。
- **未 push の滞留 → 解決していた。** `refs/remotes/origin/main` の reflog に `update by push`。**`8403e2f`(09-15 00:03) まで実際に push 済み。**
- **`title_gate_ok`（前回 N2）→ 監視から外してよい。** 672ジョブの生 grep でも0ヒット。実装されていない。
- **`.git/objects/tmp_obj_*` 1,215 → 51。** 09-15 00:12 のマージタスクが畳み込んだ。
- **09-13公開7本の初回実績が入った**（前回の「次回確認事項」の筆頭）→ 結果は §NEW N3 のとおり**判定不能**。

### ⚠️ 過去レポートの訂正

- 🔧 **「`subscribers_gained` が全ch 0（9日間）」は誤り。** 09-04〜09-09 は非ゼロ（09-08 は12人）。**0 は 09-10 以降の3日分だけ**で、同期間は `views` も 519/230/1,442 と極小＝**未集計であって実績の崩壊ではない**。
- 🔧 **「13ch 全ての `theme_queue` が0件」は誤り。** 09-14 バックアップ（`*.bak_pdca_20260914n`・13ch）合計 **283件**、現在 **261件**。**0から補充ではなく 283→261 と22件消費**が正しい。
- 🔧 **「neworigin が68コミット先行」は向きが逆。** `neworigin/main` は `ed5cbe5`(08-31) で **main が79先行**。**実運用は `origin`(zaki21016) 一本で、「どちらが正か未決」という課題は存在しない。**
- 🔧 **`check()` を公開済みタイトルに当ててはいけない。** ハッシュタグが付くので `max_chars` で全滅（素で0本 / 込みで13本全滅）。
- 🔧 **09-14 の `ok:false` 公開は「1本」ではなく3本**（company-facts / scp-lab / socio-rx）。

### ❌ 未解決

| # | 内容 | 継続 | 09-15 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 4.57日。失効予定 `2026-09-20 12:05:39` が確定値でログに出た** |
| 2 | サムネ403 | **4日** | 公開13本中 成功は **daily-science の3本のみ**。company-facts 4/4・scp-lab 2/2・yokai-watch 3/3 が403（ログの403行753件・非403は0件） |
| 3 | `ANTHROPIC_API_KEY` 401 | 継続 | 108字の値が入った上での401＝**キー文字列そのものが無効。貼り直し要** |
| 4 | OAuth 未再認可の残7ch | 継続 | akashic-librarian / fake-paper / pokemon-lab / clip-lab / clip-fukada / clip-kaneko / clip-animal。**登録者数も測れない** |
| 5 | `channel_metrics` 09-12 止まり | +1日前進 | 09-11→09-12。09-10以降の gained は0（未集計） |
| 6 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 |
| 7 | 画像ブリッジ pending 増加 | 継続 | **478 → 517**（+39/日）。failed 235 据え置き |
| 8 | `viral_translation_pending` 17件 | 継続 | 変化なし。APIキー401のため処理されない |
| 9 | `orch-20260911-followup` 未マージ | **5日** | **3先行・38遅れ**（前回 3/27）。コンフリクト2件 |
| 10 | `logs/backend.log` ローテーション未実装 | 継続 | **86,636,112 バイト**（+1,030,204/日） |
| 11 | `.git/stale_locks/` の残骸 | 継続 | 78 → **85**（`tmp_obj_*` は 1,215→51） |
| 12 | 回帰テストが測れない | **5日** | サンドボックスに pytest 無し |
| 13 | oripa `feat/stripe-checkout` 未マージ | **35日** | 9先行・0遅れ |
| 14 | ai-english-coach: Git リモート未設定 | 継続 | `git remote -v` 空 |
| 15 | fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 | 継続 | 変化なし |
| 16 | aiseki: Twilio トライアル / SNS未投稿 | 継続 | `type=Trial`・Balance -0.406 USD。Instagram 投稿0件 |
| 17 | oripa サイト本文が空 | **3日** | 200 は返るが body が空 |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🟢 **`publish_blocked` が初めて実際に公開を止めた** | scp-lab 13:00 枠が `max_digit_groups`(2718/31) 未解消で停止。**事故ではなく設計どおり。09-14 の穴は塞がった** |
| **N2** | ⚠️ **代償として「本数が減る」経路が生まれた** | 09-15 は **14枠中13本＝到達率 92.9%**。**今後「本数が減った」を見たら、OAuth より先に `⛔ この枠は公開を止めました` を疑う** |
| **N3** | 🔴 **5ch集中運用の初の判定点は「判定不能」だった** | 09-13公開7本に2日ぶりに数字が入ったが、**views が付いたのは7本中2本だけ**（scp-lab 1,030 / socio-rx 260）、**登録は0**。09-14の18本・09-15の13本は依然 views=0。**本判定は 09-21 へ持ち越し** |
| **N4** | 🔴 **SCP系は `max_digit_groups=1` と構造的に衝突する** | 題材名に必ず数字（SCP-2718）が入るため本文に数字を1つ足すと即違反→枠を捨てる。**`SCP-\d+` を除外するか `=2` にするか、09-16 の指揮者で判断** |
| **N5** | 🟢 **aiseki が Instagram プロフィール整備を完了**（未コミット） | 自己紹介93字・プロフ写真（暫定）。**手段は `worker/.ig-profile` から `accounts/edit/` を直接操作**（Chrome拡張は接続不安定で使えず）。**ウェブサイト欄は Web から編集不可** |
| **N6** | ⚠️ **未 push が11コミットに再蓄積** | `origin/main` は `8403e2f`(09-15 00:03)。以後の自動タスク11コミットが未送信。**毎日積むのでホスト側の日次習慣にするしかない** |
| **N7** | ℹ️ **fanup / oripa は「測定不能」ではなく push 済みだった** | fanup `0/0`・oripa `feat/stripe-checkout 0/0`。upstream 未設定なだけ。**バックアップ無しは ai-english-coach / rhythm-pop / claude-codex-bridge / ai-orchestrator の4つだけ** |
| **N8** | ⚠️ **総再生の前日比（180,226→174,391）を「減った」と読まない** | ch あたり**直近50本の固定窓**。新規13本が入ると古い高再生本が落ちる。**母集団の入れ替わり** |
| **N9** | ⚠️ **`company-facts` の top-level `days_of_week` がまた動いた** | 09-13 `[3,4,5]` → 09-14 `[1,4,5]` → 09-15 **`[3,4,5]`**。4枠が各自 `[0..6]` を持つので無害だが、**UI/API から編集した瞬間に週3日へ落ちる地雷は残存** |
| **N10** | ℹ️ **キュー適合率 85.1%（211/248）** | 前回 84.0% と同一定義。違反は `max_digit_groups`13 / `forbid_digits`10 / `banned_words`9 / `forbid_patterns`7。下位は socio-rx 58.3% / 2ch-matome 61.5% / scp-lab 70.6% |
| **N11** | ℹ️ **登録者数** | scp-lab **164**(+2) / daily-science **74**(+2) / company-facts **39**(+3) / yokai-watch **28**(+1) / 2ch-matome **9**(±0) / socio-rx 0。**残7chは測定不能** |
| **N12** | ℹ️ **09-15 当日行スナップショット 登録/千 0.608**（253本・174,391再生・106登録） | scp-lab 0.854(-0.009) / yokai-watch 0.791(+0.004) / **daily-science 0.725(+0.062)** / company-facts 0.613(-0.006) / 2ch-matome 0.163(+0.011)。09-14 の 0.594 から +0.014 |

---

## 3. ユーザー手動待ちタスク一覧

**🚨 今すぐ（09-16〜09-19 に必ず）— この順番で**

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / `console.cloud.google.com/auth/audience`）
   → **失効 `2026-09-20 12:05:39` が確定。残り4.57日。同意画面を先に公開してから再認可すること。**
2. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch` のみ（`youtube.com/verify`）
   → daily-science / socio-rx は通過済み。**4日連続で最優先のまま。**
3. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに貼り直す**（`backend/.env` 18行目）— 値は入っているがキー自体が無効。
4. **`cd ~/Developer/youtube-factory && git push origin main`**（11コミット未送信）

**判断が要るもの**

5. **N4: scp-lab の `max_digit_groups`**（`SCP-\d+` を除外 / `=2` へ緩和 / 現状維持＝毎日1枠落ち続ける）— **09-16 の指揮者の最優先**
6. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。akashic-librarian は実力3位）
7. 切り抜き4chを畳むか（全停止・OAuth全失効・測定不能）
8. fake-paper を止めるか作り直すか（OFF・登録/千 0.000）
9. `orch-20260911-followup` のマージ方針（**5日放置・38遅れ**。main側採用が妥当）
10. oripa `feat/stripe-checkout` を main へマージするか（**9先行・0遅れ**・35日放置）
11. **company-facts の枠 4→3 差し戻し**（0.715→0.649→0.619→0.613 と4日連続低下）— 公開分が未計測なので **09-21 に決める**

**環境の掃除（Mac 側でないと消せない）**

12. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
13. `rm -rf .git/stale_locks .git/_stale* .git/_trash_consolidated`（**85件**）／`find .git/objects -name 'tmp_obj_*' -delete`（51件）／`git gc --prune=now`
14. `logs/backend.log` **86,636,112 バイト**（+1.03MB/日）のローテーション
15. ホストで `pytest backend/tests` を1回流す（5日間測れていない）
16. **`neworigin` リモートを削除してよい**（`git remote remove neworigin`）— 08-31 で止まり79遅れ。push 先の取り違えを招く

**aiseki（公開前）**

17. **Twilio 本番アップグレード** ／ `dm_targets` の CSV 取り込み（**実在確認＋非公開判定を入れる**）／ 営業本番の開始判断（先頭 `1000bero_net`）
18. 🆕 **ChatGPT でのロゴ生成 → Instagram プロフ写真の差し替え**、**SNS 初投稿**（素材 `sns_assets/`・文面 `sns_posts.md`・投稿0件）
19. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
20. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

21. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝**バックアップ無し**）
22. LINE Pay 加盟店申込（**審査があるので最優先**）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

23. **ChatGPT スレッドURLを13ch分登録**（`threads.json` が `{}` のまま）／画像ブリッジ pending **517**（+39/日）・failed 235 の処理方針
24. oripa サイトの本文が空（3日連続）— ビルドかルーティングの確認
25. fanup 未追跡25 / rhythm-pop 未コミット19 / ai-orchestrator 未追跡1 の整理（任意）
26. **rhythm-pop / claude-codex-bridge / ai-orchestrator もリモート未設定**（バックアップ無し）。GitHub へ退避

---

## 4. 次回（09-16）の実行時に確認すること

- **🚨 OAuth の残日数**（今日 4.57日 → 明日 3.57日のはず。**失効は 09-20 12:05**）
- **サムネ403が company-facts / scp-lab / yokai-watch で止まったか**
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **N4 の判断が入ったか**（scp-lab の `max_digit_groups`）。**入らないと毎日1枠ずつ落ち続ける**
- **公開本数と到達率**（09-15 は 13/14＝92.9%。**`⛔ この枠は公開を止めました` を grep して分子を確かめる**）
- **09-14 公開18本に views が入るか**（ラグ2日なので 09-16 の fetch が最短）
- **`channel_metrics` が 09-12 から進んだか**（09-10以降の未集計が埋まるか）
- **キュー適合率**（今回 **85.1%＝211/248**。同じ2規則を除いて比較）
- **画像ブリッジ pending**（517 → +39/日の傾きが続くか）
- **09-19**: scp-lab 週7日化・company-facts 4枠化の検証 / **09-20**: OAuth 失効日 / **09-21**: 09-14 枠・型変更と 09-15 キュー補充の本判定

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 **`title_constraints.check()` は「素のタイトル」に当てる。** 公開済みタイトルにはハッシュタグが付き `max_chars` で全滅する（09-15 は素で0本 / 込みで13本全滅）。`" #"` 以降を落とす。
- 🆕 **analytics DB は `data/analytics/analytics.db`**（`data/analytics.db` ではない）。**日付カラムは `date`**（`snapshot_date` ではない）。
- 🆕 **`channel_metrics` の `subscribers_gained` が0でも「実績ゼロ」ではない。** 同日の `views` も極小なら**未集計**。09-10以降がこれ。
- 🆕 **ch あたり直近50本の固定窓なので、総再生の前日比は意味が無い。** 新規公開が入ると古い高再生本が落ちる。
- 🆕 **`backend.log` は行頭にタイムスタンプが無い。** `grep '^2026-09-15'` は0行。`tail -c` で末尾を取り既知の video_id で前後関係を読む。
- 🆕 **本数が減ったらまず `⛔ この枠は公開を止めました` を grep する。** `publish_blocked` 導入後は OAuth より先にこちら。
- 🆕 **`autopilot.schedule` の枠は `schedule["times"]`。** `schedule["slots"]` は存在しないので空に見える。
- 🆕 **`theme_queue` の前日比はバックアップ（`data/channels/*.json.bak_pdca_YYYYMMDDn`）と比べる。** `orch_config_changes_*.json` の `queue_before` は始値ではない。
- 🆕 **`youtube-factory` / `aiseki` には remote が2つある**（`origin`=zaki21016 が現役 / `neworigin`=rikoandmakoto-ops は 08-31 で放棄）。**push 先は `origin`。**
- 🆕 **remote-tracking ref は fetch できない（FETCH_HEAD は 09-08）。** 「0遅れ」は未検証。判定できるのは「先行 N」だけ。
- **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。公開の真偽は `video_id` の有無。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。
- **`data/reports/latest.md` が登録者数の唯一のソース。** OAuth が生きている ch しか値が入らない。
- **views のラグは約2日**（09-13公開が 09-15 に初計測されて実測確定）。
- **`data/job_queue.json` は `raw.get("jobs", raw)` で吸収する。**
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。** `check()`/`is_enforced()` にはチャンネルJSON全体を渡す。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。lock は `mv .git/index.lock .git/stale_locks/` で退避。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **未コミット件数は計測中に増える**（backend 稼働中）。**時刻とセットで記録する**（今回 58件 / 23:12 JST）。
- ⚠️ **夜間は `nightly-full-progress` と本タスクが近接して走る。** 先に走った run が `.auto-memory/2026-09-15.md` に夜間追記を入れていないか、`git log --since` で必ず確認してから書くこと。

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-15.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform / ai-orchestrator）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
