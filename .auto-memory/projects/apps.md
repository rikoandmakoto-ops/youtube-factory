# アプリ系プロジェクトの状態

**最終確認: 2026-09-18 23:20 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

> 🟢 **09-18 は aiseki と client-ops-platform の2つが動いた。6日連続の全面停止から抜けた。**
> 🟢 **youtube-factory は origin と同期済み（ahead 0）＝ 09-17 夜の「11コミット先行・要push」は解消。**
> 🆕 **新リポジトリ `dispatch-proxy` を確認（09-17 23:59 init）。Claude Code から Fable 5 で起動して全プロジェクトを横断管理するための代用セッション用リポジトリ。**
> **本日の YouTube キュー棚卸し（121件隔離）はここ経由（dispatch-proxy-13）で実施されている。**

| プロジェクト | パス | ブランチ | 最終コミット | 本日 | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---:|---|---|
| youtube-factory | `~/Developer/youtube-factory` | main | 09-17 `3e47dcd` 23:38 | 0 | 42 | 40 | **0（同期済み）** | — |
| **client-ops-platform** | `~/Developer/client-ops-platform` | main | **09-18 `a8974fd` 21:03** | **2** | 0 | 2 | 0 | Vercel Cron 30分ごと |
| **aiseki（相席）** | `~/Developer/aiseki` | main | 09-16 `8a64756` 00:09 | **0（未コミット5＋未追跡4）** | 5 | 4 | 0 | **aisekimatch.com** |
| dispatch-proxy | `~/Developer/dispatch-proxy` | main | 09-17 `5feaac5` 23:59 | 0 | 1 | 2 | 0 | — |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | 0 | 0 | 測定不能 | 未デプロイ |
| FanUp | `~/Developer/fanup` | main | **08-31 `2681dfd`（18日停止）** | 0 | 0 | **25** | 0 | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | **08-11 `5c15784`（38日停止）** | 0 | 0 | 1 | **9** | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 0 | 1 | 測定不能 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 0 | 10 | 7 | 測定不能 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 0 | 1 | 測定不能 | — |

> 🆕 **ORIPA の origin先行は「測定不能」ではなく 9 コミットだった**（`feat/stripe-checkout` が origin/main に対し9先行）。09-17 までの記述を訂正。
> ⚠️ 「測定不能」の4つ（ai-english-coach / ai-orchestrator / rhythm-pop / claude-codex-bridge）は upstream 未設定。**push 済みを意味しない。**
> ⚠️ **本番URLは `aisekimatch.com`**（`aiseki-xi.vercel.app` は 08-22 に移行済みの旧URL。タスク定義側が古い）。

## aiseki（相席）— 🟢 3日間の停止から動いた。判断待ちが1件ある

**本日の実績（`worker/` と `marketing_見直し案_20260918.md` の実測）**

- 🟢 **Instagram 初投稿を完了**（ホストカルーセル5枚・Playwright 自動投稿が成功。**以後も同手順で可**）。投稿0件が続いていた状態を脱した。
- 🟢 **DM を本日21件送信**（累計 sent 24 / skipped 1 / failed 2）。日次レポート自動生成を実装（`worker/dm_report.mjs` ＋ `worker/launchd/com.aiseki.dm-report.plist`）。
- 🟢 **マーケ方針を全面見直し**（`marketing_見直し案_20260918.md`・未コミット）:
  - **現フェーズは「ホスト獲得」。ゲスト集客と有料PRに金を使う段階ではない。**
  - 実測: `profiles` 8件（09-06 から増えていない）/ **`parties` 1件**（ゲスト集客解禁ラインは10件）/ `shops` 11件（**全て東京**）
  - **ターゲットを差し替え**: グルメ・せんべろ系レビュー → Tier1 主催者・コミュニティ系 → Tier2 東京の女子会 → Tier3 相席・合コン文脈
  - **ハッシュタグが関西向けだったのを東京向けへ修正**（`shops` は全て東京なのに関西に配信していた）
  - **DMテンプレを差し替え**（「承認制だから変な人は来ません」を削除＝断定的かつ検証不能・景表法グレー／§6の必須表記を追加）
  - **PR相談（有料タイアップ打診）テンプレは `parties` 10件まで凍結**
