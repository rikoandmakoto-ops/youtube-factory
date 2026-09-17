# 全プロジェクト 引き継ぎレポート — 2026-09-16

**実行日時**: 2026-09-16 23:10 JST / **タスク**: daily-project-handoff（スケジュール実行・承認者不在）
**前回**: 2026-09-15 23:20
**参照した文脈**: `last_handoff_log.md`(09-15 23:20) / `last_merge_log.md`(09-16 22:09) / `.auto-memory/` の 2026-09-10〜09-16・INDEX.md・projects/

> ℹ️ 全数値を bash で実測。主要10項目を別エージェントで独立再計測して突合 → **不一致0件**。
> ℹ️ 再計測で1点だけ精度が上がった: socio-rx のサムネは **403ではなく「パス未指定」**（後述 NEW-3）。
> ⚠️ **本 run の1時間前（22:09）に `daily-merge-all-projects` が 8コミットを作っていた。** 本レポートはその後の状態を見ている。
> ⚠️ **10:10 に別タスクの指揮者 run、10:26 に本体の指揮者 run** が走っている（3日連続の並走）。
> ℹ️ サイト疎通は `web_fetch`。4サイトすべて到達（oripa のみ本文が空）。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-16 は14本公開で稼働5chの全枠に到達**（mdg=2 が効いた）。しかし **OAuth 失効まで残り3.57日**・**サムネ403が5日連続**・**APIキー401**・🆕 **2ch-matome を再開したのに3枠とも発火せず0本** |
| aiseki | 🟢 **正常・進捗継続** | 🆕 **09-16 にコミット1件**（HANDOFF §38 = Instagram プロフィール整備）。**origin/main と完全同期・dirty 0**。aisekimatch.com 到達 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**8日**。dirty 0。**Git リモート未設定＝バックアップ無し**（継続） |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**16日**変化なし。未追跡25件。サイト正常（サポーター1,248・進行中3件が表示） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**36日**。`feat/stripe-checkout` は main比 **9先行・0遅れ**。**サイト本文が空（4日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | 4ch とも autopilot OFF・OAuth 全失効。**最終公開 clip-animal 09-06 / 他3ch 09-09**。`clip-animal` だけ `hard_constraints` 未設定（継続） |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし（86日）。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし（74日）。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | 09-15 の `6c65baa` が最新。origin/main と同期・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし。未追跡1・リモート未設定 |

---

## 2. youtube-factory 詳細

### 2-1. 公開実績（`video_status` に `video_id` が入った行＝実公開）

| JST日付 | 本数 | 内訳 |
|---|---:|---|
| 09-13 | 7 | scp 2 / company 2 / yokai 1 / socio 1 / daily 1 |
| 09-14 | 18 | company 5 / yokai 4 / scp 4 / daily 4 / socio 1 |
| 09-15 | 13 | company 4 / yokai 3 / daily 3 / scp 2 / socio 1 |
| **09-16** | **14** | **company 4 / yokai 3 / scp 3 / daily 3 / socio 1** |

**枠到達率**: 稼働5ch（2ch-matome を除く）の本日の有効枠は 13枠 → **13/13＝100%**。
`⛔ …この枠は公開を止めました` は**通算1件のまま（09-15 の scp-lab のみ）で、本日は0件**。
→ **09-16 の `max_digit_groups` 1→2（commit `fb2eee6`）が効いて、scp-lab が 3/3 で通った。**

### 2-2. autopilot 状態（13ch）

