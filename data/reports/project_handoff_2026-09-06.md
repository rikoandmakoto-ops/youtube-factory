# 全プロジェクト引き継ぎレポート — 2026-09-06

**実行日時**: 2026-09-06 23:15 JST
**前回**: 2026-09-05 23:15
**参照した文脈**: `last_handoff_log.md`(09-05) / `last_merge_log.md`(09-02) / `MEMORY_UPDATE_20260906.md`

> ⚠️ `~/Documents/Claude/.auto-memory/` は接続フォルダ外のため今回も読めず（**10日連続**）。youtube-factory 内の `MEMORY_UPDATE_*.md` で代用した。
> ℹ️ 本レポート実行中（23:00〜）に PDCA/指揮者タスクが並走。`data/reports/2026-09-06/*.json` は `pokemon-lab` まで生成済み、`scp-lab` 以降は未生成。

---

## 0. サマリ — 前回から何が動いたか

| | 件数 |
|---|---|
| 前回「未解決」だった課題 | 13 |
| うち今回 **解決を確認** | 2（+ リポジトリ衛生2件、記録の誤り訂正1件） |
| 継続中 | 11 |
| **NEW（今回新たに検出）** | **2** |

最大の変化は youtube-factory の **リポジトリ衛生の回復**（未コミット 647件 → 96件、未プッシュ 9 → 0）と、
前回 #4 で「次回消えていなければコードを疑う」としていた **scp-lab のクランプ漏れが予想どおり自然解消**したこと。
一方で **サムネA/B のCTRベースラインが再び壊れた**（前回「是正済み」と記録した19件のうち18件がパーセント尺度に戻っている）。

---

## 1. youtube-factory

**ステータス: 🟡 稼働中・要対応**
`/Users/ayukiyamazaki/Developer/youtube-factory` — https://youtube-factory-eight.vercel.app

### 1-1. 投稿状況（09-06）

**合計 26本**（公開 6 / 予約 20）。DB上のエラー・失敗ステータスは **0件**。

| チャンネル | 公開 | 予約 |
|---|---|---|
| scp-lab | 0 | 3 |
| yokai-watch | 0 | 3 |
| fake-paper | 0 | 3 |
| akashic-librarian | 0 | 3 |
| 2ch-matome | 0 | 2 |
| company-facts | 0 | 2 |
| daily-science | 0 | 2 |
| pokemon-lab | 0 | 2 |
| clip-fukada | 2 | 0 |
| clip-lab | 2 | 0 |
| clip-animal | 1 | 0 |
| clip-kaneko | 1 | 0 |

推移: 09-03 12本 → 09-04 25本 → 09-05 33本 → **09-06 26本**。

### 1-2. autopilot 状態

**13ch中12chが `enabled=true`**（`socio-rx` のみ意図的に false）。全チャンネルで枠が発火し、
OAuth トークンは13ch全て本日 15:20 UTC に自動リフレッシュ済み（`invalid_grant` の出現ゼロ）。

**clip-lab は転換ゼロが続く**: 直近30日で 32,551再生 / 登録**+1**。前回（34,743再生・登録0）から
実質変化なし。再生は取れているが登録に落ちていない構造は不変。

### 1-3. チャンネル別 登録者増（直近30日・`channel_metrics` 09-03 時点）

> ⚠️ `channel_metrics` は **2026-09-03 で止まっている**（`video_metrics` は 09-06 分313行を取得済み）。
> 絶対登録者数を持つ列がテーブルに存在しないため、純増（gained − lost）で代替した。

| ch | 再生（30日） | 登録 純増 |
|---|---|---|
| scp-lab | 41,818 | **+34** |
| company-facts | 40,964 | **+29** |
| daily-science | 38,175 | +15 |
| pokemon-lab | 37,154 | +11 |
| yokai-watch | 35,322 | +10 |
| 2ch-matome | 36,597 | +7 |
| clip-kaneko | 20,277 | +4 |
| clip-fukada | 21,242 | +5 |
| akashic-librarian | 5,259 | +2 |
| clip-lab | 32,551 | **+1** |
| fake-paper | 7,030 | +1 |
| clip-animal | 17 | 0 |

再生量がほぼ横並び（3.5〜4.2万）なのに登録が **+34 と +1 で34倍差**。
朝の指揮者分析（`MEMORY_UPDATE_20260906.md`）が指摘した「転換率格差が至上目標の律速」という結論と一致する。

### 1-4. 直近の変更（git log --oneline -5）

