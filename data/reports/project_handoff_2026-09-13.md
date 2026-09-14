# 全プロジェクト引き継ぎレポート — 2026-09-13（日）

**実行日時**: 2026-09-13 23:10 JST / **タスク**: daily-project-handoff
**参照した文脈**: `last_handoff_log.md`(09-12 23:10)、`last_merge_log.md`(09-13 22:20)、`.auto-memory/INDEX.md`・`2026-09-10/11/12/13.md`・`projects/apps.md`・`projects/youtube_channels.md`

> **今日は流れが変わった日。** 3日続いた「公開ゼロ」が解除され、13夜連続だった `ANTHROPIC_API_KEY` 未設定と4日連続だった push 失敗が同時に解消した。
> 一方で **autopilot が 13ch 中 8ch で OFF になり、稼働は5chに絞られた**（22:07 のコミット時点では全12ch ON）。これは朝の指揮者が「config は1文字も変えていない」と記録した後の 12:09 JST の変更で、**指揮者以外の手によるもの**。意図的なら問題ないが、本レポートでは NEW として扱う。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ | 前回(09-12)からの変化 |
|---|---|---|---|
| **youtube-factory** | 🟡 **部分復旧** | 09-13 に **7本公開**（09-10 以来3日ぶり）。OAuth は **6ch 再認可 / 7ch 未再認可**。autopilot は **5ch のみ稼働**（12ch→5ch） | 🔴出口封鎖 → 🟡部分復旧 |
| **aiseki** | 🟢 **進捗再開** | 09-13 22:20 に5日ぶりのコミット＋本番デプロイ（LP の「新規登録で5,000pt」誤記修正）。push 済・作業ツリー clean | 🟢停止 → 🟢稼働 |
| **ai-english-coach** | 🔵 凍結（変化なし） | コード最終変更 **08-18＝26日**。Git リモート未設定のまま。未コミット0 | 変化なし |

---

## 2. youtube-factory

### 2-1. ステータス: 🟡 部分復旧

#### ✅ 今日 解決したこと

| 項目 | 前回(09-12) | 今回(09-13) 実測 |
|---|---|---|
| **公開本数** | 0本（3日連続・最終公開 09-10） | **7本**。`video_publish.db` の `video_status` で確認。DB 上の書き込みは **22:41 JST**（再認可の11分後）、`published_at` は本来のスロット時刻（04:00〜10:00Z） |
| **OAuth** | 13ch 全失効 | **6ch 再認可**（09-13 22:30 JST）: scp-lab / company-facts / daily-science / yokai-watch / 2ch-matome / socio-rx。**19時以降のログに出る `invalid_grant` はこの6chには1件も無い**（残7chのみ） |
| **`ANTHROPIC_API_KEY`** | 13夜連続でコメントアウト | **有効化済み**（`backend/.env` 18行目・値はレポートに転記しない） |
| **push** | 4日連続失敗・22コミット先行 | **完了**。22コミットが push 済み。aiseki も 4→0。※23:10 時点で0だったが、**23:1x に別タスクが `89a323e` をコミットしたため 23:20 時点では `origin/main..main` = 1**。なお `neworigin`(rikoandmakoto-ops) 基準では **65コミット先行** — どちらへ push すべきかは未確定 |
| **backend 再起動** | 未実施（cron が旧設定のまま） | **実施済み**。ログに `Autopilot scheduled for scp-lab: sun・mon・…・sat 13:00 JST` が出ており、09-12 に入れた **scp-lab 週7日化・company-facts 12:30枠増設が cron に載った** |
| **`video_metrics`** | 4日欠測（最終 09-08） | **09-13 の行が246件**（6ch分）。`fetched_at` 22:30 JST |
| **未コミット変更** | 51ファイル | **4ファイル**（merge タスクが 09-13 22:20 に4コミットで整理済み） |

#### 🔧 前回レポートの訂正（実測で覆ったもの）

**訂正1 — 「未公開台本857件」は誤り。実際は79件。**

09-13 朝の指揮者メモが「未公開台本857件」としていた数は、`data/scenarios/*/archive/*.md` を数えたもの。このディレクトリには **2026-05月分から**のファイルが入っており（月別: 05月31 / 06月150 / 07月172 / 08月272 / 09月252）、**同じ期間に697本が公開済み**であることから、archive は公開済みを含む生成履歴の保管場所。