| channel | AP | 枠/日 | queue | 在庫 | gate |
|---|:--:|---:|---:|---:|---|
| company-facts | ✅ | 4 | 19 | 4.8日 | あり |
| daily-science | ✅ | 3 | 14 | 4.7日 | あり |
| scp-lab | ✅ | 3 | 14 | 4.7日 | あり |
| yokai-watch | ✅ | 3 | 15 | 5.0日 | あり |
| socio-rx | ✅ | 2 | 11 | 5.5日 | あり |
| **2ch-matome** | 🆕✅ | 3 | 26 | 8.7日 | あり |
| akashic-librarian | ⛔ | 3 | 11 | — | あり |
| pokemon-lab | ⛔ | 3 | 21 | — | あり |
| fake-paper | ⛔ | 3 | 3 | — | あり |
| clip-lab | ⛔ | 3 | 32 | — | あり |
| clip-kaneko | ⛔ | 3 | 36 | — | あり |
| clip-fukada | ⛔ | 2 | 30 | — | あり |
| clip-animal | ⛔ | 2 | 13 | — | **なし** |

**13ch 合計キュー 245件**（前回 261 → **-16／1日**）。うち **146件は停止7chに滞留**して消化されない。
**稼働5chの在庫は 4.7〜5.5日**（09-16 朝の指揮者メモは 5.7〜6.0日）→ **このペースだと 09-21 前後に枯れる。**

### 2-3. 登録者数・登録/千（`data/reports/latest.md`・直近30日窓）

| ch | 登録者 | 前日差 | 登録/千（30日窓） |
|---|---:|---:|---:|
| scp-lab | **166** | +2 | 0.8245 |
| daily-science | 74 | ±0 | 0.6679 |
| company-facts | **42** | +3 | 0.6013 |
| yokai-watch | 29 | +1 | 0.7606 |
| 2ch-matome | 9 | ±0 | 0.1822 |
| socio-rx | 0 | ±0 | 0.0 |
| 残7ch | — | — | 測定不能（OAuth失効） |

> ⚠️ **窓に注意。** 前回レポートの 0.854 等は指揮者の「直近50本ローリング窓」。上表は `latest.md` の**直近30日窓**で、**別の数字。前日比で並べてはいけない。**

### 2-4. エラー

| 項目 | 09-15 | **09-16** | 判定 |
|---|---|---|---|
| OAuth 残り寿命（稼働6ch） | 4.57日 | **3.56〜3.57日** | 🔴 **失効 `2026-09-20 12:05`。残り3.5日** |
| OAuth 失効7ch | 7ch | 7ch | 🔴 変化なし |
| サムネ403 | 4日連続 | **5日連続**。試行13本中 **10本が403**、成功は daily-science の3本のみ | 🔴 継続 |
| `ANTHROPIC_API_KEY` 401 | 継続 | **継続**（`latest.md` に「ANTHROPIC_API_KEY が無効（認証エラー）」・ログに `authentication_error` 307件） | 🔴 継続 |
| `channel_metrics` 最終日 | 09-12 | **09-13**（+1日） | 🟡 **09-13 は6ch全て views=0 / gained=0＝未集計** |
| `video_metrics` 最終日 | 09-15 | **09-16** | 🟢 当日分が入った |
| `logs/backend.log` | 86,636,112 B | **87,664,685 B** | 🔴 +1,028,573 B/日・ローテーション未実装 |

### 2-5. git

```
main                   311619d  [origin/main: ahead 8 / behind 0]   dirty=4（すべて未ステージ変更・未追跡0）
orch-20260911-followup 8badac5  main比 3先行 / 56遅れ               ← 前回 3先行/38遅れ・放置6日目
```

- 未push **8コミット**（09-16 のマージタスクが作った分）。前回の11コミットはホスト側で push 済みを確認。
- dirty 4件: `data/analytics/retention_insights.json` / `data/analytics/success_patterns.json` / `data/reports/latest.md` / `data/reports/pdca_history.xlsx`（いずれも backend が定期生成する成果物）
- **`neworigin`（rikoandmakoto-ops）は 08-31 で放棄済み。実運用は `origin`（zaki21016）一本。**
- ゴミ: `tmp_obj_*` **321件**（前回51 → 🆕 **再増加**）／ `.git/stale_locks/` 83件 ／ `.git/index.lock` 1件 ／ `_stale` 22件

---

