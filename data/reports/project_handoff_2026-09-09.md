# 全プロジェクト引き継ぎレポート — 2026-09-09

実行: 2026-09-09 23:15 JST 開始（daily-project-handoff 自動実行）
参照した文脈: `last_handoff_log.md`(09-08) / `last_merge_log.md`(09-08) / `MEMORY_UPDATE_20260909.md`(午前) / `MEMORY_UPDATE_20260909_night.md`(深夜) / `data/reports/全進捗_2026-09-09.md`

> ⚠️ `~/Documents/Claude/.auto-memory/` は接続フォルダ外で読めず（**13日連続**）。`MEMORY_UPDATE_*.md` / `HANDOFF.md` で代用。
> ⚠️ 実行途中でサンドボックスの bash が停止した。**git 情報は停止前に全リポジトリ分を取得済み**（このレポートの git 数値は実測）。
> sqlite の追加集計とログの時系列集計は取れなかった箇所がある（該当箇所に「未確認」と明記）。
> ℹ️ 23:09 に `nightly-full-progress` が並走。同タスクは bash が最初から使えず git 未確認だったため、**本レポートで git 数値を訂正している**（§5）。

---

## 0. 今夜の結論（3行）

1. 🚨🚨 **09-09 の投稿は 1 本のみ**（`daily-science` 11:56 の1本）。前日21本から実質全滅。
   原因は API でもサムネでもなく **レンダリングが150〜800倍遅くなったこと**。ジョブ22件がキューに滞留したまま日付をまたいだ。
2. 🚨 **06:15 の再起動は午前の設定変更より前**だった。投稿枠の変更（scp-lab の枠重複解消・2ch-matome 07:00→09:00・pokemon-lab 19:00→15:00）は**稼働プロセスに入っていない**。
3. ✅ **未プッシュは解消していた**（09-09 01:22 に origin へ push 済み）。youtube-factory の作業ツリーも**クリーン**。前回「未プッシュ6件」は**クローズ**。

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| **youtube-factory** | 🔴 **稼働停止相当** | 09-09 の投稿 **1本**（前日21本）。レンダ遅延でワーカー2本が11時間21分／16時間51分のジョブに占有。ERRORログ0（「遅い」ので検知されず）。作業ツリー**クリーン**・未プッシュ **2件** |
| **aiseki** | 🟢 進捗停止・人手待ち | 09-09 のコミット **0件**。作業ツリー**クリーン**。未プッシュ 4件（origin へは 09-02 以降 push なし）。`migration_referral_guard.sql` は **HANDOFF 上「適用済」＝実質解決**（§4 で格下げ） |
| **ai-english-coach** | 🔵 凍結 | 実装停止 **22日**（最終実装 08-18、最終コミットは 09-08 の docs のみ）。未コミット0。**Git リモート未設定のまま＝消失リスク最大** |
| **fanup** | 🟡 MVP完了・集客未着手 | `2681dfd`(08-31) から **10日間変化なし**。未コミット **25件** |
| **oripa** | 🟡 Phase1 MVP・決済未着手 | 最終コミット 08-11。HEAD は `feat/stripe-checkout`、**main に対し未マージ 9件**。未コミット1 |
| **切り抜きラボ(clip-lab)** | 🟡 稼働・**転換ほぼゼロ** | 30日 42,604再生で登録+2。09-09 は発火3回・**全失敗**。海外バイラル枠は `ANTHROPIC_API_KEY` 未設定で**9夜連続失敗** |
| **rhythm-pop** | ✅ 完成済み | 06-22 以降動きなし。未コミット **19件**・リモート未設定 |
| **claude-codex-bridge** | ✅ 完成済み | 07-04 以降動きなし。未コミット1・リモート未設定 |

---

## 2. youtube-factory

### 2-1. 直近の変更（`git log --oneline -5`・実測）

```
8b2e996 テーマキュー追加: 全7チャンネルの新規シナリオ25件とアーカイブ索引を更新   (09-09 23:15)
302e28c データ更新: 分析・チャンネル設定・オリジナリティ・トレンドを09-09時点に同期
8920bd3 fix: 09-08 深夜PDCAの指摘6件を修正する                                    (09-09 01:22)
22a1e82 data: 09-08 深夜の点検結果とコンフィグ調整を記録する
ffe8440 docs: 全プロジェクトのマージ・整理ログを記録
```

