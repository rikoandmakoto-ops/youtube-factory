# Daily Handoff Log

**実行日時**: 2026-09-14 23:25 JST
**タスク**: daily-project-handoff
**フルレポート**: `data/reports/project_handoff_2026-09-14.md`
**前回**: 2026-09-13 23:20 / **参照した文脈**: `last_handoff_log.md`(09-13)、`last_merge_log.md`(09-13 22:20)、`.auto-memory/` の 2026-09-10〜09-14・INDEX.md・projects/

> ℹ️ bash 完走。git・sqlite・ログ・キューのゲート判定・サイト疎通を全て実測。
> ℹ️ 全数値を別エージェントで独立再計測して突合。**3件の誤りを発見して訂正した**（公開本数の UTC/JST / 未コミット件数 / `title_gate_ok` の解釈）。
> ℹ️ サイト疎通は `web_fetch`。4サイトすべて 200。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応** | **09-14 に18本公開**（JST／09-13 は7本）＝5ch集中運用が完全に機能。ただし **OAuth 残り5.57日（09-20 失効）**・**サムネ403が3ch継続**・**登録者数が6chしか測れない**・**ANTHROPIC_API_KEY が401** |
| aiseki | 🟢 **正常・進捗継続** | 09-14 に3コミット（Instagram DM worker）。作業ツリー clean、origin 先行0。aisekimatch.com 200 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝6日。未コミット0。**Git リモート未設定のまま** |
| fanup | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から14日変化なし。未追跡25件。サイト200 |
| oripa | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11＝**34日**。`feat/stripe-checkout` が **9先行・0遅れ＝コンフリクト無しでマージ可**。**サイト200だが本文が空**（2日連続） |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | 4ch autopilot OFF・OAuth全失効。`clip-animal` だけ `hard_constraints` 未設定 |
| rhythm-pop | ✅ 完成済み | 06-22 以降変化なし（84日）。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降変化なし（72日）。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | **09-14 22:42 `1d5de13`** |

---

## 2. 検出した課題

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **push 先行22コミット → 解決。** `origin/main`(zaki21016) 先行 **0**。
- **socio-rx の `hard_constraints` 未設定（前回 N7）→ 解決。** `0b600d0`。`is_enforced()` も True。
- **`video_metrics` の欠測 → 解決。** 6chで 09-14 まで入っている（253行）。
- **`repair()` の `forbid_patterns` 素通り → 解決。** `2a18302`。10:40以降に生成した台本13件で `forbid_patterns` 違反0。
- **`channel_metrics` 09-10 止まり → 09-11 まで前進**（ただし `subscribers_gained` は依然全ch 0）。

### ⚠️ 過去レポートの訂正

- 🔧 **「`ANTHROPIC_API_KEY` 未設定 → 解決」は誤り。** キーは `backend/.env` 18行目にある（108文字・`sk-ant-api03` 始まり）が **API が 401 `API key is invalid` を返し続けている**（ログに471回）。**キーが無効。「設定する」ではなく「新しいキーを発行して差し替える」タスク。** Claude分析・dual scenario gen・`viral_translation_pending` が全て止まる原因。
- 🔧 **キュー適合率 64.1%（09-13）は測り方が誤り。** `min_effective_chars` と `require_any_of` を**キューの題材**に課していた。`title_constraints.py` の docstring 自身が「題材は最終タイトルではないため課すのは意味が無い」と明記。**正しい適合率は 84.0%（226/269）。** 全規則で数えると 58.7%。
- 🔧 **公開本数は UTC/JST を明示する。** `published_at` は UTC。前回の「09-13 に7本」は偶然一致していたが方法は誤り。
- 🔧 **`check()` / `is_enforced()` にはチャンネルJSON全体を渡す。** `hard_constraints` だけだと常に False。前回の「socio-rx は `is_enforced()` が False」も、この踏み間違いだった可能性がある。

### ❌ 未解決

| # | 内容 | 継続 | 09-14 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」 | 期限超過 | **残り 5.57日＝09-20 前後に稼働6chが一斉失効**（数値として確定） |
| 2 | OAuth 未再認可の残7ch | 継続 | akashic-librarian / fake-paper / pokemon-lab / clip-lab / clip-fukada / clip-kaneko / clip-animal。**この7chは登録者数も測れない** |
| 3 | `channel_metrics` の `subscribers_gained` が全ch 0 | **9日** | 最新 09-11（1日前進）。09-06〜09-11 の gained/lost が全ch 0 |
| 4 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 |
| 5 | `viral_translation_pending` の滞留 | 継続 | **17件**（増減なし）。**API キー401のため今後も処理されない** |
| 6 | `orch-20260911-followup` 未マージ | **4日** | 3先行・27遅れ。コンフリクト2件 |
| 7 | `logs/backend.log` ローテーション未実装 | 継続 | **85,605,908 バイト**（+1,440,384/日） |
| 8 | `tmp_obj_*` / `stale_locks/` の残骸 | 継続 | `tmp_obj_*` **1,128→1,215** / `stale_locks/` **76→78** |
| 9 | 回帰テストが測れない | **4日** | サンドボックスに pytest 無し |
| 10 | oripa `feat/stripe-checkout` 未マージ | **34日** | **9先行・0遅れ** |
| 11 | ai-english-coach: Git リモート未設定 | 継続 | `git remote -v` 空。最終コミット 09-08 |
| 12 | fanup 未追跡25 / rhythm-pop 未コミット19 / bridge 未追跡1 | 継続 | 変化なし |
| 13 | aiseki: Twilio トライアル / Instagram `sessionid` | 継続 | worker は 09-14 に改善3件。本番アップグレードは未 |
| 14 | push 先が2つ | 継続 | `origin` 先行0 / `neworigin` **先行68**。どちらが正か未決 |

### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🟢 **サムネ403は ch単位で、すでに2ch通っている** | 09-14 の全25 upload を video_id 突合: **daily-science 5/5・socio-rx 2/2 成功**、**company-facts 0/7・scp-lab 0/6・yokai-watch 0/5 が403**。**＝ユーザーがやるべきは稼働中の残り3chの電話認証だけ**（前回は「daily-science だけ」と記録） |
| **N2** | 🔴 **`title_gate_ok` は「0件」ではなく「フィールドが存在しない」** | `job_queue.json` 全659ジョブのキー集合に無い。あるのは `scenario_data.title_gate:{"cleaned":false}` 25件。**3日間、実装されていない指標を数えていた。** 実装するか監視から外すか要判断 |
| **N3** | 🔴 **ゲートは検知しても止めない穴が残存** | 09-14 18:18 生成の `SCP-1440_追跡班が7日目に報告をやめた謎` が `ok:false`（`max_digit_groups`/`require_any_of`）のまま 10:00Z に公開。`forbid_patterns` は直ったが**「ok:false なら公開しない」分岐が無い**のは未対処 |
| **N4** | ⚠️ **キュー適合率が最も低いのが稼働5ch** | 正しい測り方でも **scp-lab 53%(10/19)・socio-rx 57%(8/14)** が下位。停止中の akashic-librarian / fake-paper / yokai-watch / daily-science は100%。違反は `max_digit_groups`16 / `banned_words`12 / `forbid_digits`10 / `forbid_patterns`7＝**いずれも repair 可能な規則** |
| **N5** | ⚠️ **画像ブリッジ pending 424 → 478（+54/日で3日一定）** | failed 235 / delivered 0 据え置き。**放置すると1ヶ月で約2,100件** |
| **N6** | 🟢 **aiseki が2日連続で動いた** | 09-14 13:59 までに3コミット（Cookie sessionid 検知 / DMスレッド判定を `/direct/t/` に限定 / 非公開アカウントの理由表示）。Instagram DM worker が実運用フェーズ |
| **N7** | ⚠️ **未コミット件数は測定中に増える** | 本タスク中に 58 → 62 件（M34 + ??28）。backend 稼働中。**時刻とセットで記録すること** |
| **N8** | ℹ️ **`clip-animal` だけ `hard_constraints` 未設定** | 停止中なので実害は無いが再開時に無検査で走る |
| **N9** | ℹ️ **09-13以降の25本すべて views=0 だが、これは異常ではない** | 過去スナップショットで views>0 の最新公開日は一貫して **公開から約2日遅れ**（09-08 snap → 09-06）。**09-13公開分の初回実績は 09-15 の fetch が最短。** 5ch集中運用の判定点は 09-15 |
| **N10** | ℹ️ **09-14 スナップショットの登録/千は 0.594**（6ch・180,226再生・107登録） | ch別 scp-lab 0.863 / yokai-watch 0.787 / daily-science 0.663 / company-facts 0.619 / 2ch-matome 0.152。09-13 の 0.582 から +0.012 |
| **N11** | ℹ️ **登録者数の絶対値（`latest.md` 由来）** | scp-lab 162 / daily-science 72 / company-facts 36 / yokai-watch 27 / 2ch-matome 9 / socio-rx 0。**残7chは OAuth 失効のため測定不能** |

---

## 3. ユーザー手動待ちタスク一覧

**🚨 今すぐ（09-15〜09-19 に必ず）— この順番で**

1. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」へ公開**（project 844705815004 / `console.cloud.google.com/auth/audience`）
   → **残り 5.57日。09-20 前後に稼働6chが一斉に落ちる。落ちたら公開もアナリティクスも全停止。**
