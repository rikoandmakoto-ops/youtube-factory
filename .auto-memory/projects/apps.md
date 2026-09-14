# アプリ系プロジェクトの状態

**最終確認: 2026-09-14 23:10 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

> 🟢 **09-14 に aiseki の最大ブロッカーが1つ落ちた。** Instagram の `sessionid` を取得済みで、
> **営業DMの本送信が1通成功**した（確認用アカウント `@c.est_yuichiii`）。「DMが1通も送れない」状態は終了。
> 🟢 push 済み状態は維持（origin 先行 0）。

| プロジェクト | パス | ブランチ | 最終コミット | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---|---|
| aiseki（相席） | `~/Developer/aiseki` | main | **09-14 `87e3a84`** | 0 | 0 | **0** | **aisekimatch.com** |
| client-ops-platform | `~/Developer/client-ops-platform` | main | **09-14 `1d5de13`** | 0 | 2 | **0** | Vercel Cron 30分ごと |
| youtube-factory | `~/Developer/youtube-factory` | main | **09-14 `6acb403`** | 30 | 28 | **0** | — |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | 0 | 測定不能 | — |
| FanUp | `~/Developer/fanup` | main | 08-31 `2681dfd` | 0 | **25** | 測定不能 | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | 08-11 `5c15784` | 0 | 1 | 測定不能 | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 1 | 測定不能 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 10 | 7 | 測定不能 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 1 | 測定不能 | — |

> ⚠️ **upstream(origin) が設定されているのは aiseki / client-ops-platform / youtube-factory の3つだけ。**
> 残り6つの「測定不能」は **push 済みを意味しない**。
> ⚠️ **タスク定義の `aiseki-xi.vercel.app` は古い。** 本番は **`aisekimatch.com`**（08-22 移行済み）。

## aiseki（相席）— 最も動いている

- **09-14 `87e3a84`**: 非公開アカウントでスレッドが開けないときの理由を worker に出すようにした。HANDOFF §37-d〜f。
- **09-14 の到達点（HANDOFF §37-d）**: 確認用アカウント **`@c.est_yuichiii`** へ **本送信1通成功**。
  `dm_targets.status=sent`（`sent_at` 2026-09-14T04:58:36Z）／`dm_jobs` は `done`（送信1・失敗0）。
  **経路は「プロフィールの『メッセージ』ボタン → `/direct/t/<id>/`」**。`ig.me` は受信箱に落ちるので使えない。
- 🚨 **非公開アカウントには送れない（§37-e）**。`ig.me` もプロフィールボタンも受信箱に落ちてスレッドが作られず、
  宛先検索も結果が返らない。**取り込み時に非公開を弾くこと。** インフルエンサー17件は全員公開なので本番には当たらない見込み。
- 🚨 **インフルエンサーリスト30件中13件は存在しないアカウントだった（§37-a）。** 取り込み時に実在確認が要る。
- **本番は aisekimatch.com**。Supabase は **新ref `melfyxfvhyknqhruytms`**。Git: github.com/zaki21016/aiseki（private）。
- **設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。
  ホスト側は必ず2名以上（**ホスト側の下限2を1に下げると前提が壊れる**。ゲスト側1名は 08-28 解禁済み）／
  個人間DMを作らない／性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。UI と RLS の両方で担保。
- **残ブロッカー**:
  1. ⛔ **Twilio がトライアルのまま**（`type=Trial`・Balance **-0.406 USD**）。検証していない番号に SMS が届かない。
     **紹介ボーナスの支払いが電話番号認証に依存するので、ここが止まると紹介報酬も止まる。** SMS認証の本番公開前に有料化が必須。
  2. **営業本番の開始判断**（§37-f）。確認用2件（送信済み・非公開）を対象から外し、1件ずつ積んで様子を見る手順が用意済み。
     先頭は `1000bero_net`（7.6万）。
  3. **1日30件・間隔30〜120秒は変えない。「操作がブロックされました」が出たらその日は止める**（§33-a）。
     自動送信は **Meta Platform Terms に反する**。運営判断で稼働中。**ペースの歯止めと停止条件を緩めないこと。**

## client-ops-platform（09-14 に4コミット・動いている）

- `1d5de13`(22:42) Facebook チャネルの有効化スイッチと intake-fb プロンプトの現行化
- `03f6369`(11:33) Messenger の `aria-label` に付く敬称「さん」を除去
- `e700e04`(10:37) Vercel デプロイの再トリガー
- `7e8a913`(00:40) Messenger のスレッドを名前からクライアントへ自動割り当て
- 未追跡2件（`.claude/settings.local.json` / `.triage-scratch/`）は作業用なので放置で可。

## FanUp / ORIPA / その他（09-12 から**変化なし**・3日目）

- **FanUp: 未追跡25ファイルが14日放置**（最終コミット 08-31、Stripe クライアントの遅延生成によるビルド修正）。
- **ORIPA: `feat/stripe-checkout` に居たまま1ヶ月超動いていない**（08-11）。main へのマージ判断が保留。
- **ai-english-coach / ai-orchestrator / rhythm-pop / claude-codex-bridge も動きなし。**
  rhythm-pop は変更10・未追跡7 が 06-22 から放置。

## 共通の制約

- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。`git merge` / `git checkout` は必ず失敗する。
  マージ可否の判定は `/tmp` に `git clone -s` した作業用クローンで行う。`git add` / `commit` / `log` / `status --porcelain` は動く。
  **ただし rename は通る** ので、`git` の lock は `mv .git/index.lock .git/index.lock.stale_$(date +%s)` で外せる。
- **push はサンドボックスからできない**（GitHub 認証情報が無い）。ホスト端末で実行が要る。09-14 時点で未 push のリポジトリは無い。