- 作業ツリー: **クリーン（0件）**
- `origin/main` = `8920bd3`（09-09 01:22 更新）→ **未プッシュ 2件**（`302e28c` / `8b2e996`）
- `neworigin/main` は **10件遅れ**（一度も同期していない）
- ブランチは `main` のみ。未マージブランチ **なし**
- `.git` 内の `*.stale.*` ゴミ参照 **38件**（動作影響なし）

### 2-2. チャンネル別 autopilot と 09-09 の実績

| # | チャンネル | autopilot | 投稿枠（JSON） | 09-09 |
|---|---|---|---|---|
| 1 | daily-science | ON | 07:30 / 12:30 / 17:00 | 発火3・**公開1本**（唯一） |
| 2 | scp-lab | ON | 09:00 / 13:00 / 19:00 | 発火2・公開0。**枠重複解消は稼働プロセス未反映** |
| 3 | company-facts | ON | 08:15 / 19:00 / 17:00 | 発火4・公開0 |
| 4 | akashic-librarian | ON | 10:00 / 14:30 / 18:45 | 発火4・公開0。`title_rules` 無し／OAuth失効 |
| 5 | 2ch-matome | ON | 09:00 / 12:15 / 21:00 | 発火4・公開0。**稼働中は 07:00 のまま** |
| 6 | pokemon-lab | ON | 08:30 / 15:00 / 17:00 | 発火2・公開0 |
| 7 | yokai-watch | ON | 12:00 / 09:30 / 17:00 | 発火3・公開0 |
| 8 | fake-paper | ON | 11:00 / 15:30 / 19:30 | 発火3・公開0。`title_rules` 無し／OAuth失効 |
| 9 | socio-rx | **OFF** | 20:00（平日）/ 15:00（土日） | 停止のまま |
| 10 | clip-lab | ON | 11:45 / 17:45 / 20:45(viral) | 発火3・**全失敗**（ffmpeg 1800s TO / yt-dlp 300s TO / APIキー未設定） |
| 11 | clip-fukada | ON | 12:45 / 20:00 | 発火2・**2枠とも ffmpeg 1800s タイムアウト** |
| 12 | clip-kaneko | ON | 08:00 / 14:00 / 20:30 | 発火3・**3枠とも LLMフック生成失敗**（09-08 に解消したはずが再発） |
| 13 | clip-animal | ON | 09:30 / 18:00 | 発火2・**2件とも失敗**。実質停止 |

**投稿本数の推移（`video_publish.db` 実測）**: 09-05 33 → 09-06 30 → 09-07 27 → **09-08 21（確定・後追い増加なし）** → **09-09 1**。

### 2-3. PDCA で検出された課題の対応状況

09-09 午前の指揮者が入れた設定は、**ディスク上に全て残存を確認済み**（深夜の全13ch直読み）。09-08 に発生した「バックエンドによる設定上書き消失」は**再発していない**。

- 全6ch: `banned_words` に「秘密」追加（登録/千再生 0.120 vs 0.527 ＝4.4倍差）
- 全6ch: 99%型フックの禁止 ／ `require_any_of`（答え提示語）の必須化
- 2ch-matome: 「ワイ」「質問ある」禁止 ／ scp-lab: 記録票フォーマット禁止 ／ yokai-watch: 末尾疑問符禁止
- pokemon-lab: `theme_seeds` 23→33本

ゲートが効き始めた時刻も実測済み: 06:15枠は素通り → **11:30枠で「ワイ」発動** → **17:15以降で答え提示語が発動**。
**09-10 が全数判定の初日**（ただし投稿が動くことが前提）。

---

## 3. aiseki

- 直近コミット: `1538169`(09-08 22:08) ← **09-09 は 0 コミット**
- 作業ツリー **クリーン**、ブランチは `main` のみ、**未マージブランチなし**
- **未プッシュ 4件**（`1538169` / `1d3f26e` / `a33d809` / `af5f442`）。`origin/main` の最終更新は **09-02 22:25**
- 本番 `aisekimatch.com`（`aiseki-xi.vercel.app` は旧URL）。**今回はネットワーク検証ができず、疎通は未確認**
- マイグレーション: `migration_referral_guard.sql` は **`HANDOFF.md` 609行目に「✅適用済」**、3017行目にも「適用済み」と明記 → **本番適用は完了しているとみなす**（§4で格下げ）

---

## 4. ai-english-coach