実測し直すと:

| 指標 | 件数 |
|---|---:|
| 現役プール（`data/scenarios/*/*.json`・archive 外） | **87** |
| うちタイトルが公開済み動画と一致 | 8 |
| **正味の未公開台本** | **79** |
| （参考）archive 内の `.md` | 877 |

→ **「再認可した瞬間に857件が一気に流れて投稿間隔が壊れる」というリスクは存在しない。** 79件は約1週間分の在庫で、通常運用の範囲。09-13 メモの「857件をそのまま流すな」は取り下げてよい。

**訂正2 — `oauth_tokens.expires_at` で失効判定してはいけない。**

13ch 中 **11ch で `updated_at` = `expires_at` + 28,801秒（8時間1秒）ちょうど**、残り2chも同方向（pokemon-lab +28,802 / akashic-librarian +32,121）。**全13ch で `updated_at` が `expires_at` より8〜9時間あと**になっている。再認可直後の6chも同じで、22:30 JST に更新されたトークンの `expires_at` が 14:30 JST（8時間前）になっている。

→ **このフィールドを現在時刻と比較すると、再認可した直後のトークンまで「失効」と判定される。** 過去レポートの「13ch 全失効」にはこの読み違いが混ざっていた可能性がある。**失効判定は ①`backend.log` の `invalid_grant` の有無 ②実際に公開できたか、の2点で行うこと。**

#### ❌ 未解決（継続）

| # | 内容 | 継続 | 09-13 の実測 |
|---|---|---|---|
| 1 | GCP OAuth 同意画面が「テスト中」（project 844705815004） | 期限超過 | **サンドボックスから確認不能。** テスト中のままなら再認可した6chも **09-20 頃に再失効**する |
| 2 | OAuth 未再認可の残**7ch** | 継続 | pokemon-lab / akashic-librarian / fake-paper / clip-lab / clip-fukada / clip-kaneko / clip-animal。19時以降のログで全件 `invalid_grant` |
| 3 | `channel_metrics` の欠測 | **8日** | 最終 09-10 まで進んだ（前回 09-05）が、**09-06〜09-10 の `subscribers_gained` が全ch 0**・views も 27〜241 と異常に小さい。**登録者数は依然として出せない** |
| 4 | 画像ブリッジ `threads.json` が空 | 継続 | `{}` / delivered 0 / images 0 |
| 5 | `viral_translation_pending` の滞留 | 継続 | **17件**（08-31〜09-12・増減なし）。API キーが入ったので次回処理されるか要確認 |
| 6 | `orch-20260911-followup` 未マージ | **3日** | 3コミット先行。コンフリクト2件（`.auto-memory/INDEX.md` / `data/channels/2ch-matome.json`） |
| 7 | `logs/backend.log` のローテーション未実装 | 継続 | **84,165,524 バイト**（09-12: 82,740,449 → **+1,425,075**） |
| 8 | `tmp_obj_*` / `stale_locks/` の残骸 | 継続 | `tmp_obj_*` **997 → 1,128** / `stale_locks/` **61 → 76** |
| 9 | clip-lab の転換ほぼゼロ | 継続 | 現在 autopilot OFF のため実質凍結 |
| 10 | `test_fixes_20260912.py` の赤4件 | **判定不能** | サンドボックスに pytest が入っていない（`No module named pytest`）。ホスト側でないと測れない |

