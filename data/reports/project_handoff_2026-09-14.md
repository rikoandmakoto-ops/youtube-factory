# 全プロジェクト引き継ぎレポート — 2026-09-14（月）

**実行**: 2026-09-14 23:25 JST / **前回**: 09-13 23:20
**参照した文脈**: `last_handoff_log.md`(09-13) / `last_merge_log.md`(09-13 22:20) / `.auto-memory/` 2026-09-10〜09-14・INDEX.md・projects/

> 全数値は bash で実測し、別エージェントで独立に再測定して突合した。**突合で3件の誤りを見つけて訂正済み**（公開本数の日付基準 / 未コミット件数 / `title_gate_ok` の解釈）。
> サイト疎通は `web_fetch` で4サイト取得。

---

## 0. 一行で

**出口は完全に開いた（09-14 に 18本公開＝直近最多）。詰まっているのは「測る」側と「見せる」側。**
登録者数は 6ch しか取れず、伸びは 09-11 で止まっている。サムネイルは 5ch中2ch しか視聴者に届いていない。
そして **09-20 に OAuth が6ch一斉に切れる**（残り 5.57日、実測）。

---

## 1. プロジェクト別ステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| **youtube-factory** | 🟡 **要対応**（前回🟡部分復旧） | **09-14 に18本公開**（09-13 は7本／JST基準）。5ch集中運用が完全に機能。ただし **OAuth 残り5.57日**・**サムネ403が3chで継続**・**登録者数が6chしか測れない** |
| **aiseki** | 🟢 **正常・進捗継続**（前回🟢進捗再開） | **09-14 に3コミット**（Instagram DM worker の判定改善）。作業ツリー clean、origin 先行0。aisekimatch.com 200 |
| **ai-english-coach** | 🔵 凍結（変化なし） | 最終コミット **09-08**＝6日前。未コミット0。**Git リモート未設定のまま**（バックアップ無し） |
| **fanup** | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から14日変化なし。未追跡25件（事業計画書 docx/pdf/pptx 等）。サイト200・サポーター1,248表示 |
| **oripa** | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11＝**34日**。`feat/stripe-checkout` が main より **9コミット先行・0遅れ**。**サイトは200だが本文が空**（2日連続で同じ） |
| **切り抜きラボ(clip 4ch)** | 🔴 全停止（変化なし） | 4ch すべて autopilot OFF・OAuth全失効。生成・公開ともに0。`clip-animal` だけ `hard_constraints` 未設定 |
| **rhythm-pop** | ✅ 完成済み | 06-22 以降変化なし（84日）。未コミット19件・リモート未設定 |
| **claude-codex-bridge** | ✅ 完成済み | 07-04 以降変化なし（72日）。未追跡1件・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | **09-14 22:42 `1d5de13`** — 本日も動いている |

---

## 2. youtube-factory 詳細

### 2-1. 公開状況（JST基準）

| 日 | 本数 |
|---|---:|
| 09-14 | **18** |
| 09-13 | 7 |
| 09-12 | 0 |
| 09-11 | 0 |
| 09-10 | 2 |

> ⚠️ **計測注意**: `video_status.published_at` は **UTC の `Z` 付き**。日付文字列をそのまま JST として数えると 09-13 22:30Z / 23:15Z の2本が 09-13 に誤計上される。前回レポートの「09-13 に7本」は偶然一致しているが、方法は誤り。**必ず +9h してから日付を切ること。**

内訳（09-14 JST）: company-facts 5 / scp-lab 5 / daily-science 4 / yokai-watch 4 / socio-rx 1。
**5ch集中運用（09-13 の autopilot 絞り込み）は成立している。** cron も週7日で登録済み（company-facts は 17:00/19:00 を含む4枠、socio-rx は平日20:00＋土日15:00）。

### 2-2. チャンネル別（09-14 スナップショット）