- 🟡🔴 **★ザキ様の判断待ち: `mihokan34`（東京グルメ・2万f）から初の返信。** 凍結した「PR相談」テンプレへの反応で、
  **有料タイアップの条件提示を求められている。** 現フェーズ（`parties` 1件）でPRに費用は出せないため、
  **「ホストとして会を立てる体験 → 感想を投稿」という無償の第一歩を提案する**方向が推奨されている。未返信のまま保留中。

**残ブロッカー**

1. ⛔ **Twilio がトライアルのまま**（`type=Trial`・Balance −0.406 USD）。未検証番号にSMSが届かない。
   **紹介ボーナスの支払いが電話番号認証に依存するため、ここが止まると紹介報酬も止まる。ザキ様の作業。**
2. **Tier1→2→3 のターゲット収集・実在確認が「指示待ち」。** 新テンプレでのDM再開はその後（1日10件程度に抑える）。
3. **判定日 09-21**: 送信済み24件からの返信・登録がゼロなら、DM営業は筋が悪いと判断して投稿＋検索広告へ軸足を移す。
4. `kanpai_tokyo` / `agamogu` は「DM画面を開けませんでした」で失敗。公開アカウントなので**DM受信制限**の可能性。次回1度だけ再試行。

**設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。ホスト側は必ず2名以上（**下限2を1に下げると前提が壊れる**）／
個人間DMを作らない／性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。UIとRLSの両方で担保。
**1日30件・間隔30〜120秒は変えない。「操作がブロックされました」が出たらその日は止める。**
Supabase 新ref `melfyxfvhyknqhruytms`。Git: github.com/zaki21016/aiseki（private）。
🚨 非公開アカウントには送れない／インフルエンサーリストは実在確認が要る（生成リストの13/30が存在しないアカウントだった）。

## client-ops-platform — 🟢 3日ぶりに再開（本日2コミット）

- `2068191`(14:55) 公式LINEの未割当を解消し、社内グループを除外、タスク削除ボタンを追加
- `a8974fd`(21:03) 出所に媒体・グループ名・発言者・日時を機械的に表示する
- 未追跡2件（`.claude/settings.local.json` / `.triage-scratch/`）は作業用なので放置で可。
- intake-fb の定期実行は launchd 登録済み（毎日 9:05 / 17:05）。

## FanUp / ORIPA / その他（**7日連続で変化なし**）

- **FanUp: 未追跡25ファイルが18日放置**（最終コミット 08-31＝Stripeクライアントの遅延生成によるビルド修正）。
  残作業は Stripe/Resend の環境変数投入 → Webhook本番登録 → 再デプロイ → テストモードE2E。
- **ORIPA: `feat/stripe-checkout` に居たまま38日動いていない（origin/main に9コミット先行）。** main へのマージ判断が保留。
  最長リードタイムは**古物商許可（審査約40日）**なので、**着手が遅れるほど開業日が後ろへ動く。**
- **ai-english-coach**（09-08 で停止・未デプロイ）/ **ai-orchestrator**（08-09）/ **rhythm-pop**（06-22・変更10/未追跡7 放置）/
  **claude-codex-bridge**（07-04）も動きなし。ai-orchestrator と claude-codex-bridge は「アーカイブ or 継続」の判断が 08-11 から保留のまま。

## 共通の制約

- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。
  マージ可否の判定は `/tmp` に `git clone -s` した作業用クローンで行う。`git add` / `commit` / `log` / `status --porcelain` は動く。
  **rename は通る**ので、lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で外せる。
- **push はサンドボックスからできない**（GitHub 認証情報が無い）。ホスト端末で実行が要る。
  ただし **09-18 時点で youtube-factory / aiseki / client-ops-platform はいずれも ahead 0＝push 済み。**
- 🆕 **`git status` をループで回すときは `git -C <絶対パス>` を使う。** `cd` したまま相対パスで次のリポジトリを見ると、
  2件目以降が全て「gitなし」と誤判定される（09-18 に1度踏んだ）。