#### 🆕 NEW（今回はじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨 **autopilot が 13ch 中 8ch で OFF になった** | 09-13 **12:09:35** に `2ch-matome / akashic-librarian / clip-animal / clip-fukada / clip-kaneko / clip-lab / fake-paper / pokemon-lab` の8chが `enabled:false` へ。同時に **socio-rx が `false → true`**。09-12 最終コミット `88d1a18`（22:07）時点では socio-rx 以外の12ch が全て `true` だった。**朝の指揮者メモ（10:17）は「config は1文字も変えていない」と記録しているので、これは指揮者以外の変更。** 効果は即時で、12:09 以降に生成したのは稼働5chのみ（12本→6本に減）。**意図的な絞り込みなら妥当（登録/千 上位ch＋再認可済みch に一致）だが、記録が残っていないので確認が要る** |
| **N2** | 🚨 **サムネ403が「判定保留」から「確定」に変わった** | 09-13 に公開した**7本すべて**でサムネ設定が 403 で失敗。メッセージは `The authenticated user doesn't have permissions to upload and set custom video thumbnails.`（reason: forbidden / domain: youtube.thumbnail）。これは**トークンの問題ではなくチャンネル側の電話番号確認が未了**の典型。→ **YouTube Studio で各チャンネルのアカウント確認（電話番号）を済ませる必要がある。** 3日間「公開0本だから判定できない」としていた件が、公開再開で確定した |
| **N3** | ⚠️ **キュー適合率が 64.1%（248件中 不合格89件）で、稼働中の主力3chに集中** | company-facts 19/24 不合格・yokai-watch 18/24・daily-science 15/18。違反内訳は `min_effective_chars` **55件**（うち18〜19字が**29件**）/ `max_digit_groups` 15 / `require_any_of` 14 / `banned_words` 11。**下限20字の直前で落ちる候補が過半**なので、直すべきは生成側プロンプト（機械 repair は禁止・09-12 の実測どおり） |
| **N4** | ⚠️ **`title_gate_ok` が依然 0件（274件中0）** | **backend 再起動後も付いていない。** 09-12 のコミット `64f919b` で実装したはずの印がディスクに残らない。再起動で cron は更新されたのに印は付かない＝**実装が「キューに書き戻す」経路に入っていない**可能性が高い。「補充の何割が落ちたか」を毎日観測する目的は3日連続で未達 |
| **N5** | ⚠️ **画像ブリッジ pending が 370 → 424（+54/日）** | delivered 0 / failed 235 は据え置き。増加ペースは前日(+74)より鈍化したが滞留は継続 |
| **N7** | ⚠️ **socio-rx が稼働chになったのに `hard_constraints` 未設定** | 09-13 に `enabled:false → true` へ復帰し、当日1本公開した。しかし `title_rules.hard_constraints` が空で **`is_enforced()` が False ＝ タイトル検査が丸ごとスキップされる**。キュー12件が無検査のまま。ゆっくり系なので他7chと同じ `max_chars` / `min_effective_chars=20` を付けるのが筋 |
| **N6** | ℹ️ **09-13 スナップショットの登録/千は 0.582（6ch・246本・188,858再生・110登録）** | 09-08 の 0.377（12ch・351本）より高いが、**母集団が違う（6ch対12ch）ので直接比較しない。** ch別は scp-lab 0.819 / yokai-watch 0.733 / company-facts 0.649 / daily-science 0.640 / 2ch-matome 0.165。**yokai-watch が 0.324→0.733 と大きく上がって見えるが、これも窓が違う（30日窓 vs 当日スナップショット）** |

### 2-2. 直近の変更サマリ（`git log --oneline -5`）

```
d64fb2e chore(reports): daily-merge-all-projects 09-13 の実行ログを更新
3e7e136 ops: 09-13 指揮者タスクのスクリプト・分析レポート・引き継ぎメモを追加
eb07abe chore(data): analytics・originality・CTA履歴・ファクト台帳を 09-13 実行分で更新
2144330 feat(content): 09-13 分の台本・トレンド・socio-rx のプレイリストとシリーズリンクを追加
55ddf39 chore(channels): theme_queue の消化分を反映（company-facts / daily-science / scp-lab / socio-rx / yokai-watch）
```

- **ブランチ**: `main` / 未マージ `orch-20260911-followup`（3コミット）
- **リモート**: `origin`=zaki21016/youtube-factory（**先行1**・23:1x の `89a323e` 分）/ `neworigin`=rikoandmakoto-ops/youtube-factory（**先行65**）。**どちらを正とするか未確定のまま**
- **未コミット**: 4ファイル（`data/analytics/retention_insights.json` / `success_patterns.json` / `data/reports/latest.md` / `pdca_history.xlsx`）※23:10 時点

### 2-3. チャンネル別の現況（13ch）