| ch | autopilot | 登録者 | 総再生 | 本数 | 登録/千（直近50本） | OAuth | サムネ |
|---|---|---:|---:|---:|---:|---|---|
| scp-lab | ✅ | **162** | 166,728 | 194 | **0.863** | OK 5.57日 | ❌ 403 |
| yokai-watch | ✅ | 27 | 55,870 | 58 | **0.787** | OK 5.57日 | ❌ 403 |
| daily-science | ✅ | 72 | 200,318 | 215 | 0.663 | OK 5.57日 | ✅ 成功 |
| company-facts | ✅ | 36 | 57,541 | 50 | 0.619 | OK 5.57日 | ❌ 403 |
| socio-rx | ✅ | 0 | 1,070 | 2 | — (再生0) | OK 5.57日 | ✅ 成功 |
| 2ch-matome | ❌ | 9 | 47,451 | 51 | 0.152 | OK 5.56日 | — |
| akashic-librarian / fake-paper / pokemon-lab / clip-lab / clip-fukada / clip-kaneko / clip-animal | ❌ | **測定不能** | — | — | — | ❌ 失効 | — |

**合計 登録/千 = 0.594**（6ch・180,226再生・107登録）。09-13 の 0.582 から +0.012。
**登録者数が取れるのは OAuth が生きている6chだけ。** 残り7chは「登録者ソースが取得できないため判断保留」と出ており、再認可しない限り永久に測れない。

### 2-3. 前回施策の検証

| 施策 | 判定 |
|---|---|
| 09-13: 5ch集中運用 | **○ 成立**。09-14 に18本＝直近最多 |
| 09-13: company-facts 毎日投稿化 | **○ 成立**。09-14 に5本 |
| 09-13: socio-rx に `hard_constraints` | **○ 設定確認済み**（前回 N7 は解消） |
| 09-14: `title_constraints.repair()` の `forbid_patterns` 対応 | **○ 効いている**。10:40以降に生成された台本13件で `forbid_patterns` 違反は**0件**（修正前は当日2件） |
| 09-12: scp-lab 週7日化 / company-facts 4枠化 | **△ まだ測れない**（後述） |

### 2-4. 🔴 「効果がまだ1本も測れていない」ことの確定

**09-13 以降に公開した25本すべてが、09-14 スナップショットで `views=0`。**

これは異常ではなく **YouTube Analytics の集計ラグ**。過去のスナップショットで「views>0 が入っている最新の公開日」を見ると一貫して **公開から約2日遅れ**:

| スナップショット日 | views>0 の最新公開日 | ラグ |
|---|---|---|
| 09-08 | 09-06 | 2日 |
| 09-13 | 09-09 | （09-10〜12 は公開0本） |
| **09-14** | **09-09** | 同上 |

→ **09-13公開分の初回実績が入るのは 09-15 の fetch。** 「週7日化」「枠増設」「5ch集中」の効果判定は **09-15 が最短**で、09-19 の本判定まで動かさないこと。

---

## 3. 検出した課題

### ✅ 前回から解決を確認（次回「要対応」として報告しないこと）

- **push 先行22コミット → 解決。** `origin/main`(zaki21016) 先行 **0**。作業ツリーの変更は日々の自動生成分のみ。
- **socio-rx の `hard_constraints` 未設定（前回 N7）→ 解決。** `0b600d0` で設定済み。`is_enforced()` も True。
- **`video_metrics` の欠測 → 解決。** 6chで **09-14** まで入っている（253行）。
- **`repair()` の `forbid_patterns` 素通り → 解決。** コミット `2a18302`。実効も確認済み（§2-3）。
- **`channel_metrics` 09-10 止まり → 09-11 まで進んだ**（1日ぶん前進。ただし下の #3 は未解決）。

### ⚠️ 過去レポートの訂正

- 🔧 **「`ANTHROPIC_API_KEY` 未設定 → 解決」は誤り。** キー自体は `backend/.env` 18行目に入っている（108文字・`sk-ant-api03` 始まり）が、**API が 401 `authentication_error: API key is invalid` を返し続けている**（ログに471回）。**キーが無効＝失効か誤りである。** その結果、`latest.md` のあらゆる Claude 分析が「スキップ（ANTHROPIC_API_KEY が無効）」になり、dual scenario gen も GPT単独に劣化したまま。**これは「設定する」ではなく「新しいキーを発行して差し替える」タスク。**
- 🔧 **キュー適合率 64.1%（09-13）は測り方が誤っていた。** `min_effective_chars` と `require_any_of` を**キューの題材**に課していたが、`title_constraints.py` の docstring 自身が「題材は最終タイトルではないため、20字下限を題材に課すのは意味が無い — `require_any_of` と同じ理由」と明記している。**この2規則を除いた正しい適合率は 84.0%（226/269）。**（全規則で数えると 58.7%）
- 🔧 **公開本数は UTC/JST を必ず明示する**（§2-1）。
- 🔧 **`title_constraints.check()` / `is_enforced()` には「チャンネルJSON全体の dict」を渡す。** `hard_constraints` だけを渡すと **必ず False** になる（本タスク中に一度踏んだ）。前回レポートの「socio-rx は `is_enforced()` が False」も、この踏み間違いだった可能性がある。

