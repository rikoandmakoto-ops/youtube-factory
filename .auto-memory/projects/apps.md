# アプリ系プロジェクトの状態

**最終確認: 2026-09-17 23:15 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

> 🔴 **本日コミットがあったのは youtube-factory（2件・いずれも 12:2x の指揮者 run）だけ。他8リポジトリは全て0。**
> 🔴 **aiseki は本日0コミット。09-16 の §38 コミット以降、実作業が進んでいない（2日連続）。**
> 🔴 **client-ops-platform は 09-15 以降0（3日連続）。FanUp / ORIPA / ai-english-coach / ai-orchestrator / rhythm-pop / claude-codex-bridge は6日連続で完全停止。**
> 🔴 **youtube-factory は origin/main に対し 11コミット先行、さらに未コミット67件（変更32・未追跡35）。**
> **うち `backend/api_channel_autopilot.py` と `backend/channels/channel_manager.py` は
> 「ディスク変更→cron 貼り直し」フックの実装で、YouTube 側の最上位ブロッカーの修正コード。
> コミットも push も再起動もされていない。ホスト端末での作業が要る。**

| プロジェクト | パス | ブランチ | 最終コミット | 本日コミット | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---:|---|---|
| youtube-factory | `~/Developer/youtube-factory` | main | **09-17 `7ebe488` 12:31** | **2** | **32** | **35** | **11（要push）** | — |
| aiseki（相席） | `~/Developer/aiseki` | main | 09-16 `8a64756` 00:09 | **0** | 0 | 0 | 0 | **aisekimatch.com** |
| client-ops-platform | `~/Developer/client-ops-platform` | main | 09-15 `6c65baa` | 0 | 0 | 2 | 0 | Vercel Cron 30分ごと |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | 0 | 0 | 測定不能 | 未デプロイ |
| FanUp | `~/Developer/fanup` | main | **08-31 `2681dfd`（17日停止）** | 0 | 0 | **25** | 測定不能 | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | **08-11 `5c15784`（37日停止）** | 0 | 0 | 1 | 測定不能 | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 0 | 1 | 測定不能 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 0 | 10 | 7 | 測定不能 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 0 | 1 | 測定不能 | — |

> ⚠️ **upstream(origin) が設定されているのは aiseki / client-ops-platform / youtube-factory の3つだけ。**
> 残り6つの「測定不能」は **push 済みを意味しない。**
> ⚠️ **本番URLは `aisekimatch.com`**（`aiseki-xi.vercel.app` は 08-22 に移行済みの旧URL。タスク定義側が古い）。

## aiseki（相席）— 09-17 は完全停止（コミット0・作業0）

- 🔴 **09-17: コミット0・作業ツリーもクリーン（変更0/未追跡0）。実質的な進捗はゼロ。**
  **ブロッカーは 09-15 から3日間1つも動いていない。** 手が止まっているのは技術課題ではなく**着手判断**。
- 09-16: `8a64756`（00:09）で §38 をコミット・push 済み。ahead 0。内容は 09-15 のプロフィール整備。

- 🆕 **09-15: Instagram `aiseki_match` のプロフィール整備を完了（HANDOFF §38・未コミット）。**
  - 手段は **`worker/.ig-profile`（ログイン済み Playwright プロファイル）から `instagram.com/accounts/edit/` を直接操作**。
    **Chrome 拡張（claude-in-chrome）は接続が不安定で使えなかった。**
  - 自己紹介93文字を投入（「グループで飲みに行く相席アプリ / ホストは0円 / DM機能なし / 20歳以上」）。
    **「登録で5,000pt」は書いていない（§34-a の方針）。**
  - プロフィール写真は**暫定**で `public/icon-maskable-512.png`（ネイビー×ゴールドの「A」）。
  - ⚠️ **ウェブサイト欄は Web からは編集不可（モバイルアプリのみ）**。今回は元の値がそのまま残った。
  - ⛔ **残: ChatGPT でのロゴ生成が未了**（chatgpt.com 未ログイン・Chrome 拡張も接続切れ）。**投稿は0件のまま**（素材 `sns_assets/`・文面 `sns_posts.md`）。