| ch | autopilot | OAuth | 09-13 生成 | 09-13 公開 | 登録/千 | キュー(合格/不合格) | ゲート |
|---|---|---|---:|---:|---:|---|---|
| scp-lab | ✅ ON | ✅ 再認可 | 2 | **2** | 0.819 | 9 / 13 | 有 min20 |
| company-facts | ✅ ON | ✅ 再認可 | 4 | **2** | 0.649 | 5 / **19** | 有 min20 |
| daily-science | ✅ ON | ✅ 再認可 | 3 | **1** | 0.640 | 3 / **15** | 有 min20 |
| yokai-watch | ✅ ON | ✅ 再認可 | 3 | **1** | 0.733 | 6 / **18** | 有 min20 |
| socio-rx | ✅ **ON**（09-13 に復帰） | ✅ 再認可 | 1 | **1** | — (実績2行) | 検査対象外(12件) | **未設定 ⚠️N7** |
| 2ch-matome | ❌ OFF（09-13 12:09） | ✅ 再認可 | 2 | 0 | 0.165 | 15 / 1 | 有 min20 |
| pokemon-lab | ❌ OFF（09-13 12:09） | ❌ 失効 | 1 | 0 | 0.336※ | 9 / 12 | 有 min20 |
| akashic-librarian | ❌ OFF（09-13 12:09） | ❌ 失効 | 1 | 0 | 0.727※ | 11 / 0 | 有 min20 |
| fake-paper | ❌ OFF（09-13 12:09） | ❌ 失効 | 1 | 0 | 0.000※ | 9 / 0 | 有 min20 |
| clip-lab | ❌ OFF（09-13 12:09） | ❌ 失効 | 0 | 0 | 0.004※ | 29 / 4 | 有（禁止系のみ） |
| clip-fukada | ❌ OFF（09-13 12:09） | ❌ 失効 | 0 | 0 | 0.193※ | 29 / 3 | 有（禁止系のみ） |
| clip-kaneko | ❌ OFF（09-13 12:09） | ❌ 失効 | 0 | 0 | 0.178※ | 34 / 4 | 有（禁止系のみ） |
| clip-animal | ❌ OFF（09-13 12:09） | ❌ 失効 | 0 | 0 | 0.000※ | 検査対象外(14件) | **未設定** |

> ※印は **30日窓（08-10〜09-08）** の値。印なしは **09-13 当日スナップショット**。窓が違うので上下の行を直接比べないこと。
> 「登録者数（総数）」は `analytics.db` にも `data/channels/*.json` にも保存されていない。ダッシュボード側でしか見られない。

### 2-4. 次にやるべきこと（youtube-factory）

1. **N1 の確認** — 8ch の autopilot OFF が意図的か。意図的なら `.auto-memory` に理由を記録する
2. **N2 の対処** — YouTube Studio で各chのアカウント確認（電話番号）。これをやるまで全動画がデフォルトサムネで出続ける
3. **GCP OAuth 同意画面を「本番」へ公開** — やらないと再認可した6chも09-20頃に再失効する
4. **残7chの再認可**（続ける ch を決めてから。全部やる必要はない）
5. **N3 の対処** — 生成プロンプト側で実効20字を満たさせる。18〜19字で落ちる29件が最大の塊
6. **N4 の調査** — `title_gate_ok` がキューに書き戻らない経路を特定する
7. **N7 の対処** — socio-rx に `hard_constraints` を付与する（稼働中なのに無検査）

---

## 3. aiseki

### 3-1. ステータス: 🟢 進捗再開

- **5日ぶりにコミットが入った。** `3761e5f`（09-13 22:20:59）— 本番の LP・ランディング・登録フォームに残っていた「新規登録で5,000pt」を「カード登録で5,000pt」に修正し、デプロイ済み。
- `HANDOFF.md` も同日更新され、「§34-a の『LP は元から正しかった』は嘘」と自己訂正が入っている。
- **push 完了**（`origin/main..main` = 0。前回は4コミット先行が5日継続していた）。作業ツリー clean・未追跡0。
- **未マージブランチなし**（`main` のみ）。
- **サイト疎通 OK** — `https://aisekimatch.com` が 200。タイトル・OG・構造化メタまで正常。