- 直近コミット: `cd2c8c5`(09-08 22:08、docs のみ)。**実装の最終更新は 08-18 ＝ 22日停止**
- 作業ツリー **クリーン**、`main` と `_locktest`（main にマージ済み）
- **`git remote -v` が空 = リモート未設定のまま。22日間ローカルのみ**

---

## 5. 前回（09-08）からの差分

### ✅ 今回 解決を確認（次回「要対応」として報告しないこと）

- **前回#未プッシュ「youtube-factory 6件」→ クローズ。** 09-09 01:22 に `origin` へ push 済み（`origin/main` = `8920bd3`）。現在の未プッシュは**その後に積まれた新規2件**
- **前回N4「未コミット・未プッシュの増加」→ 未コミットは解消。** youtube-factory / aiseki / ai-english-coach の**3リポジトリとも作業ツリーがクリーン**（前回 youtube-factory 2件）
- **前回#14「aiseki `migration_referral_guard.sql` 未適用の疑い」→ 格下げ。** `HANDOFF.md` に2箇所「適用済」と明記。残るのは `apply_migrations.command` への未登録＝**再現手順の欠落のみ**で、本番の機能欠損ではない
- **前回N1「`require_answer_marker` が効かず日本語も壊す」→ ゲート自体は動作を確認。** 11:30枠で「ワイ」、17:15以降で答え提示語の発動を実測。ただし**充足率の全数判定は 09-10 に持ち越し**（09-09 は公開1本で母数が無い）
- **09-08 の「バックエンドが設定を上書きして消す」→ 再発なし。** 全13ch 直読みで午前の変更が残存
- **サムネ403 → 09-09 は 0回。** ただし**アップロードが1本しかないから発生していないだけ**で、本人確認は未了。**解決ではない**

### ❌ 未解決（継続）

| # | 内容 | 種別 | 09-09 の実測 |
|---|---|---|---|
| 1 | **`ANTHROPIC_API_KEY` 未設定**（`backend/.env` **18行目**がコメントアウト） | 継続・**9夜連続** | clip-lab バイラル枠・clip-kaneko フック生成が同時に失敗中 |
| 2 | **サムネイル `thumbnails/set` の HTTP 403**（本人確認未了） | 継続・**9夜連続** | 今夜は0回だが投稿が止まっているため。未解決 |
| 3 | **OAuth 4ch失効**（clip-animal / socio-rx / fake-paper / akashic-librarian） | 継続 | 分析不能のまま |
| 4 | **GCP OAuth 同意画面が「テスト中」**（project 844705815004） | 継続・**期限超過** | 失効予定日 09-09 を過ぎた |
| 5 | `channel_metrics` の詰まり | 継続 | 今回は sqlite 集計ができず**未確認**。前回は 09-05 止まり・9chのみ |
| 6 | 画像ブリッジのスレッドURL未登録（`threads.json` が `{}`） | 継続 | 今回は件数を**未確認**。前回 failed 235件 |
| 7 | clip-lab の転換ほぼゼロ | 継続・悪化 | 42,604再生で登録+2 |
| 8 | clip-animal 実質停止（OAuth失効＋素材枯渇） | 継続 | 公開0本。autopilot は ON のまま |
| 9 | aiseki: Twilio トライアルのまま / Instagram DM ワーカー未ログイン | 継続 | 変化なし |
| 10 | **ai-english-coach: Git リモート未設定** | 継続・**22日** | `git remote -v` が空 |
| 11 | `~/Documents/Claude/.auto-memory/` が読めない | 継続・**13日連続** | — |
| 12 | `.git` の `*.stale.*` ゴミ参照 | 継続 | youtube-factory **38件** |

### 🆕 NEW（前回レポート以降にはじめて検出）