```
c51c3de fix: 使い切った元動画が候補枠を食い潰して切り抜きが出せない件を直す
9245aab data: 09-04〜09-05 の実行結果とレポートを記録する
37449ae fix: 画像ブリッジの配送を開通し、機械ゲートの取りこぼしを塞ぐ
e4eef9f fix: 指揮者(09-05)の指摘7件を反映する
a08c70d feat: 画像は 1ch=1スレッド固定にし、OpenAI Images API を削除する
```

- ブランチ: `main` のみ（未マージブランチなし）
- **未プッシュ: 0**（前回9 → 解消）
- **未コミット: 96件**（変更41 / 未追跡55。前回647 → **85%削減**）

### 1-5. 本日のコンフィグ変更（指揮者タスクが朝に適用済み）

- `scp-lab` / `pokemon-lab` / `yokai-watch`: 4行目を「新情報追加型」→「比較・言い換えで自分ゴト化（新情報の追加は禁止）」に変更
- `pokemon-lab`: `total_chars` 175-225 → 170-205
- `yokai-watch`: `theme_queue` からコンセプト外2件を除去し、勝ち筋型5件を先頭に補充
- バックアップ: `data/channels/{scp-lab,pokemon-lab,yokai-watch}.json.bak_pdca_20260906_orch`
- **反証条件: 2026-09-13 に3chの 0.3→0.7減衰pt を再測定。09-06時点（scp 23.6 / pokemon 22.0 / yokai 25.0）を下回らなければ仮説棄却して元に戻す**

### 1-6. 進行中の実験（触ってはいけないもの）

| 実験 | 現状 | 判定日 |
|---|---|---|
| `cta_position` A/B | yokai-watch・pokemon-lab = `end`（介入群） / scp-lab = `after_hook`（対照群）で**継続中・設定は無傷** | **09-11** |
| 尺の対照実験 | 実験群 scp-lab・2ch-matome / 対照群 daily-science・pokemon-lab・yokai-watch | **09-12** |
| 4行目ルール変更 | 本日投入 | **09-13** |
| yokai-watch 投稿時刻 19:00→17:45 | 継続観察 | **09-19** |

---

## 2. aiseki

**ステータス: 🟢 開発は進捗・公開待ち**
`/Users/ayukiyamazaki/Developer/aiseki` — https://aisekimatch.com

### 2-1. 直近の変更

```
a33d809 (09-06 16:55) 紹介ボーナスの量産穴を塞ぎ、SNS投稿用の画像素材とマーケ資料の誤りを直す
af5f442 (09-03 11:08) 広告用LPに料金比較・FAQ・構造化データを足す
e37c670 (09-02 22:25) 招待・DM・電話番号まわりの e2e 検証スクリプトを追加する
0ea61b3 一時デバッグスクリプトと xlsx 資料を .gitignore に足す
cd61e3e DMの自動送信を足す（管理画面からジョブを積み、手元のワーカーが送る）
```

- 本日 `a33d809` で **新規開発が入った**（09-03 以来3日ぶり）
- **未コミット: 2件**（いずれも LibreOffice のロックファイル `.~lock.*.xlsx#`。実質クリーン。前回5 → 改善）
- **未プッシュ: 2コミット**（`a33d809` / `af5f442`）
- 未マージブランチ: なし
- マイグレーション: `supabase/migration_referral_guard.sql` は **適用済み**（HANDOFF §34-c で確認）。未適用マイグレーションは検出されず
- Vercel: HANDOFF に「本番へデプロイした」と本日付で記録あり。本番 `aisekimatch.com` は稼働中の記録

### 2-2. 本日わかったこと（HANDOFF §34）

- **`34-a` マーケ資料の虚偽記載を全て修正**: 「登録で5,000pt」は実際には**カード登録後**にしか付与されない（`handle_new_user()` は残高0で作成）。SNS/DM資料13箇所を「カード登録で5,000pt」へ訂正。景表法リスクを公開前に潰した。LP は元から正しかった
- **`34-c` 紹介ボーナスの量産穴を塞いで本番デプロイ**
- **`34-d` SNS投稿用の画像素材14枚を生成**

---

## 3. ai-english-coach

**ステータス: 🔵 凍結（19日間動きなし）**
`/Users/ayukiyamazaki/Developer/ai-english-coach`

```
a90c4ad (08-18 22:14) docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
6db3262 feat: phase 1 - AI text dialog MVP with Supabase
```

- 最終コミット **2026-08-18**。前回から進捗なし
- 未コミット: 2件（`HANDOFF.md` / `.__perm_test`）
- ブランチ: `main` / `_locktest`
- **⛔ Git リモート未設定が継続**。Vercel未作成・Supabaseクラウド未作成・LINE公式アカウント未作成・LINE Pay未申込。**ローカルのみに存在する = 消失リスクが最も高いプロジェクト**