### ❌ 未解決（継続）

| # | 内容 | 継続 | 09-14 の実測 |
|---|---|---|---|
| 1 | **GCP OAuth 同意画面が「テスト中」** | 期限超過 | **残り 5.57日＝09-20 前後に稼働6chが一斉失効。** 数値として確定した |
| 2 | OAuth 未再認可の残7ch | 継続 | akashic-librarian / fake-paper / pokemon-lab / clip-lab / clip-fukada / clip-kaneko / clip-animal。**この7chは登録者数すら測れない** |
| 3 | `channel_metrics` の `subscribers_gained` が全ch 0 | **9日** | 最新 09-11（1日前進）。だが 09-06〜09-11 の `subscribers_gained` / `lost` が全ch 0。**日次の登録増減は依然として出せない** |
| 4 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 |
| 5 | `viral_translation_pending` の滞留 | 継続 | **17件**（08-31〜09-12・増減なし）。**API キーが401なので今後も処理されない**（#の ANTHROPIC 訂正と同根） |
| 6 | `orch-20260911-followup` 未マージ | **4日** | main より3先行・27遅れ。コンフリクト2件（`.auto-memory/INDEX.md` / `data/channels/2ch-matome.json`） |
| 7 | `logs/backend.log` ローテーション未実装 | 継続 | **85,605,908 バイト**（09-13: 84,165,524 → **+1,440,384/日**） |
| 8 | `tmp_obj_*` / `stale_locks/` の残骸 | 継続 | `tmp_obj_*` **1,128→1,215** / `stale_locks/` **76→78** |
| 9 | 回帰テストの本数が測れない | **4日** | サンドボックスに pytest 無し。ホストでしか測れない |
| 10 | oripa `feat/stripe-checkout` 未マージ | **34日** | 9コミット先行・0遅れ（＝クリーンにマージ可能） |
| 11 | ai-english-coach: Git リモート未設定 | **継続** | `git remote -v` が空。最終コミット 09-08 |
| 12 | fanup 未追跡25 / rhythm-pop 未コミット19 / claude-codex-bridge 未追跡1 | 継続 | 変化なし |
| 13 | aiseki: Twilio トライアル / Instagram `sessionid` | 継続 | worker 側は 09-14 に改善コミット3件。本番アップグレードは未 |
| 14 | youtube-factory の push 先が2つ | 継続 | `origin`(zaki21016) 先行0 / `neworigin`(rikoandmakoto-ops) **先行68**。どちらが正か未決 |