### 3-2. 直近の変更サマリ

```
3761e5f 本番の LP・ランディング・登録フォームに残っていた「新規登録で5,000pt」を「カード登録で5,000pt」に直す
1538169 docs: マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加
1d3f26e chore: LibreOffice のロックファイルを .gitignore に追加
a33d809 紹介ボーナスの量産穴を塞ぎ、SNS投稿用の画像素材とマーケ資料の誤りを直す
af5f442 広告用LPに料金比較・FAQ・構造化データを足す
```

### 3-3. マイグレーション

- **`supabase/migrations/` ディレクトリは存在しない。** マイグレーションは `supabase/migration_*.sql` としてフラットに置かれている（20本以上）。適用は `apply_migrations.command` から `scripts/apply_sql.mjs` 経由。
- **`apply_migrations.command` は `.gitignore` 済み**（DBパスワードの保管場所を兼ねる設計）。ただし **Supabase DB パスワードが平文で2箇所**（新ref 用と旧ref 用）に書かれている点は前回から変化なし。**ホスト上のファイルなので流出はしていないが、扱いには注意。**
- **未適用マイグレーションの機械的な判定はできない**（適用済みを記録するテーブルが無く、`.command` が固定3ファイルをループする作りのため）。判定には Supabase への接続が要る＝サンドボックスからは不可。

### 3-4. Vercel デプロイ

- サンドボックスから Vercel API は叩けない。**本番サイトの疎通（200・最新コピー「カード登録で5,000pt」の反映）で間接的に確認**した。HANDOFF の記載どおりデプロイ済みとみなせる。

### 3-5. 前回からの差分 / 次にやるべきこと

**NEW**: なし（新たな課題の検出はゼロ。むしろ1つ解消した）

**継続ブロッカー（公開前に必須・すべてユーザー手動）**

1. **Twilio がトライアルのまま** — SMS認証を本番公開する前にアップグレード必須
2. **Instagram の `sessionid` 未取得** — 営業DMが1通も送れない（`cd worker && npm run login`）
3. `dm_targets` の CSV 取り込み / SNSアカウント（@aisekimatch）開設 / live で1回購入して確認 / サインアップの CAPTCHA
4. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定
5. ⚠️ 営業DMの自動送信は **Meta Platform Terms に反する**。運営判断で稼働中。**ペースの歯止めと停止条件を緩めないこと**

---

## 4. ai-english-coach

### 4-1. ステータス: 🔵 凍結（前回から変化なし）

| 項目 | 実測 |
|---|---|
| ブランチ | `main`（他に `_locktest`・**マージ済みで差分0**） |
| 最終コミット | `cd2c8c5`（**09-08 22:08**）— docs のみ |
| **コードを触った最後のコミット** | `d1af467`（**08-18 22:14**）＝ **26日前** |
| 未コミット変更 | **0** |
| Git リモート | **未設定**（`git remote -v` が空・**26日間ローカルのみ**） |
| 総コミット数 | 8 |

### 4-2. 直近の変更サマリ

```
cd2c8c5 docs: HANDOFF を追加し一時ファイルを .gitignore に追加
a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
```

### 4-3. 前回からの差分 / 次にやるべきこと

**NEW**: なし

1. **GitHub リモートの作成と push**（26日ローカルのみ＝バックアップが存在しない状態）
2. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通（すべて未着手）

---

## 5. 全進捗サマリ（8プロジェクト）