| # | 内容 | 判断材料 |
|---|---|---|
| **N1** | 🚨🚨 **レンダリングが150〜800倍遅くなり投稿がほぼ全滅** | 09-08 は `4.83it/s`（毎秒4.83フレーム）→ 09-09 は `20〜162 s/it`。23:45時点で2本が **11時間21分 / 16時間51分**経過。ワーカー2本が占有され `📥 Job queued` **22件が全件滞留**。**ERROR ログは0件**で既存監視に一切かからなかった |
| **N2** | 🚨 **06:15 の再起動が設定変更より前だった＝JSON と APScheduler が乖離** | 再起動直後のログに `2ch-matome [slot 0]: 07:00 JST`。ディスクは 09:00。scp-lab の旧6枠（idx 3,4,5）も残存の可能性 |
| **N3** | 🚨 **`job_queue.json` の永続化が壊れている（78回）** | `JobQueue persist failed: [Errno 2] ... job_queue.json.tmp -> job_queue.json`。**再起動すると滞留中の22件が消える** |
| **N4** | 🚨 **`daily-pdca-report` が 09-09 に実行されていない** | `lastRunAt` が 09-08 23:33 のまま `nextRunAt` が 09-10 へ飛んだ。`success_patterns.json` / `retention_insights.json` は 09-08 23:20 で停止。`vercel-migration-reminder` も同様に1回飛んでいる |
| **N5** | ⚠️ **N1 の原因仮説に反証がある — 「フレームごとの画像生成」説は静的読みでは支持されない** | `generate_illustration` / `generate_pillow_illustration` の呼び出しは**全て `make_frame` の外**（`plans` ループ・4054/4091/4095/3832/3840行）で、**全て `cache_dir` を渡している**。`make_frame` の中身は `self._get_bg_frame(t)` → `Image.alpha_composite` のみ。<br>**代替仮説**: `_get_bg_frame` は `bg_video` がある時だけ `self.bg_video.get_frame(t % duration)` を呼ぶ。**modulo でフレームごとに後方シークが起きるため、背景動画が長尺・高解像度だとこの桁の悪化が説明できる。**「背景が静止画のジョブは速く、背景動画のジョブだけ遅い」かどうかをまず確認すべき |
| **N6** | ⚠️ **fanup / rhythm-pop の未コミットが放置されたまま** | fanup **25件**・rhythm-pop **19件**。rhythm-pop はリモート未設定なので消失リスクあり |

---

## 6. 次にやるべきこと（プロジェクト別）

### youtube-factory — 09-10 朝、この順で

1. 🚨🚨 **レンダ遅延の切り分け** — まず `logs/backend.log` で「遅いジョブが背景動画ありか静止画か」を確認（N5）。
   並行して `git show 8920bd3 -- backend/pipeline/video_generator.py backend/pipeline/pillow_illustration.py` の差分を読む。
2. 🚨 **`job_queue.json` の永続化を先に直すか、滞留22件を捨てる前提にするかを決める**（N3）。再起動すると消える。
3. 🚨 **バックエンド再起動** — これで設定変更（枠3件）が初めて稼働プロセスに入る（N2）。
4. 🚨 **`ANTHROPIC_API_KEY` を有効化**（`backend/.env` 18行目のコメントを外すだけ）。clip-lab バイラル枠と clip-kaneko フック生成が同時に復旧する。
5. `git push origin main`（2件）。`neworigin` にも揃えるなら `git push neworigin main`（10件）。
6. `daily-pdca-report` の cron を点検（2日連続で飛んだら設定見直し）。

### aiseki

1. `git push origin main`（4件・09-02 以降 push なし）。
2. Twilio 本番アップグレード ／ Instagram ログイン（`cd worker && npm run login`）。
3. `migration_referral_guard.sql` を `apply_migrations.command` に登録（**本番適用は済んでいるので優先度は低い**）。

### ai-english-coach

1. **GitHub リモートを作って push**（22日ローカルのみ・消失リスク最大）。それ以外は凍結継続で問題ない。

### その他

- **oripa**: `feat/stripe-checkout`（未マージ9件）を main に入れるか判断。
- **fanup / rhythm-pop**: 未コミット 25件 / 19件 の整理。rhythm-pop はリモート未設定。
- **clip-animal**: OAuth失効＋素材枯渇で公開0本。**続けるか止めるかの判断**。

---

## 7. 全進捗サマリ（URL・ステータス）

| プロジェクト | URL | ステータス | 補足 |
|---|---|---|---|
| **youtube-factory** | https://youtube-factory-eight.vercel.app | 🔴 稼働停止相当 | 13ch中12ch autopilot ON（socio-rx のみ OFF）。09-09 公開1本 |
| **aiseki** | https://aisekimatch.com | 🟡 人手待ち | 開発は止まっている。残: push / Twilio / Instagram / CAPTCHA |
| **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | 10日間変化なし |
| **oripa** | https://oripa-omega.vercel.app | 🟡 Phase 1 MVP・決済未着手 | `feat/stripe-checkout` が未マージ9件 |
| **ai-english-coach** | （デプロイなし） | 🔵 凍結22日 | Phase 1 テキスト版完了・音声課金未着手。リモート未設定 |
| **切り抜きラボ（clip-lab）** | — | 🟡 稼働・転換ほぼゼロ | 42,604再生で登録+2。バイラル枠は9夜連続失敗 |
| **rhythm-pop** | （ローカル） | ✅ 完成済み | 06-22 以降変化なし。未コミット19 |
| **claude-codex-bridge** | （ローカル） | ✅ 完成済み | 07-04 以降変化なし |