### 🆕 NEW（今回はじめて検出／前回から質的に変わったもの）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🟢 **サムネ403は「チャンネル単位」で、すでに2ch通っている** | 09-14 の全25 upload を video_id で突合: **daily-science 5/5 成功・socio-rx 2/2 成功**、**company-facts 0/7・scp-lab 0/6・yokai-watch 0/5 が403**。前回「通っているのは daily-science だけ」→ socio-rx も通っていた。**＝ユーザーがやるべきは全13chではなく、稼働中の残り3ch（company-facts / scp-lab / yokai-watch）の電話認証だけ。** しかもこの3chは登録/千の上位を占める |
| **N2** | 🔴 **`title_gate_ok` は「0件」ではなく「フィールドが存在しない」** | `data/job_queue.json` 全659ジョブのキー集合に `title_gate_ok` が**無い**。あるのは `scenario_data.title_gate: {"cleaned": false}` が25件。**3日間「0件」と報告してきたが、実装されていない指標を数えていた。** 監視項目から外すか、書き戻し経路を実装するかを決める必要がある |
| **N3** | 🔴 **ゲートは「検知しても止めない」穴が残っている** | 09-14 18:18 生成の `SCP-1440_追跡班が7日目に報告をやめた謎` が `title_constraints.ok:false`（`max_digit_groups` / `require_any_of`）のまま **10:00Z に公開された**。`forbid_patterns` は直ったが、**「ok:false なら公開しない」分岐そのものが無い**という09-14朝の指摘は未対処 |
| **N4** | ⚠️ **キュー適合率が最も低いのが稼働5ch** | 正しい測り方（`min_effective_chars`/`require_any_of` 除外）でも **scp-lab 53%(10/19)・socio-rx 57%(8/14)** が下位。停止中の akashic-librarian / fake-paper / yokai-watch / daily-science は100%。**違反は `max_digit_groups` 16 / `banned_words` 12 / `forbid_digits` 10 / `forbid_patterns` 7 で、いずれも機械 repair 可能な規則**。生成側プロンプトで抑えるのが本筋 |
| **N5** | ⚠️ **画像ブリッジ pending 424 → 478（+54/日で3日一定）** | failed 235・delivered 0 は据え置き。**+54/日で増え続けるので、放置すると1ヶ月で約2,100件** |
| **N6** | 🟢 **aiseki が2日連続で動いた** | 09-14 13:59 までに3コミット（`b264255` Cookie の sessionid 検知 / `9eb3099` DM スレッド判定を `/direct/t/` に限定 / `87e3a84` 非公開アカウントの理由表示）。**Instagram DM worker が実運用フェーズに入っている**（HANDOFF §37 に本送信1通の結果を記録） |
| **N7** | ⚠️ **未コミット件数は測定中に増え続ける** | 本タスク中に 58 → 62 件（M 34 + ?? 28）。backend が稼働中で `data/scenarios/` `data/trends/` を書き続けるため。**件数は必ず計測時刻とセットで記録すること** |
| **N8** | ℹ️ **`clip-animal` だけ `hard_constraints` 未設定** | 他12chは設定済み。停止中なので実害は無いが、再開時に無検査で走る |

---

## 4. ユーザー手動待ちタスク

### 🚨 今すぐ（09-15〜09-19 に必ず）— この順番で

1. **GCP OAuth 同意画面を「テスト中」→「本番」に公開**（`https://console.cloud.google.com/auth/audience` / project 844705815004）
   → **残り 5.57日。09-20 前後に稼働6chが一斉に落ちる。落ちたら公開もアナリティクスも全停止。** これが最優先。
2. **YouTube Studio で 3ch のアカウント確認（電話番号）** — `company-facts` / `scp-lab` / `yokai-watch`
   → `youtube.com/verify`。daily-science と socio-rx は既に通っているので **残りはこの3chだけ**。やるまで、この3chの全動画がデフォルトサムネのまま。
3. **`ANTHROPIC_API_KEY` を新しいキーに差し替える** — 現在のキーは401（無効）。`backend/.env` 18行目。
   → これが直るまで、Claude 分析・dual scenario gen・`viral_translation_pending` 17件の処理はすべて止まったまま。

### 判断が要るもの

4. 残7chの OAuth 再認可をどこまでやるか（**続ける ch を決めてから**。今の7chは登録者数すら測れない）
5. 切り抜き4chを畳むか（全停止・OAuth全失効・測定不能）
6. fake-paper を止めるか作り直すか（現在OFF・測定不能）
7. `orch-20260911-followup` のマージ方針（4日放置。main 側＝エントリ削除済みの採用が妥当に見える）
8. **N3: 「`title_constraints.ok:false` なら公開しない」分岐を入れるか**（入れると公開本数が減る。今日の18本中1本が該当）
9. **N2: `title_gate_ok` を実装するか、監視項目から外すか**
10. oripa `feat/stripe-checkout` を main へマージするか（**9コミット先行・0遅れ＝コンフリクト無しでマージできる**・34日放置）
11. N14: youtube-factory の push 先を `origin` / `neworigin` のどちらに一本化するか（neworigin は68先行）

### 環境の掃除（Mac 側でないと消せない）

```bash
cd ~/Developer/youtube-factory
rm -f .git/*.lock .git/refs/heads/*.lock
rm -rf .git/stale_locks .git/_stale*                 # 78件
find .git/objects -name 'tmp_obj_*' -delete          # 1,215件
git gc --prune=now
# logs/backend.log = 85,605,908 バイト（+1.44MB/日）のローテーション
pytest backend/tests                                  # 4日間サンドボックスで測れていない
```

