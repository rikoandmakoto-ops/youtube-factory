# Daily Handoff Log

**実行日時**: 2026-09-13 23:20 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-13.md`
**前回**: 2026-09-12 23:10 / **参照した文脈**: `last_handoff_log.md`(09-12)、`last_merge_log.md`(09-13 22:20)、`.auto-memory/INDEX.md`・`2026-09-10/11/12/13.md`・`projects/apps.md`・`projects/youtube_channels.md`

> ℹ️ bash 完走。git・sqlite・ログ・キューのゲート判定・サイト疎通を全て実測。
> ℹ️ 全数値を別エージェントで独立再計測して突合済み。**2件の誤りを発見して訂正した**（OAuth の秒差 / push 先行数）。
> ℹ️ サイト疎通は `web_fetch`。**今回は oripa も含め4サイト全て取得できた。**

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **部分復旧**（前回🔴出口封鎖） | **09-13 に7本公開＝3日ぶりに出口が開いた**（DB書き込みは22:41 JST・再認可の11分後）。OAuth **6ch再認可 / 7ch失効**。**autopilot が 12ch → 5ch に絞られた**（09-13 12:09）。`ANTHROPIC_API_KEY` 有効化・push 完了・backend 再起動済み |
| aiseki | 🟢 **進捗再開**（前回🟢停止） | 5日ぶりのコミット `3761e5f`（09-13 22:20）＋本番デプロイ。push 済・作業ツリー clean。aisekimatch.com 200 |
| ai-english-coach | 🔵 凍結（変化なし） | コード最終変更 **08-18＝26日**。**Gitリモート未設定のまま**。未コミット0 |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から13日変化なし。未追跡25件。サイト200 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11＝**33日**。`feat/stripe-checkout` が **main より9コミット先行・未マージ**。**サイトは200だが本文が空**（前回未確認→今回取得） |
| 切り抜きラボ(clip 4ch) | 🔴 **全停止** | clip-lab / fukada / kaneko / animal の**4ch すべて 09-13 12:09 に autopilot OFF**。OAuth も4ch全失効。生成・公開ともに0 |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし（83日）。変更10＋未追跡7・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし（71日）。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | **09-13 22:51 `be5014f`** — 今日も動いている |

---

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **公開ゼロ3日連続 → 解除。** 09-13 に7本（scp-lab 2 / company-facts 2 / daily-science 1 / yokai-watch 1 / socio-rx 1）。
- **OAuth 全失効 → 6ch 再認可済み**（09-13 22:30 JST）。scp-lab / company-facts / daily-science / yokai-watch / 2ch-matome / socio-rx。**最後の `upload_done` 以降のログで、この6chの `invalid_grant` は0件**（残7chのみ計80行）。
- **`ANTHROPIC_API_KEY` 未設定（13夜連続）→ 解決。** `backend/.env` 18行目で有効化済み。
- **push 失敗（4日連続・22コミット先行）→ 解決。** 22件 push 済み。aiseki も 4→0。
- **backend 未再起動 → 解決。** ログに週7日の cron 登録（`scp-lab: sun〜sat 13:00 JST`）が出ており、09-12 の schedule 変更が反映された。
- **`video_metrics` 欠測（4日）→ 部分解決。** 09-13 に246行（6ch分）が入った。
- **未コミット51ファイル → 解決。** merge タスクが 09-13 22:20 に4コミットで整理。作業ツリーは残4ファイルのみ。

### ⚠️ 前回レポート／朝の指揮者メモの訂正

- **「未公開台本857件」は誤り。正しくは79件。** 数えていたのは `data/scenarios/*/archive/*.md`（877件）で、ここには **2026-05月分から**入っている（月別 05:31 / 06:150 / 07:172 / 08:272 / 09:252）。同じ期間に697本が公開済み＝archive は公開済みを含む生成履歴。**現役プールは `.json`（archive外）87件、うち未公開79件。** → **「再認可した瞬間に857件が一気に流れる」リスクは存在しない。09-13 メモの警告は取り下げてよい。**
- **`oauth_tokens.expires_at` で失効判定してはいけない。** 全13chで `updated_at` が `expires_at` より8〜9時間あと（11chは +28,801秒ちょうど / pokemon-lab +28,802 / akashic-librarian +32,121）。**再認可直後のトークンまで「失効済み」に見える。** 判定は ①ログの `invalid_grant` の ch別出現 ②実際の公開成否 で行う。過去の「13ch全失効」にはこの読み違いが混ざっていた可能性がある。
- **サムネ403は「判定保留」ではなく「未解決・確定」に変わった**（下の N2）。

### ❌ 未解決

| # | 内容 | 継続 | 09-13 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」（project 844705815004） | 期限超過 | **サンドボックスから確認不能。** テスト中のままなら再認可した6chも **09-20頃に再失効** |
| 2 | OAuth 未再認可の残7ch | 継続 | pokemon-lab / akashic-librarian / fake-paper / clip-lab / clip-fukada / clip-kaneko / clip-animal |
| 3 | `channel_metrics` の欠測 | **8日** | 最終 09-10（前回 09-05 から進んだ）。ただし **09-06〜09-10 の `subscribers_gained` が全ch 0**・views も 27〜241 と異常。**登録者数は依然出せない** |
| 4 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 / images 0 |
| 5 | `viral_translation_pending` の滞留 | 継続 | **17件**（08-31〜09-12・増減なし）。API キーが入ったので次回処理されるか要確認 |
| 6 | `orch-20260911-followup` 未マージ | **3日** | 3コミット先行。コンフリクト2件（`.auto-memory/INDEX.md` / `data/channels/2ch-matome.json`） |
| 7 | `logs/backend.log` ローテーション未実装 | 継続 | **84,165,524 バイト**（09-12: 82,740,449 → +1,425,075） |
| 8 | `tmp_obj_*` / `stale_locks/` の残骸 | 継続 | `tmp_obj_*` **997→1,128** / `stale_locks/` **61→76** |
| 9 | clip-lab の転換ほぼゼロ | 継続 | 現在 autopilot OFF のため実質凍結 |
| 10 | `test_fixes_20260912.py` の赤4件 | **判定不能** | **サンドボックスに pytest が入っていない**（`No module named pytest`）。ホストでないと測れない |
| 11 | aiseki: Twilio トライアル / Instagram `sessionid` 未取得 | 継続 | 変化なし |
| 12 | ai-english-coach: Gitリモート未設定 | **26日** | `git remote -v` が空 |
| 13 | fanup 未追跡25件 / rhythm-pop 変更10＋未追跡7 | 継続 | 変化なし |
| 14 | oripa `feat/stripe-checkout` 未マージ | **33日** | **main より9コミット先行**（前回は「測定不能」だった） |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨 **autopilot が 13ch中8chで OFF になった** | 09-13 **12:09:35** に `2ch-matome / akashic-librarian / clip-animal / clip-fukada / clip-kaneko / clip-lab / fake-paper / pokemon-lab` が `enabled:false` へ。同時に **socio-rx が false→true**。09-12 最終コミット `88d1a18`(22:07) 時点では socio-rx 以外の12chが全て true。**朝の指揮者メモ(10:17)は「config は1文字も変えていない」と記録＝指揮者以外の変更。** 効果は即時（12:09以降に生成したのは稼働5chのみ）。**絞り込み先は登録/千 上位ch＋再認可済みchに一致しており合理的だが、記録が残っていない** |
| **N2** | 🚨 **サムネ403が「判定保留」→「確定」に** | 09-13 公開の**7本すべて**でサムネ設定が403失敗。`The authenticated user doesn't have permissions to upload and set custom video thumbnails.`（reason: forbidden / domain: youtube.thumbnail）＝**チャンネルの電話番号確認が未了**。トークンの問題ではない。**7本ともデフォルトサムネで公開されている** |
| **N3** | ⚠️ **キュー適合率 64.1%（248件中 不合格89）。不合格が稼働主力3chに集中** | company-facts 19/24・yokai-watch 18/24・daily-science 15/18。違反内訳 `min_effective_chars` **55**（うち18〜19字が**29**）/ `max_digit_groups` 15 / `require_any_of` 14 / `banned_words` 11。**直すべきは生成側プロンプト。機械 repair は禁止** |
| **N4** | ⚠️ **`title_gate_ok` が依然0件（274件中0）** | **backend 再起動後も付かない。** 再起動で cron は更新されたのに印は付かない＝実装がキューへの書き戻し経路に入っていない可能性が高い。**3日連続で目的未達** |
| **N5** | ⚠️ **画像ブリッジ pending 370 → 424（+54/日）** | delivered 0 / failed 235 据え置き |
| **N6** | ℹ️ **09-13 スナップショットの登録/千は 0.582**（6ch・246本・188,858再生・110登録） | ch別 scp-lab 0.819 / yokai-watch 0.733 / company-facts 0.649 / daily-science 0.640 / 2ch-matome 0.165。**09-08 の 0.377 は12ch・30日窓なので直接比較しない** |
| **N7** | ⚠️ **socio-rx が稼働chに戻ったのに `hard_constraints` 未設定** | `is_enforced()` が False ＝ **タイトル検査が丸ごとスキップ**。キュー12件が無検査。09-13 に1本公開済み |
| **N8** | ℹ️ **youtube-factory の push 先は2つあり未確定** | `origin`=zaki21016（先行1・23:1x の `89a323e`）/ `neworigin`=rikoandmakoto-ops（**先行65**）。**どちらが正か決まっていない** |

---

## 3. ユーザー手動待ちタスク一覧

**今すぐ（09-14 朝）— この順番で**

1. 🚨 **N1 の確認** — 8ch の autopilot OFF（09-13 12:09）は意図したものか。意図的なら `.auto-memory` に理由を記録／意図外なら戻す
2. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project 844705815004）。**やらないと再認可した6chも09-20頃に再失効**
3. 🚨 **YouTube Studio で各chのアカウント確認（電話番号）** — N2 のサムネ403の原因。やるまで全動画がデフォルトサムネ

**判断が要るもの**

4. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**再認可するほうが早い）
5. 切り抜き4chを畳むか（全停止中・OAuth全失効・30日窓で登録/千 0.004〜0.193）
6. fake-paper を止めるか作り直すか（30日窓で登録ゼロ・現在OFF）
7. `orch-20260911-followup` のマージ方針（main側＝エントリ削除済みの採用が妥当に見える）
8. N3 の対処＝生成プロンプト側で実効20字を満たさせる（機械 repair は禁止）
9. oripa `feat/stripe-checkout` を main へマージするか（**9コミット先行・33日放置**）
10. N8＝youtube-factory の push 先を `origin` / `neworigin` のどちらに一本化するか

**環境の掃除（Mac 側でないと消せない）**

11. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
12. `rm -rf .git/stale_locks .git/_stale*`（**76件**）／`find .git/objects -name 'tmp_obj_*' -delete`（**1,128件**）／`git gc --prune=now`
13. `logs/backend.log` **84,165,524 バイト**のローテーション
14. ホストで `pytest backend/tests` を1回流す（サンドボックスに pytest が無く3日間確認できていない）

**aiseki（公開前）**

15. **Twilio 本番アップグレード** ／ **Instagram ログイン**（`cd worker && npm run login`）／ `dm_targets` の CSV 取り込み ／ SNSアカウント（@aisekimatch）開設 ／ live で1回購入して確認 ／ サインアップの CAPTCHA
16. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
17. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

18. **GitHub リモートの作成と push**（26日ローカルのみ＝バックアップ無し）
19. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

20. ChatGPT スレッドURLを13ch分登録 / `REDDIT_CLIENT_ID` の設定
21. 画像ブリッジ pending **424** / failed 235 の処理方針
22. `viral_translation_pending` **17件** — API キーが入ったので処理されるか09-14に確認
23. fanup 未追跡25件 / rhythm-pop 変更10＋未追跡7 の整理（任意）

---

## 4. 次回（09-14）の実行時に確認すること

- **autopilot 5ch 体制が続いているか**（N1 が意図的だったか）
- **公開本数**（09-13 は7本。5ch体制なら1日13本前後が上限）
- **サムネ403が止まったか**（アカウント確認を実施した場合）
- **6chのトークンが 09-14 も生きているか** — 生きていれば「同意画面が本番公開済み」の傍証
- **`channel_metrics` が 09-10 から進んだか／`subscribers_gained` がゼロでなくなったか**
- **`title_gate_ok` がキューに付いたか**（3日連続0件）
- **キュー適合率**（今回 **64.1%＝159/248**。09-12 の 60.5%＝155/256 とは母集団が近いので比較可）
- **socio-rx に `hard_constraints` が付いたか**（N7）
- **`viral_translation_pending` が17件から減ったか** / **画像ブリッジ pending が424から減ったか**
- **09-15**: 答え提示型100%化の反証期限 / **09-16**: 「実は」出現率 / **09-19**: scp-lab 週7日化・company-facts 4枠化の効果検証 / **09-20**: 09-09 施策の評価
  → **公開が再開したので 09-19 の検証は成立する見込み。ただし母集団は5chに縮む。**

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 **`oauth_tokens.expires_at` で失効判定しない。** 全13chで `updated_at` が `expires_at` より8〜9時間あと。再認可直後のトークンも「失効済み」に見える。**判定はログの `invalid_grant` と実際の公開成否で行う。**
- 🆕 **`data/scenarios/*/archive/*.md` は「未公開在庫」ではない。** 2026-05月分から入っており公開済みを含む。**現役プールは `data/scenarios/*/*.json`（archive外）。**
- 🆕 **`data/job_queue.json` は読むタイミングで形が変わる。** 本タスク中に `list`(641要素) → `{"version":…,"jobs":[…]}` に変わった。**必ず `raw.get("jobs", raw)` で吸収する。**
- 🆕 **サンドボックスに pytest が入っていない。** 回帰テストの本数はホストでしか測れない。
- 🆕 **`video_metrics` の最新スナップショット日は ch ごとに違う**（09-13 が6ch / 09-08 が4ch / 09-06 が3ch）。全ch合算すると窓の違う数字が混ざる。
- 🆕 **未 push 数は remote を明示して書く。** youtube-factory は `origin`(zaki21016) と `neworigin`(rikoandmakoto-ops) で **1 対 65** と桁が違う。
- **`title_constraints.is_enforced()` / `check()` には生の dict を渡す**（`ChannelProfile` や `.data` を渡すと `AttributeError` か常に False）。`check()` の戻りは `{"ok":bool,"violations":[{"rule":…}]}`。
- **`theme_queue` は `d["autopilot"]["theme_queue"]`**、**`hard_constraints` は `d["title_rules"]["hard_constraints"]`**。
- **ログのサイズはバイト数で記録する。**
- **実行中に別タスクが同じ repo を書く。** 本タスクの 23:10→23:20 の10分間に新規コミット `89a323e` が入った。**未コミット件数・先行コミット数は計測時刻とセットで記録すること。**
- `curl` は egress 不可。サイト疎通は `web_fetch`。**URL はタスク定義に載っているものだけ取得できる**（今回は oripa も定義にあり取得成功）。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。判定は `/tmp` へのクローンで行う。

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-13.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform）への書き込み・git 操作（push/merge/commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
