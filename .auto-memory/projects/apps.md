# アプリ系プロジェクトの状態

**最終確認: 2026-09-20 23:10 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

> 🟡 **09-20 に動いたのは youtube-factory（2コミット）だけ。aiseki は 09-19 の6コミットから本日0で止まった。**
> 🟢 **youtube-factory / aiseki / client-ops-platform / dispatch-proxy はいずれも ahead 0 ＝ push 済み。**
> ⚠️ **並走 run を実行中に直接観測（8日連続）。** 23時台の cron 3本（nightly-full-progress / daily-project-handoff / vercel-migration-reminder）は同時刻。
>    **マーカーファイル方式は7日連続で効いていない。スケジュール側をずらすしかない。**
> 🔴 **client-ops-platform は2日連続で0コミット。**
> 🔴 **aiseki の判定日が明日（09-21）。** 送信済み24件からの返信・登録がゼロなら DM営業を畳んで投稿＋検索広告へ軸足を移す、と 09-18 に決めてある。
>    **09-19 のDMレポートは 送信0・返信0・pending 0。09-20 のレポートは未生成（`worker/reports/` の最新は `2026-09-19.md`）。**

| プロジェクト | パス | ブランチ | 最終コミット | 本日 | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---:|---|---|
| **youtube-factory** | `~/Developer/youtube-factory` | main | **09-20 `85f8288`** | **2** | 30 | 41 | **0（同期済み）** | — |
| **aiseki（相席）** | `~/Developer/aiseki` | main | 09-19 `c92949a` | **0** | 0 | 0 | **0（同期済み）** | **aisekimatch.com** |
| client-ops-platform | `~/Developer/client-ops-platform` | main | 09-18 `a8974fd` | 0 | 0 | 2 | 0 | Vercel Cron 30分ごと |
| dispatch-proxy | `~/Developer/dispatch-proxy` | main | 09-19 `90675da` | 0 | 0 | 0 | 0 | — |
| ai-english-coach | `~/Developer/ai-english-coach` | main | **09-08 `cd2c8c5`（12日停止）** | 0 | 0 | 0 | 測定不能 | 未デプロイ |
| FanUp | `~/Developer/fanup` | main | **08-31 `2681dfd`（20日停止）** | 0 | 0 | **25** | 測定不能 | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | **08-11 `5c15784`（40日停止）** | 0 | 0 | 1 | 測定不能（**origin/main に9先行**） | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 0 | 1 | 測定不能 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 0 | 10 | 7 | 測定不能 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 0 | 1 | 測定不能 | — |

> ⚠️ 「測定不能」は**現在のブランチに upstream が設定されていない**という意味で、push 済みを意味しない。ORIPA / FanUp / ai-english-coach / ai-orchestrator / rhythm-pop / claude-codex-bridge の6つ。**バックアップが無いものがある。**
> ⚠️ **本番URLは `aisekimatch.com`**（`aiseki-xi.vercel.app` は 08-22 に移行済みの旧URL。タスク定義側が古い。旧URLも同じ画面へ到達する）。

## youtube-factory — 🟢 本日2コミット

- `e89f8aa`(10:35) fix(scripts): 相席マッチのメール基盤を流用するのをやめる
- `85f8288`(18:32) feat(company-facts): ビッグネーム×衝撃数字の題材8件をキューへ再投入
- 🟢 **`orch-20260911-followup` ブランチが消滅（`git branch -a` に無い）。9日続いた未マージ問題は終了。**
- dirty 71件（変更30・未追跡41）はレポート・シナリオ等の自動生成分を含む。ahead 0。

## aiseki（相席）— 🟢 2日連続で稼働。本日は「有料PR → 成果報酬」への方針転換

**本日のコミット（5件）**

- `7053d29` **アフィリエイト座組を「課金トリガー版」で作成**（`marketing_アフィリエイト座組_20260919.md` ＋ 文面）
- `5be9e44` マーケ方針を東京ターゲットへ見直し
- `a4480ab` worker: DMスレッドを開けなかった時もスクリーンショットを残す
- `5e25227` worker: 営業DMのデイリーレポートを追加
- `3c82075` `worker/logs`・`worker/reports` を .gitignore へ