## 3. 前回からの差分

### ✅ 解決を確認（次回「要対応」として報告しないこと）

- **N4「scp-lab の `max_digit_groups=1` が枠を捨てる」→ 解決。** 09-16 に scp-lab / pokemon-lab を **mdg=2** へ（commit `fb2eee6`）。根拠は実測（未使用キュー違反 5/17→0、公開済み 112/209 が不合格だった、数字個数と登録/千は ch 内で無相関）。**本日 scp-lab は 3/3 で公開到達、`publish_blocked` 0件。**
- **前回の「未push 11コミット」→ 解決。** ホスト側で push 済み。現在の ahead 8 は**本日新たに積まれた分**。
- **「本数が減る」懸念（前回 N2）→ 本日は発生せず。** 到達率 100%（稼働5ch）。
- **`video_metrics` の停滞 → 解決。** 09-15 止まり → **09-16 の当日分が入った。**
- **aiseki の Instagram プロフィール整備（前回 N5・未コミット）→ コミット済み**（`8a64756`）。origin/main と同期。

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🔴 **2ch-matome を autopilot ON に戻したのに、3枠すべて発火せず 0本だった** | 10:10 の並走 run が `autopilot.enabled` を false→true にしたが、**書き込みは JSON 直書き（`patch_channel_file`）で `_refresh_channel_job()` を通っていない**。既知の罠（INDEX.md「反映されるもの・されないもの」）を**そのまま踏んでいる**。12:15 / 17:30 の2枠が過ぎても公開0。最終公開は依然 **09-10**。→ **backend 再起動か `PUT /api/channels/2ch-matome/autopilot` が要る。** 放置すると「発火しない→キューを消費しない→cron が永久に更新されない」の自己強化ループに入る |
| **N2** | 🟢 **mdg=2 の効果が初日で出た** | scp-lab 3/3・`publish_blocked` 0件・稼働5chの枠到達率 100%。09-15 は 13/14 |
| **N3** | ⚠️ **socio-rx のサムネは403ではなく「パス未指定」** | `ℹ️ サムネイルパス未指定 (video_id=9EIbN-1gito)`。**403の3chとは別の問題で、サムネ自体が生成・指定されていない。** 電話番号確認が通っても socio-rx は直らない |
| **N4** | ⚠️ **`.git/objects/tmp_obj_*` が 51 → 321 に再増加** | 09-16 22:09 のマージタスクが8コミットを作る際に、サンドボックスの delete 不可回避策で量産した。**毎回のマージ run で数百件ずつ増える構造** |
| **N5** | 🟡 **キュー在庫が稼働5chで 4.7〜5.5日まで低下** | 朝の指揮者メモの 5.7〜6.0日から半日で目減り。**補充が消費に追いついていない。09-21 前後に枯渇見込み** |
| **N6** | ⚠️ **`channel_metrics` は 09-13 まで進んだが、その 09-13 は6ch全て views=0 / gained=0** | **日付だけ前進して中身が空。「未集計が 09-10 以降4日連続」が実態**で、前進とは言えない |
| **N7** | ⚠️ **停止7chに 146件のキューが死蔵されている** | 13ch合計245件のうち 60%。**clip-kaneko 36 / clip-lab 32 / clip-fukada 30 / pokemon-lab 21** が上位。畳むなら消す、続けるなら再認可が要る |
| **N8** | ℹ️ **`orch-20260911-followup` の遅れが 38 → 56 に拡大** | 6日放置。先行3コミットは変わらず。**main 側が5日で56進んだので、いまマージする価値はほぼ無い。cherry-pick か破棄が妥当** |
| **N9** | ℹ️ **画像ブリッジ pending 517 → 558（+41/日）** | failed 235 は据え置き。`threads.json` は `{}` のまま（最終更新 09-04＝12日間動いていない） |

### ❌ 未解決（継続）