### 30日実績（09-08 時点のスナップショット・OAuth 有効な9ch分）

| チャンネル | 30日再生 | 30日登録 |
|---|---:|---:|
| company-facts | 44,760 | **+30**（最高） |
| clip-lab | 42,604 | +2（最低効率） |
| 2ch-matome | 40,296 | +8 |
| daily-science | 32,585 | +11 |
| clip-kaneko | 23,671 | +4 |
| clip-fukada | 23,664 | +6 |

登録/千再生の1位は **scp-lab 0.795**、下から2番目が **pokemon-lab 0.278**。

---

## 8. ユーザー手動待ちタスク一覧

**今すぐ（09-10 朝）**

1. 🚨🚨 レンダ遅延の切り分けと revert 判断 — **直らない限り投稿は0本のまま**
2. 🚨 バックエンド再起動（滞留22件を捨てる前提か、先に `job_queue.json` を直すか決めてから）
3. 🚨 `ANTHROPIC_API_KEY` を `backend/.env` 18行目のコメント解除で有効化（**9夜連続**）

**期限超過**

4. 🚨 GCP OAuth 同意画面を「テスト中」→「本番」へ公開（project 844705815004）
5. 🚨 失効中4ch の再認可（clip-animal / socio-rx / fake-paper / akashic-librarian）※4のあと
6. 🚨 YouTube 13ch の電話番号確認（youtube.com/verify）— サムネ403の唯一の解・**9夜連続**

**消失リスク**

7. **ai-english-coach の GitHub リモート作成と push**（22日ローカルのみ）
8. push — youtube-factory 2件 / aiseki 4件（サンドボックスに GitHub 認証がなく自動化不可）

**aiseki（公開前）**

9. サインアップの CAPTCHA 実装（紹介ボーナス量産穴）
10. Twilio 本番アップグレード / Instagram ログイン
11. `apply_migrations.command` に `migration_referral_guard.sql` を登録（本番適用済みなので優先度低）
12. ⚠️ `apply_migrations.command` に Supabase の DB パスワードが平文で2箇所（`.gitignore` 済みだが要対処）

**その他**

13. ChatGPT スレッドURLを13ch分登録（`threads.json` が空）
14. `REDDIT_CLIENT_ID` の設定
15. oripa の `feat/stripe-checkout` を main へマージするか判断（未マージ9件）
16. clip-animal を続けるか止めるか判断
17. `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加（**13日連続で読めていない**）
18. fanup 25件 / rhythm-pop 19件 の未コミット整理（任意）
19. `.git` の `*.stale.*` 掃除（任意・youtube-factory 38件）

---

## 9. 次回（09-10）の実行時に確認すること

- **レンダリング速度が戻ったか**（`logs/backend.log` の `it/s`）。戻っていなければ N5 の切り分けから
- **投稿が再開したか。** 09-09 は1本、09-08 は21本
- **再起動されたか。** されていなければ枠の乖離（N2）が続く
- **滞留22件が処理されたか、消えたか**（N3）
- **09-10 は「秘密」「ワイ」「答え提示語」が全数に効く初日** — 投稿が動いていることが前提
- **`daily-pdca-report` が実行されたか。2日連続で飛んだら cron を見直す**
- **`channel_metrics` / 画像ブリッジ件数** — 今回 sqlite が使えず未確認。次回必ず取り直す
- **09-11**: `cta_position` A/B の判定日
- **09-12**: 尺の対照実験の評価日（それまで対照群の尺に触れない）
- **09-13**: 4行目ルール変更の反証日（scp 23.6 / pokemon 22.0 / yokai 25.0 を下回らなければ棄却）
- **09-15**: 答え提示型100%化の反証期限
- **09-16**: 「実は」の出現率が上がったか（上がっていなければ `repair_with` の並べ替えへ）
- **09-19**: yokai-watch の枠移動の影響評価

---

## 10. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-09.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

他プロジェクトへの書き込み・git 操作（push / merge / commit）・設定変更・外部への送信は**一切していない。読み取りのみ**。