### 🆕 事業方針の変更（記録しておくこと）

**固定費のPR発注（商談ベースのタイアップ）はやらない。成果報酬のみで組む。**
**報酬の発動点は「参加」ではなく「ユーザーのポイント購入＝当社への実入金」。**

理由（実装から逆算した実測）: 参加費 3,800pt はポイント残高から引かれるが、その残高には無償配布分が含まれる。

| 無償ポイント | 額 | 出典 |
|---|---:|---|
| カード登録ボーナス | 5,000pt | `migration_card_bonus.sql` |
| 紹介ボーナス（被紹介側） | 3,800pt | `referral_bonus()` |

**新規ユーザーは最大 8,800pt（＝参加2回分）を1円も払わずに消費できる。**
参加トリガーだと 760円×2＝**1,520円を売上ゼロのまま支払う**ことになる。
**課金トリガーなら現金が入った時にしか報酬が発生し、原資が常に存在する。**

- ポイントパック（`src/lib/packs.js`）: 3,800円/3,800pt ｜ 7,200円/7,600pt ｜ 10,600円/11,400pt ｜ 17,100円/19,000pt ｜ 32,300円/38,000pt
- 参加費 3,800pt/人（`join_fee_per_person()`）、**ホストは 0pt・飲食代0円（課金しない）**

### フェーズ判定（09-18 の見直しから変更なし）

**現在は「ホスト獲得フェーズ」。ゲスト集客と有料PRに金を使う段階ではない。**
実測: `profiles` 8件（09-06 から増えていない）/ **`parties` 1件**（ゲスト集客の解禁ラインは10件）/ `shops` 11件（**全て東京**）。
ターゲットは Tier1 主催者・コミュニティ系 → Tier2 東京の女子会 → Tier3 相席・合コン文脈。
ハッシュタグは関西向け → 東京向けに修正済み（`shops` が全て東京なのに関西へ配信していた）。

### 営業DM（Instagram `aiseki_match`）

- **09-19 実績: 送信0・失敗0・返信0**（累計 sent 24 / pending **0**）。上限 30/日。**pending が 0 なので送る玉が尽きている＝ターゲット収集が止まっているだけで、ツールは壊れていない。**
- 09-18 実績: 送信21・失敗1・返信0。
- **09-20 のレポートは未生成**（`worker/reports/` の最新は `2026-09-19.md`・生成は 09-20 09:00）。日次レポートは `worker/dm_report.mjs` ＋ launchd `com.aiseki.dm-report.plist`。
  日次レポートは `worker/dm_report.mjs` ＋ launchd `com.aiseki.dm-report.plist`。
- 🟡 **判断待ち: `mihokan34`（東京グルメ・2万f）からの初返信。** 凍結した「PR相談」テンプレへの反応で有料タイアップの条件提示を求められている。
  **上記の課金トリガー座組ができたので、これを提示する形で返せる状態になった。**（09-18 は「無償の第一歩を提案」が推奨だった）
- `kanpai_tokyo` / `agamogu` は「DM画面を開けませんでした」で失敗。公開アカウントなので DM受信制限の可能性。次回1度だけ再試行。
- 🔴 **判定日 09-21（明日）**: 送信済み24件からの返信・登録がゼロなら、DM営業は筋が悪いと判断して投稿＋検索広告へ軸足を移す。
  **09-20 23:10 時点で 返信0・登録0。この判定は「畳む」側に倒れる見込み。** ただし pending 0＝ここ2日は1件も送っていないので、
  **「DMが効かない」ではなく「送っていない」状態での判定になる**点は明記しておくこと。判定するなら n=24 の打ち止めとして扱う。

### 残ブロッカー

1. ⛔ **Twilio がトライアルのまま**（`type=Trial`・Balance −0.406 USD）。未検証番号に SMS が届かない。
   **紹介ボーナスの支払いが電話番号認証に依存するので、ここが止まると紹介報酬も止まる。ザキ様の作業。18日連続で未着手。**