| # | 内容 | 継続 | 09-16 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 3.57日。失効 `2026-09-20 12:05`** |
| 2 | サムネ403 | **5日** | 試行13本中10本が403（company-facts 4 / yokai-watch 3 / scp-lab 3）。成功は daily-science 3本のみ |
| 3 | `ANTHROPIC_API_KEY` 401 | 継続 | `authentication_error` 307件。貼り直しが要る |
| 4 | OAuth 未再認可の残7ch | 継続 | akashic-librarian / fake-paper / pokemon-lab / clip-lab / clip-fukada / clip-kaneko / clip-animal |
| 5 | `channel_metrics` の未集計 | **4日** | 日付は 09-13 まで来たが中身は空（N6） |
| 6 | 画像ブリッジ `threads.json` が空 | **12日** | `{}` / 最終更新 09-04 |
| 7 | 画像ブリッジ pending 増加 | 継続 | **558**（+41/日）・failed 235 |
| 8 | `viral_translation_pending` 17件 | 継続 | 変化なし（08-31〜09-12）。APIキー401のため処理されない |
| 9 | `orch-20260911-followup` 未マージ | **6日** | 3先行・**56遅れ**（N8） |
| 10 | `logs/backend.log` ローテーション未実装 | 継続 | **87,664,685 B**（+1,028,573/日） |
| 11 | `.git` のゴミ | 継続 | `tmp_obj_*` **321**（N4）／ `stale_locks` 83 ／ `index.lock` 1 |
| 12 | 回帰テストが測れない | **6日** | サンドボックスに pytest 無し |
| 13 | oripa `feat/stripe-checkout` 未マージ | **36日** | 9先行・0遅れ |
| 14 | ai-english-coach: Git リモート未設定 | 継続 | `git remote -v` 空 |
| 15 | fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 / ai-orchestrator 未追跡1 | 継続 | 変化なし |
| 16 | aiseki: Twilio トライアル / SNS未投稿 / ロゴ未作成 | 継続 | HANDOFF §38 に「投稿は0件のまま」と明記 |
| 17 | oripa サイト本文が空 | **4日** | 到達するが body が空 |
| 18 | clip-animal の `hard_constraints` 未設定 | 継続 | 停止中なので実害は無いが、再開した瞬間に検査が丸ごとスキップされる |

---

## 4. 全進捗サマリ（URL・ステータス）

| プロジェクト | URL | ステータス | 残タスク |
|---|---|---|---|
| **youtube-factory** | https://youtube-factory-eight.vercel.app | 🟡 稼働・要対応 | 稼働5ch（scp-lab 166 / daily-science 74 / company-facts 42 / yokai-watch 29 / socio-rx 0）＋ 2ch-matome 9（再開したが未発火）。**OAuth 09-20 失効 / サムネ403 / APIキー401** |
| **aiseki** | https://aisekimatch.com | 🟢 開発継続 | Twilio 本番化・DM営業の本番開始判断・SNS初投稿・ロゴ作成・実機確認・運営体制の確定 |
| **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了 | **集客未着手**（16日停滞）。未追跡25件の整理 |
| **oripa** | https://oripa-omega.vercel.app | 🟡 Phase1 MVP | **決済未着手**（`feat/stripe-checkout` 9先行・36日放置）。**サイト本文が空（4日）** |
| **ai-english-coach** | （未デプロイ） | 🔵 Phase1 テキスト版完了 | **音声課金未着手**・LINE Pay 加盟店申込・**GitHub リモート未設定** |
| **切り抜きラボ** | （4ch: clip-lab / clip-fukada / clip-kaneko / clip-animal） | 🔴 全停止 | OAuth 全失効・最終公開 09-06〜09-09。**畳むか再開かの判断待ち** |
| **rhythm-pop** | （ローカル） | ✅ 完成済み | 86日変化なし。未コミット19・リモート未設定 |
| **claude-codex-bridge** | （ローカル） | ✅ 完成済み | 74日変化なし。未追跡1・リモート未設定 |