---

## 4. 全進捗サマリ

| プロジェクト | URL | ステータス | 一行 |
|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 稼働中・要対応 | 09-06 に26本（公開6/予約20）。12ch autopilot 正常。**サムネ403が6夜連続で最優先** |
| aiseki | https://aisekimatch.com | 🟢 進捗あり・公開待ち | 本日 `a33d809` で虚偽記載修正＋紹介穴塞ぎをデプロイ。残るブロッカーは **Twilio本番化** と **Instagramログイン** |
| fanup | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から**6日間変化なし**。未コミット25 / リモート未設定 |
| oripa | https://oripa-omega.vercel.app | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11。`feat/stripe-checkout` は **origin へプッシュ済み**、main へ未マージ9コミット |
| ai-english-coach | （未発行） | 🔵 凍結 | Phase1テキスト版完了・音声課金未着手。**リモート未設定** |
| 切り抜きラボ (clip-lab) | — | 🟡 稼働・**転換ほぼゼロ** | 30日 32,551再生で登録**+1**。20:47 viral枠は API キー未設定で失敗継続 |
| rhythm-pop | — | ✅ 完成済み | 06-22 以降動きなし。未コミット19 / リモート未設定 |
| claude-codex-bridge | — | ✅ 完成済み | 07-04 以降動きなし。未コミット1 / リモート未設定 |

---

## 5. 課題一覧

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

| 前回# | 内容 | 実測 |
|---|---|---|
| 4 | **`success_patterns.json` の scp-lab だけ `avg_view_percentage` 未クランプ（337.05）** | → **67.35**。全12chが 0〜100 に収まり、100超はゼロ件。前回立てた「並走PDCAが scp-lab に未到達だっただけ」という見立てが正しかった。**コードの疑いは晴れた** |
| — | **youtube-factory の未コミット肥大（647件）** | → **96件**（変更41/未追跡55）。未プッシュも 9 → **0** |
| — | **oripa「未プッシュ9コミット」という前回の記録は誤り** | `feat/stripe-checkout` は `origin` へプッシュ済み（未プッシュ0）。9 は **main への未マージ数**。消失リスクは無く、判断待ちなだけ |
| 部分 | clip-fukada の素材ゼロ | 09-06 も 2本公開。3日連続で安定 |

### ❌ 未解決（継続）

| # | 内容 | 種別 | 実測（09-06） |
|---|---|---|---|
| 1 | **サムネイル `thumbnails/set` が HTTP 403**（本人確認未了）。全公開本がサムネ無し | 継続・**最優先**・**6夜連続** | 本日ログ内 **103件**。moviepy系6ch全部で失敗 |
| 2 | `ANTHROPIC_API_KEY` 未設定（`backend/.env` 18行目コメントアウト） | 継続（**6夜連続**） | clip-lab の 20:47 枠が3回試行して中止。依頼書 `viral_1w8he0z.json` が新たに滞留（未処理は計12件） |
| 3 | analytics の `views=0` かつ `impressions>0` | 継続・数は増 | 09-04:7 → 09-05:20 → **09-06:25行**。⚠️ ただし朝の分析で「Analytics の48〜72時間遅延によるもの」と判明済み。**当日公開分が必ず該当するため、投稿本数の増加に比例するのが正常**。破損ではない可能性が高く、次回は 09-04分（7→現在値）が埋まったかで判定すべき |
| 4 | `channel_metrics` が **2026-09-03** 止まり（3日欠測） | 継続・1日前進 | 前回 09-02 → 今回 09-03。`video_metrics` は 09-06 分313行取得済みで、**`channel_metrics` の経路だけ詰まっている**構図は不変 |
| 5 | ChatGPT画像ブリッジのスレッドURLが13ch全て未登録（`threads.json` が `{}`） | 継続 | — |
| 6 | Reddit RSS 429（`REDDIT_CLIENT_ID` が `.env` に無い） | 継続 | 本日ログ内 429 が69回 |
| 7 | GCP OAuth 同意画面が「テスト中」 | 継続・**期限まで3日** | 次の失効は **09-09 前後**。現時点では13ch全てリフレッシュ成功中（本日 15:20 UTC） |
| 8 | サムネA/B が19件すべて `monitoring`、切替ゼロ | 継続 | 判定ロジックが一度も発火していない |
| 9 | clip-lab の転換ほぼゼロ | 継続 | 32,551再生で登録+1 |
| 10 | clip-kaneko「全ての元動画が切り抜き済み」 | 継続 | 本日ログに3回。ただし1本は公開できている（`clips_per_video` 引き上げか元動画追加が要る） |
| 11 | aiseki: Twilio トライアルのまま / DM自動送信の規約リスク | 継続 | 公開前の必須条件 |
| 12 | ai-english-coach: Gitリモート未設定（消失リスク） | 継続・**19日** | — |
| 13 | `~/Documents/Claude/.auto-memory/` が接続フォルダ外で読めない | 継続（**10日連続**） | — |