- 09-14 の到達点（§37-d）: 確認用 `@c.est_yuichiii` へ**本送信1通成功**。経路は「プロフィールの『メッセージ』ボタン → `/direct/t/<id>/`」。`ig.me` は受信箱に落ちるので使えない。
- 🚨 **非公開アカウントには送れない（§37-e）。** 取り込み時に弾くこと。インフルエンサー17件は全員公開なので本番には当たらない見込み。
- 🚨 **インフルエンサーリスト30件中13件は存在しないアカウントだった（§37-a）。** 取り込み時に実在確認が要る。
- **設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。
  ホスト側は必ず2名以上（**下限2を1に下げると前提が壊れる**。ゲスト側1名は 08-28 解禁済み）／個人間DMを作らない／
  性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。UI と RLS の両方で担保。
- Supabase は新ref `melfyxfvhyknqhruytms`。Git: github.com/zaki21016/aiseki（private）。
- **残ブロッカー**:
  1. ⛔ **Twilio がトライアルのまま**（`type=Trial`・Balance **-0.406 USD**）。未検証番号に SMS が届かない。
     **紹介ボーナスの支払いが電話番号認証に依存するので、ここが止まると紹介報酬も止まる。** SMS認証の本番公開前に有料化が必須。
  2. **営業本番の開始判断（§37-f）。** 確認用2件を対象から外し、1件ずつ積む手順は用意済み。先頭は `1000bero_net`（7.6万）。
  3. **1日30件・間隔30〜120秒は変えない。「操作がブロックされました」が出たらその日は止める（§33-a）。**
     自動送信は Meta Platform Terms に反する。運営判断で稼働中。**ペースの歯止めと停止条件を緩めないこと。**
  4. 🆕 ロゴ生成と SNS 初投稿（上記）。

## client-ops-platform（09-15 が最後・3日連続で0コミット）

- `00bf40f`(00:02) Chatwork のルーム検索 API を追加（クライアント登録の下調べ用）
- `607cc5c`(01:14) クライアントへのチャネル個別登録 API を追加
- `6c65baa`(02:06) **intake-fb の定期実行を launchd に登録（毎日 9:05 / 17:05）**
- 未追跡2件（`.claude/settings.local.json` / `.triage-scratch/`）は作業用なので放置で可。
- ℹ️ 09-08 夜の指摘「ワーカー13本が Cowork 定期タスクとして1つも登録されていない」は、**launchd 側で登録が進み始めた**（intake-fb が初）。

## FanUp / ORIPA / その他（**6日連続で変化なし**）

- **FanUp: 未追跡25ファイルが17日放置**（最終コミット 08-31＝Stripe クライアントの遅延生成によるビルド修正）。
  残作業は Stripe/Resend の環境変数投入 → Webhook 本番登録 → 再デプロイ → テストモード E2E。
- **ORIPA: `feat/stripe-checkout` に居たまま37日動いていない。** main へのマージ判断が保留。
  最長リードタイムは**古物商許可（審査約40日）**なので、**着手が遅れるほど開業日が後ろへ動く。**
- **ai-english-coach**（09-08 で停止・未デプロイ）/ **ai-orchestrator**（08-09）/ **rhythm-pop**（06-22・変更10/未追跡7 放置）/
  **claude-codex-bridge**（07-04）も動きなし。ai-orchestrator と claude-codex-bridge は「アーカイブ or 継続」の判断が 08-11 から保留のまま。

## 共通の制約

- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。
  マージ可否の判定は `/tmp` に `git clone -s` した作業用クローンで行う。`git add` / `commit` / `log` / `status --porcelain` は動く。
  **rename は通る**ので、lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で外せる。
- **push はサンドボックスからできない**（GitHub 認証情報が無い）。ホスト端末で実行が要る。