2. 🚨 **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch` のみ（`youtube.com/verify`）
   → daily-science と socio-rx は既に通過済み。**残りはこの3chだけ。** やるまで全動画がデフォルトサムネ。
3. 🚨 **`ANTHROPIC_API_KEY` を新しいキーに差し替える**（`backend/.env` 18行目）— 現キーは401。Claude分析・dual gen・`viral_translation_pending` が全停止中。

**判断が要るもの**

4. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。今の7chは登録者数すら測れない）
5. 切り抜き4chを畳むか（全停止・OAuth全失効・測定不能）
6. fake-paper を止めるか作り直すか（OFF・測定不能）
7. `orch-20260911-followup` のマージ方針（4日放置。main側＝エントリ削除済みの採用が妥当に見える）
8. **N3: 「`title_constraints.ok:false` なら公開しない」分岐を入れるか**（今日の18本中1本が該当）
9. **N2: `title_gate_ok` を実装するか、監視項目から外すか**
10. oripa `feat/stripe-checkout` を main へマージするか（**9先行・0遅れ＝コンフリクト無し**・34日放置）
11. push 先を `origin` / `neworigin` のどちらに一本化するか（neworigin は68先行）

**環境の掃除（Mac 側でないと消せない）**

12. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
13. `rm -rf .git/stale_locks .git/_stale*`（**78件**）／`find .git/objects -name 'tmp_obj_*' -delete`（**1,215件**）／`git gc --prune=now`
14. `logs/backend.log` **85,605,908 バイト**（+1.44MB/日）のローテーション
15. ホストで `pytest backend/tests` を1回流す（4日間サンドボックスで測れていない）

**aiseki（公開前）**

16. **Twilio 本番アップグレード** ／ **Instagram ログイン**（`cd worker && npm run login`）／ `dm_targets` の CSV 取り込み ／ SNSアカウント（@aisekimatch）開設 ／ live で1回購入して確認 ／ サインアップの CAPTCHA
17. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
18. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

**ai-english-coach**

19. **GitHub リモートの作成と push**（最終コミット 09-08・ローカルのみ＝バックアップ無し）
20. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

21. ChatGPT スレッドURLを13ch分登録 / `REDDIT_CLIENT_ID` の設定
22. 画像ブリッジ pending **478**（+54/日）/ failed 235 の処理方針
23. oripa サイトの本文が空（2日連続）— ビルドかルーティングの確認
24. fanup 未追跡25件 / rhythm-pop 未コミット19件の整理（任意）

---

## 4. 次回（09-15）の実行時に確認すること

- **🚨 OAuth の残日数**（今日 5.57日 → 明日 4.57日のはず）
- **サムネ403が company-facts / scp-lab / yokai-watch で止まったか**
- **09-13公開7本の初回実績** — **ラグ2日なので 09-15 の fetch で初めて views が入る。5ch集中運用の最初の判定点**
- **`ANTHROPIC_API_KEY` の401が消えたか** / **`viral_translation_pending` が17件から減ったか**
- **`channel_metrics` が 09-11 から進み `subscribers_gained` がゼロでなくなったか**
- **公開本数**（09-14 は18本／JST。**必ず +9h してから日付を切る**）
- **キュー適合率**（今回 **84.0%＝226/269**、`min_effective_chars`/`require_any_of` 除外。**次回も同じ2規則を除いて比較すること**）
- **画像ブリッジ pending**（478 → +54/日の傾きが続くか）
- **N3 の分岐**（`ok:false` のまま公開された本数。今日は1本）
- **09-16**: 「実は」出現率 / **09-19**: scp-lab 週7日化・company-facts 4枠化の効果検証 / **09-20**: 09-09 施策の評価＆**OAuth 失効日**

---

## 5. 計測方法の注意（次回実行者向け）

- 🆕 **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。しないと 22:30Z / 23:15Z の公開が前日に入る。
- 🆕 **`title_constraints.check()` / `is_enforced()` にはチャンネルJSON全体の dict を渡す。** `hard_constraints` だけだと常に False。
- 🆕 **キューの題材に `min_effective_chars` と `require_any_of` を課さない。** モジュールの docstring が「題材は最終タイトルではない」と明記。適合率はこの2規則を除いて出す。
- 🆕 **`title_gate_ok` というキーは `job_queue.json` に存在しない。** 「0件」を報告しても意味が無い。
- 🆕 **未コミット件数は計測中に増える**（backend 稼働中）。**時刻とセットで記録する。**
- 🆕 **`data/reports/latest.md` に登録者数と OAuth 残日数が入っている。** DB には登録者の絶対数が無いので、ここが唯一のソース。ただし **OAuth が生きている ch しか値が入らない。**
- 🆕 **views のラグは約2日。** 「公開したのに views=0」を不具合と読まない。判定はスナップショット日 −2日まで。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `latest.md` の「OAuth トークン寿命」表か、ログの `invalid_grant` の ch別出現で行う。
- **`data/scenarios/*/archive/*.md` は未公開在庫ではない。** 現役プールは `data/scenarios/*/*.json`（archive外・105件）。
- **`data/job_queue.json` は `raw.get("jobs", raw)` で吸収する。**
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`impressions` 列は窓と整合しない。** CTR は `video_reach_daily` を使う。
- **`video_metrics` の最新スナップショット日は ch ごとに違う**（09-14 が6ch / 09-08 が4ch / 09-06 が3ch）。全ch合算すると窓の違う数字が混ざる。
- **`theme_queue` は `d["autopilot"]["theme_queue"]`**、**`hard_constraints` は `d["title_rules"]["hard_constraints"]`**。
- **ログのサイズはバイト数で記録する。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge` / `git checkout` は必ず失敗する。判定は `/tmp` へのクローンで行う。lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で退避。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。

---

## 6. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-14.md`（新規）
- `data/reports/last_handoff_log.md`（本ファイル・上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