---

## 5. 次にやるべきこと（ユーザー手動）

**🚨 今すぐ（09-17〜09-19 に必ず）— この順番で**

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project `844705815004` / https://console.cloud.google.com/auth/audience ）
   → **失効 `2026-09-20 12:05`。残り3.57日。同意画面を先に公開してから再認可すること。**
2. 🆕 🚨 **2ch-matome を実際に発火させる**（N1）— `PUT /api/channels/2ch-matome/autopilot` を叩くか backend を再起動。
   **今のままでは「ONにした」だけで1本も出ない。** 判定期日 09-23 の材料が取れなくなる。
3. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch`（ https://youtube.com/verify ）**5日連続で最優先のまま。**
4. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに貼り直す**（`backend/.env` 18行目）
5. **`cd ~/Developer/youtube-factory && git push origin main`**（8コミット未送信）
6. 🆕 **稼働5chのテーマキュー補充**（在庫 4.7〜5.5日・09-21 前後に枯渇）

**判断が要るもの**

7. 🆕 **socio-rx のサムネ生成**（N3）— 403ではなく「パス未指定」。電話番号確認では直らない別件
8. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。akashic-librarian は実力3位）
9. 切り抜き4chを畳むか（全停止・最終公開 09-06〜09-09・キュー111件が死蔵）
10. fake-paper を止めるか作り直すか（OFF・キュー3件）
11. 🆕 **`orch-20260911-followup` は破棄か cherry-pick が妥当**（3先行・**56遅れ**・6日放置。マージの価値はほぼ無い）
12. oripa `feat/stripe-checkout` を main へマージするか（9先行・0遅れ・36日放置）
13. **company-facts の枠 4→3 差し戻し**（09-21 に判定・指揮者メモの申し送り）
14. **いいね率 vs 維持率のどちらを先行指標にするか**（09-21 に独立コホートで本判定・指揮者メモ §3）

**環境の掃除（Mac 側でないと消せない）**

15. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
16. `rm -rf .git/stale_locks .git/_stale* .git/_locksink .git/_trash_consolidated .git/_scratch_delme .git/_writetest`（83件+22件）
17. 🆕 `find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**321件・毎回のマージ run で数百件増える**）
18. `logs/backend.log` **87.7MB**（+1.03MB/日）のローテーション
19. ホストで `pytest backend/tests` を1回流す（6日間測れていない）
20. **`neworigin` リモートを削除してよい**（`git remote remove neworigin`）— 08-31 で放棄。push 先の取り違えを招く

**aiseki（公開前）**

21. **Twilio 本番アップグレード** ／ `dm_targets` の CSV 取り込み（**実在確認＋非公開判定を入れる**）／ 営業本番の開始判断（先頭 `1000bero_net`・1日30件/間隔30〜120秒は変えない）
22. **ChatGPT でのロゴ生成 → Instagram プロフ写真の差し替え**、**SNS 初投稿**（素材 `sns_assets/`・文面 `sns_posts.md`・投稿0件）
23. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
24. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

25. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝**バックアップ無し**）
26. LINE Pay 加盟店申込（**審査があるので最優先**）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

27. **ChatGPT スレッドURLを13ch分登録**（`threads.json` が `{}` のまま12日）／画像ブリッジ pending **558**（+41/日）・failed 235 の処理方針
28. oripa サイトの本文が空（4日連続）— ビルドかルーティングの確認
29. fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 / ai-orchestrator 未追跡1 の整理（任意）
30. **rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach はリモート未設定**（バックアップ無し）。GitHub へ退避

---

## 6. 次回（09-17）の実行時に確認すること