2. ⛔ **live で1回購入してポイントが増えることの確認**（実課金が発生する）。**課金トリガーの座組はここが通らないと成立しない。**
3. ⚠ Supabase の custom SMTP が生きているかを PAT で GET する（PAT が手元に無い）。
4. ⚠ 09-01 の `unno@wealthpols.co.jp` の登録が本物なら初の外部ユーザー。`profiles` を見て対応を決める。
5. Tier1→2→3 のターゲット収集・実在確認が「指示待ち」。新テンプレでの DM 再開はその後（1日10件程度に抑える）。

**設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。ホスト側は必ず2名以上（**下限2を1に下げると前提が壊れる**）／
個人間DMを作らない／性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。UIとRLSの両方で担保。
**1日30件・間隔30〜120秒は変えない。「操作がブロックされました」が出たらその日は止める。**
Supabase 新ref `melfyxfvhyknqhruytms`。Git: github.com/zaki21016/aiseki（private）。
🚨 非公開アカウントには送れない／インフルエンサーリストは実在確認が要る（生成リストの13/30が存在しないアカウントだった）。

## client-ops-platform — 🔴 2日連続で0コミット（最終 09-18）

- 最終 `a8974fd`(09-18 21:03) 出所に媒体・グループ名・発言者・日時を機械的に表示する。
- 未追跡2件（`.claude/settings.local.json` / `.triage-scratch/`）は作業用なので放置で可。
- intake-fb の定期実行は launchd 登録済み（毎日 9:05 / 17:05）。
- **ワーカー13本は Cowork 定期タスクとして1つも登録されていない**（09-08 から未解決）。

## FanUp — 🟡 MVP 完了・集客未着手（20日停止）

- サイトは正常（サポーター1,248 / 進行中3件 / 達成8ch を表示。09-19 実測）。
- **未追跡25ファイルが20日放置。**
- 残作業: Stripe / Resend の環境変数投入 → Webhook 本番登録 → 再デプロイ → テストモードE2E。

## ORIPA — 🟡 Phase1 MVP・**サイト本文が空（8日連続・09-13 以降）**

- `oripa-omega.vercel.app` は 200 で到達するが **body が空**。09-13 以降ずっと同じ。
- `feat/stripe-checkout` に居たまま **40日**（origin/main に9先行・0遅れ）。main へのマージ判断が保留。
- **最長リードタイムは古物商許可（審査約40日）。着手が遅れるほど開業日がそのまま後ろへ動く。**

## その他（変化なし）

- **ai-english-coach**: 09-08 で停止・12日。dirty 0 だが **リモート未設定＝バックアップが無い**。未デプロイ。
- **ai-orchestrator**: 08-09 から42日。未追跡1・リモート未設定。**「アーカイブ or 継続」の判断が 08-11 から保留。**
- **rhythm-pop**: 06-22 から90日。変更10・未追跡7・リモート未設定。
- **claude-codex-bridge**: 07-04 から78日。未追跡1・リモート未設定。**同じく判断保留。**
- **dispatch-proxy**: 09-17 init。Claude Code から Fable 5 で起動して全プロジェクトを横断管理するための代用セッション用リポジトリ。

## 共通の制約

- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。
  マージ可否の判定は `/tmp` に `git clone -s` した作業用クローンで行う。`git add` / `commit` / `log` / `status --porcelain` は動く。
  **rename は通る**ので、lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で外せる。
- **push はサンドボックスからできない**（GitHub 認証情報が無い）。ホスト端末で実行が要る。
  **09-20 時点で youtube-factory / aiseki / client-ops-platform / dispatch-proxy はいずれも ahead 0＝push 済み。**
- **`git status` をループで回すときは `git -C <絶対パス>` を使う。** `cd` したまま相対パスで次のリポジトリを見ると2件目以降が全て「gitなし」と誤判定される。
- **`~/.auto-memory/` は接続フォルダ外で読めない（17夜連続）。** 実質の参照先は `youtube-factory/.auto-memory/`。
  タスク定義が指している `project_*.md` 群の役割は、このディレクトリの `projects/youtube_channels.md` と `projects/apps.md` が担っている。