### 🆕 NEW（今回新たに検出）

| # | 内容 | 根拠 |
|---|---|---|
| **N1** | **サムネA/B の `channel_avg_ctr` が再び壊れた（回帰）** | 前回「19件すべて 0.0145〜0.0337 に是正済み・1以上ゼロ件」と記録したが、現在 **19件中18件が 39.24〜46.46**（＝比率ではなくパーセント尺度）。正しい尺度なのは 08-28 作成の1件（0.0331）のみ。`last_checked_at` は 09-05 18:00 / 09-06 01:00 UTC で、**再チェック処理が書き戻す際にパーセント値を入れている**。つまり一度きりのデータ修復はしたが、**書き込み側のコードは直っていない**。内訳は daily-science 14件・scp-lab 4件。課題#8（切替ゼロ）はこれが原因の可能性が高い |
| **N2** | **aiseki の Instagram DM ワーカーが1通も送れない** | HANDOFF §34-b。`worker/.ig-profile/Default/Cookies` に **`sessionid` が無い＝未ログイン**（残っているのは csrftoken/datr/dpr/ig_did/mid/wd の6つのみ）。加えて本番DBの **`dm_targets` が0件**。実装・Playwright環境・Chromium は揃っているので、**足りないのは人手の2操作だけ**。§33-a の歯止め（1日30件・間隔30〜120秒）は緩めないこと |

---

## 6. ユーザー手動待ちタスク一覧

| 優先 | タスク | 期限・理由 |
|---|---|---|
| **1** | **YouTube 13ch の電話番号確認**（https://www.youtube.com/verify） | サムネ403の唯一の解。6夜連続・本日だけで103件失敗。「サムネ品質最優先」の前提がここで止まっている |
| **2** | **GCP OAuth 同意画面を本番公開**（project 844705815004） | **09-09 期限**（残り3日）。放置すると13ch全ての投稿が止まる |
| 3 | `ANTHROPIC_API_KEY` を `backend/.env` 18行目のコメント解除で設定 | clip-lab の viral 枠が6夜連続停止。滞留12件 |
| 4 | **Twilio を本番アップグレード** | aiseki 公開前の必須条件 |
| 5 | **Instagram にログイン**（`cd worker && npm run login`）＋ `/admin/dm` から送信先CSVを取り込む | **NEW**。両方やらないとDMは0通のまま |
| 6 | ChatGPT スレッドURL を 13ch 分登録（`scripts/image_bridge.py thread set`） | — |
| 7 | `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加 | 10日連続で読めていない |
| 8 | `REDDIT_CLIENT_ID` の設定 | 429継続 |
| 9 | **ai-english-coach の GitHub リモート作成と push** | 19日間ローカルのみ。消失リスク最大 |
| 10 | oripa の `feat/stripe-checkout` を main へマージするか判断（9コミット） | 消失リスクは無い（origin にプッシュ済み）。判断のみ |

---

## 7. 次回（09-07）の実行時に確認すること

- **サムネ403が解消したか**（解消していれば「解決済み」へ移す）
- **N1: `channel_avg_ctr` の書き戻しが直ったか**。次回も18件が39〜46のままなら、**データ修復ではなくコード修正が必要**と確定させる
- `channel_metrics` が 09-03 から前進したか（3日連続で1日ずつしか進んでいない）
- 課題#3 は「09-04公開分の views が埋まったか」で判定する（当日分の0は正常）
- **09-09 前後**: OAuth リフレッシュトークンの失効
- **09-11**: `cta_position` A/B の判定日（scp-lab `after_hook` vs yokai/pokemon `end`）
- **09-12**: 尺の対照実験の評価日。**それまで対照群の尺に触れない**
- **09-13**: 4行目ルール変更の反証日（3chの 0.3→0.7減衰pt を再測定）
- **09-19**: yokai-watch の投稿時刻変更の影響評価

---

## 8. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-06.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge）への書き込み・git 操作（push / merge / commit）・設定変更は**一切していない。読み取りのみ**。