- **🚨 OAuth の残日数**（今日 3.57日 → 明日 2.57日のはず。**失効は 09-20 12:05**）
- 🆕 **2ch-matome が発火したか**（N1）。`video_status` に 09-17 の 2ch-matome 行が入るか。**入らなければ cron 未反映が確定**
- **サムネ403が company-facts / scp-lab / yokai-watch で止まったか**
- **`ANTHROPIC_API_KEY` の401が消えたか**
- **公開本数と枠到達率**（09-16 は稼働5chで 13/13＝100%。**`この枠は公開を止めました` を grep して分子を確かめる**）
- **mdg=2 の2日目**（scp-lab が再び 3/3 か）
- **キュー在庫**（今日 4.7〜5.5日。補充が入ったか。**入らないと 09-21 前後に枯れる**）
- **`channel_metrics` の中身が埋まったか**（日付ではなく `views`/`subscribers_gained` が非ゼロになったか）
- **画像ブリッジ pending**（558 → +41/日の傾きが続くか）
- **09-20**: OAuth 失効日 / **09-21**: 09-14 枠・型変更の本判定、company-facts 枠 4→3、いいね率 vs 維持率 / **09-23**: 2ch-matome 再開と評価期日の延期分

---

## 7. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`git status` の前に必ず `cp .git/index /tmp/x && export GIT_INDEX_FILE=/tmp/x` する。** 空の `GIT_INDEX_FILE` を新規に指すと**全追跡ファイルが `D`（削除）に見え**、本日 dirty=2,850 という偽の数字が出た。実際は **4件**。
- 🆕 **`publish_blocked` の grep 文字列に注意。** 実フォーマットは `⛔ <job_id> [チャンネル名] この枠は公開を止めました:` で、**`⛔ この枠は公開を止めました` では0件になる。** `この枠は公開を止めました` だけで引くこと。
- 🆕 **サムネの失敗は403だけではない。** `ℹ️ サムネイルパス未指定` は403とは別で、**試行すらしていない**。403件数だけ数えると socio-rx を見落とす。
- 🆕 **`latest.md` の「人/1000再生」は直近30日窓、指揮者の「登録/千」は直近50本ローリング窓。** **別の数字なので前日比で並べてはいけない。**
- 🆕 **`autopilot.enabled` を JSON 直書きで true にしても発火しない。** cron を貼り直すのは `_save_autopilot()` → `_refresh_channel_job()` の経路だけ。**「ONにした」を「動き出した」と書かないこと。** 確認は `video_status` の実公開行で。
- **`title_constraints.check()` は「素のタイトル」に当てる。** 公開済みタイトルにはハッシュタグが付き `max_chars` で全滅する。
- **analytics DB は `data/analytics/analytics.db`・日付カラムは `date`。**
- **`channel_metrics` は日付が進んでも中身が空のことがある。** `views` も0なら**未集計**であって実績ゼロではない。
- **`video_metrics` の views は直近30日窓**（`fetch_video_metrics(days=30)`）。同一動画でも日をまたいで**減る**。「再生が減った」と読まない。
- **ch あたり直近50本の固定窓なので、総再生の前日比は意味が無い。**
- **`backend.log` は行頭にタイムスタンプが無い。** `tail -c` で末尾を取り、既知の `video_id` で前後関係を読む。
- **`autopilot.schedule` の枠は `schedule["times"]`。** `schedule["slots"]` は存在しない。
- **`hard_constraints` は `d["title_rules"]["hard_constraints"]`、`theme_queue` は `d["autopilot"]["theme_queue"]`。**
- **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。公開の真偽は `video_id` の有無。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `data/reports/latest.md` の OAuth 表。
- **`data/reports/latest.md` が登録者数の唯一のソース。**
- **views のラグは約2日。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は必ず失敗する。マージ可否は `/tmp` の `git clone -s` で判定する。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- ⚠️ **夜間は `daily-merge-all-projects`(22:09) → 本タスク(23:10) の順で走る。** **マージタスクのコミットを「今日の開発進捗」と読み違えないこと。** 本日の8コミットは自動タスクの成果物同期で、手作業の進捗ではない。

---

## 8. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-16.md`（新規・本ファイル）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform / ai-orchestrator）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