### aiseki（公開前）

12. **Twilio 本番アップグレード** / **Instagram ログイン**（`cd worker && npm run login`）/ `dm_targets` の CSV 取り込み / SNSアカウント（@aisekimatch）開設 / live で1回購入して確認 / サインアップの CAPTCHA
13. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
14. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

### ai-english-coach

15. **GitHub リモートの作成と push** — 最終コミット 09-08 でローカルのみ＝バックアップ無し
16. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通

### その他

17. ChatGPT スレッドURLを13ch分登録 / `REDDIT_CLIENT_ID` の設定
18. 画像ブリッジ pending **478**（+54/日）/ failed 235 の処理方針
19. oripa サイトの本文が空（2日連続）— ビルド失敗かルーティングの問題を確認
20. fanup 未追跡25件 / rhythm-pop 未コミット19件の整理（任意）

---

## 5. 次回（09-15）に確認すること

- **🚨 OAuth の残日数**（今日 5.57日 → 明日 4.57日のはず。同意画面を本番公開していれば数値の挙動が変わる）
- **サムネ403が company-facts / scp-lab / yokai-watch で止まったか**（電話認証を実施した場合）
- **09-13公開7本の初回実績** — **ラグ2日なので 09-15 の fetch で初めて views が入る。ここが「5ch集中運用」の最初の判定点**
- **`ANTHROPIC_API_KEY` の401が消えたか** / **`viral_translation_pending` が17件から減ったか**
- **`channel_metrics` が 09-11 から進み、`subscribers_gained` がゼロでなくなったか**
- **公開本数**（09-14 は18本／JST。**必ず +9h してから日付を切る**）
- **キュー適合率**（今回 **84.0%＝226/269**、`min_effective_chars`/`require_any_of` 除外。全規則なら 58.7%。**次回も同じ2規則を除いて比較すること**）
- **画像ブリッジ pending**（478 → +54/日の傾きが続くか）
- **N3 の分岐**（`ok:false` のまま公開された本数。今日は1本）
- **09-16**: 「実は」出現率 / **09-19**: scp-lab 週7日化・company-facts 4枠化の効果検証 / **09-20**: 09-09 施策の評価＆**OAuth 失効日**

---

## 6. 計測方法の注意（次回実行者向け）

- 🆕 **`video_status.published_at` は UTC（`Z`）。** 日付を切る前に +9h する。しないと 22:30Z / 23:15Z の公開が前日に入る。
- 🆕 **`title_constraints.check()` / `is_enforced()` にはチャンネルJSON全体を渡す。** `hard_constraints` だけを渡すと常に False。
- 🆕 **キューの題材に `min_effective_chars` と `require_any_of` を課さない。** モジュールの docstring が「題材は最終タイトルではない」と明記している。適合率はこの2規則を除いて出す。
- 🆕 **`title_gate_ok` というキーは `job_queue.json` に存在しない。** 「0件」を報告しても意味が無い。
- 🆕 **未コミット件数は計測中に増える**（backend 稼働中）。**時刻とセットで記録する。**
- 🆕 **`data/reports/latest.md` に登録者数と OAuth 残日数が入っている。** DB には登録者の絶対数が無いので、ここが唯一のソース。ただし **OAuth が生きている ch しか値が入らない。**
- 🆕 **views のラグは約2日。** 「公開したのに views=0」を不具合と読まないこと。判定はスナップショット日 −2日まで。
- **`oauth_tokens.expires_at` で失効判定しない。** 判定は `latest.md` の「OAuth トークン寿命」表か、ログの `invalid_grant` の ch別出現で行う。
- **`data/scenarios/*/archive/*.md` は未公開在庫ではない。** 現役プールは `data/scenarios/*/*.json`（archive外、105件）。
- **`data/job_queue.json` は `raw.get("jobs", raw)` で吸収する。**
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`impressions` 列は窓と整合しない。** CTR は `video_reach_daily` を使う。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge` / `git checkout` は失敗する。判定は `/tmp` へのクローンで行う。lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で退避。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。

---

## 7. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-14.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform）への書き込み・git 操作（push / merge / commit）・config 変更・外部送信は**一切していない。読み取りのみ。**