| プロジェクト | URL | ステータス | 実測（09-13 23:10） |
|---|---|---|---|
| **youtube-factory** | https://youtube-factory-eight.vercel.app | 🟡 部分復旧 | サイト200（ログイン画面）。**稼働 5ch / 停止 8ch**。09-13 公開7本。OAuth 6ch再認可・7ch失効。**登録者総数はDBに無くダッシュボードのみ**。登録/千（09-13当日）: scp-lab 0.819 / yokai-watch 0.733 / company-facts 0.649 / daily-science 0.640 / 2ch-matome 0.165 |
| **aiseki** | https://aisekimatch.com | 🟢 開発中・公開前 | サイト200。09-13 コミット＋デプロイ。push済・clean。残タスクは Twilio有料化 / IGログイン / dm_targets 取り込み |
| **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | サイト200（サポーター1,248・進行中3・達成8＝デモデータ）。最終コミット **08-31**＝13日。**未追跡25件**が放置。origin 同期済み |
| **oripa** | https://oripa-omega.vercel.app | 🟡 Phase1 MVP・決済未着手 | **サイトは200だが本文が空**（前回未確認→今回取得成功）。`feat/stripe-checkout` に居たまま **33日**（08-11）。**同ブランチが main より9コミット先行・未マージ**。未追跡1 |
| **ai-english-coach** | — | 🔵 凍結 | Phase1テキスト版完了・音声課金未着手。コード最終変更 **08-18＝26日**。**Gitリモート未設定** |
| **切り抜きラボ（clip-lab 他4ch）** | （youtube-factory 内） | 🔴 **全停止** | clip-lab / clip-fukada / clip-kaneko / clip-animal の**4ch すべて 09-13 12:09 に autopilot OFF**。OAuth も4ch全失効。09-13 の生成・公開ともに0。登録/千 は30日窓で 0.004〜0.193（ゆっくり系の 1/4〜1/200） |
| **rhythm-pop** | — | ✅ 完成済み | 06-22 以降変化なし（83日）。**変更10件＋未追跡7件**・リモート未設定 |
| **claude-codex-bridge** | — | ✅ 完成済み | 07-04 以降変化なし（71日）。未追跡1・リモート未設定 |
| （参考）client-ops-platform | Vercel Cron | 🟢 稼働 | **09-13 22:51 `be5014f`** — 今日も動いている。未追跡2 |

---

## 6. ユーザー手動待ちタスク一覧

### 今すぐ（09-14 朝）— この順番で

1. 🚨 **N1 の確認** — youtube-factory の 8ch autopilot OFF（09-13 12:09）は意図したものか。意図的なら記録を残す／意図外なら戻す
2. 🚨 **GCP OAuth 同意画面を「テスト中」→「本番」に公開**（project 844705815004）。**やらないと再認可した6chも09-20頃に再失効する**
3. 🚨 **YouTube Studio で各チャンネルのアカウント確認（電話番号）** — サムネ403の原因。**09-13 の公開7本すべてがデフォルトサムネのまま出ている**

### 判断が要るもの

4. **残7chの OAuth 再認可をどこまでやるか**（pokemon-lab / akashic-librarian / fake-paper / clip-lab / clip-fukada / clip-kaneko / clip-animal）。**続ける ch を先に決めてから再認可するほうが早い**
5. **切り抜き4chを畳むか**（全停止中・OAuth全失効・30日窓で登録/千 0.004〜0.193）
6. **fake-paper を止めるか作り直すか**（30日窓で登録ゼロ・現在OFF）
7. `orch-20260911-followup` のマージ方針（main側＝エントリ削除済みの採用が妥当に見える。コンフリクトは `.auto-memory/INDEX.md` と `data/channels/2ch-matome.json` の2件）
8. **N3 の対処** — キュー不合格89件のうち `min_effective_chars` 55件（18〜19字が29件）。**生成プロンプト側で直す。機械 repair は禁止**
9. oripa `feat/stripe-checkout` を main へマージするか（**9コミット先行・33日放置**）

### 環境の掃除（Mac 側でないと消せない）

10. `cd ~/Developer/youtube-factory && rm -f .git/*.lock .git/refs/heads/*.lock`
11. `rm -rf .git/stale_locks .git/_stale*` （**stale_locks 76件**）／`find .git/objects -name 'tmp_obj_*' -delete` （**1,128件**）／`git gc --prune=now`
12. `logs/backend.log` **84,165,524 バイト**のローテーション
13. ホストで `pytest backend/tests` を1回流す（サンドボックスに pytest が無く、`test_fixes_20260912.py` の赤4件が3日間確認できていない）

### aiseki（公開前）

14. **Twilio 本番アップグレード** ／ **Instagram ログイン**（`cd worker && npm run login`）／ `dm_targets` の CSV 取り込み ／ SNSアカウント（@aisekimatch）開設 ／ live で1回購入して確認 ／ サインアップの CAPTCHA
15. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済みだが要注意）
16. 実機での動作確認 / 運営体制（通報対応者・営業許可・本店所在地）の確定

### ai-english-coach

17. **GitHub リモートの作成と push**（26日ローカルのみ＝バックアップ無し）
18. LINE公式アカウント / LINE Pay加盟店申込 / Supabase / Vercel / OpenAIキー / Webhook疎通

### その他

19. ChatGPT スレッドURLを13ch分登録 / `REDDIT_CLIENT_ID` の設定
20. 画像ブリッジ pending **424** / failed 235 の処理方針
21. `viral_translation_pending` **17件** — API キーが入ったので処理されるか09-14に確認
22. fanup 未追跡25件 / rhythm-pop 変更10＋未追跡7 の整理（任意）

---

## 7. 次回（09-14）の実行時に確認すること

- **autopilot 5ch 体制が続いているか**（N1 が意図的だったか）
- **公開本数**（09-13 は7本。5ch体制なら1日13本前後が上限）
- **サムネ403が止まったか**（アカウント確認を実施した場合）
- **6chのトークンが 09-14 も生きているか** — 生きていれば「同意画面が本番公開済み」の傍証になる
- **`channel_metrics` が 09-10 から進んだか／`subscribers_gained` がゼロでなくなったか**
- **`title_gate_ok` がキューに付いたか**（3日連続で0件）
- **キュー適合率**（今回 **64.1%＝159/248**。09-12 の 60.5%＝155/256 とは母集団が近いので比較可）
- **`viral_translation_pending` が17件から減ったか**
- **画像ブリッジ pending が424から減ったか**
- **09-15**: 答え提示型100%化の反証期限 / **09-16**: 「実は」出現率 / **09-19**: scp-lab 週7日化・company-facts 4枠化の効果検証 / **09-20**: 09-09 施策の評価
  → **09-13 に公開が再開したので、09-19 の検証は成立する見込み。ただし母集団は5chに縮む。**

---

## 8. 計測方法の注意（次回実行者向け）

- 🆕 **`oauth_tokens.expires_at` で失効判定しない。** 全13件で `updated_at = expires_at + 28,801秒` になっており、再認可直後のトークンも「8時間前に失効済み」に見える。**判定は `backend.log` の `invalid_grant` の ch別出現と、実際の公開成否で行う。**
- 🆕 **`data/scenarios/*/archive/*.md` は「未公開在庫」ではない。** 2026-05月分から入っており公開済みを含む。**現役プールは `data/scenarios/*/*.json`（archive外）**。
- 🆕 **`data/job_queue.json` は読むタイミングで形が変わる。** 本タスク中に `list`（641要素）→ `{"version":…, "jobs":[…]}` に変わった。**必ず `raw.get("jobs", raw)` で吸収すること。**
- 🆕 **サンドボックスに pytest が入っていない。** 回帰テストの本数はホストでしか測れない。
- 🆕 **`video_metrics` の最新スナップショット日は ch ごとに違う**（09-13 は6ch、09-08 が4ch、09-06 が3ch）。全ch合算すると窓の違う数字が混ざる。
- **`title_constraints.check()` は dict を返す**（`{"ok":bool,"violations":[{"rule":…}]}`）。`is_enforced()` / `check()` には **`ChannelProfile` ではなく生の dict** を渡す（属性アクセスすると `AttributeError`、ラッパーを渡すと常に False）。
- **`theme_queue` は `d["autopilot"]["theme_queue"]`**、**`hard_constraints` は `d["title_rules"]["hard_constraints"]`**。
- **ログのサイズはバイト数で記録する**（MiB/MB 混在の再発防止）。
- **実行中に別タスクが同じ repo を書く。** 未コミット件数・キュー件数は**計測時刻とセットで記録すること**。
- `curl` は egress 不可。サイト疎通は `web_fetch` を使う。**URL はタスク定義に載っているものだけ取得できる**（今回は oripa も定義に載っていたため取得できた）。
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。判定は `/tmp` へのクローンで行う。

---

## 9. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-13.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

**他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge / client-ops-platform）への書き込みは一切していない。読み取りのみ。**
**git 操作（push / merge / commit / config 変更）・外部送信も一切していない。**
