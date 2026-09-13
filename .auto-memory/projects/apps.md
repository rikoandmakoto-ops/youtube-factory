# アプリ系プロジェクトの状態

**最終確認: 2026-09-13 23:10 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

> 🟢 **09-13 に push が通った。** 09-12 夜に「youtube-factory 22コミット先行 / aiseki 4コミット先行」
> と記録した未 push 分は**すべて解消**（両方とも origin先行 0）。ホスト端末で push された。

| プロジェクト | パス | ブランチ | 最終コミット | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---|---|
| aiseki（相席） | `~/Developer/aiseki` | main | **09-13 `3761e5f`** | 0 | 0 | **0** | **aisekimatch.com** |
| client-ops-platform | `~/Developer/client-ops-platform` | main | **09-13 `be5014f`** | 0 | 2 | **0** | Vercel Cron 30分ごと |
| youtube-factory | `~/Developer/youtube-factory` | main | **09-13 `d64fb2e`** | 4 | 0 | **0** | — |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | 0 | 測定不能 | — |
| FanUp | `~/Developer/fanup` | main | 08-31 `2681dfd` | 0 | **25** | 測定不能 | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | 08-11 `5c15784` | 0 | 1 | 測定不能 | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 1 | 測定不能 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 10 | 7 | 測定不能 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 1 | 測定不能 | — |

> ⚠️ **upstream(origin) が設定されているのは aiseki / client-ops-platform / youtube-factory の3つだけ**（09-12 訂正が今も有効）。
> 残り6つの「測定不能」は **push 済みを意味しない**。upstream を設定するか、リモートの有無自体を確認すること。
> ⚠️ **タスク定義に書かれている `aiseki-xi.vercel.app` は古い。** 本番は **`aisekimatch.com`**（08-22 移行済み）。

## aiseki（最も動いている・09-13 も更新あり）

- **09-13 の変更**: 本番の LP・ランディング・登録フォームに残っていた
  **「新規登録で5,000pt」を「カード登録で5,000pt」へ訂正してデプロイ**（`3761e5f`）。
  HANDOFF §35。**09-06 の「LP は元から正しかった（§34-a）」は誤りだった**と HANDOFF 自身が訂正している。
- 本番は **aisekimatch.com**。Supabase は **新ref `melfyxfvhyknqhruytms`**（旧 `tvydtsqirogdxglkoicz` は接続先ではない）。
- Git: https://github.com/zaki21016/aiseki（private）。**09-13 時点で push 済み・origin先行 0。**
- **設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。
  ホスト側は必ず2名以上（ゲスト側1名は 08-28 に解禁済み。**ホスト側の下限2を1に下げると前提が壊れる**）／
  個人間DMを作らない／性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。
  いずれも UI だけでなく RLS まで含めて担保してある。
- **残ブロッカー（HANDOFF §35-c・09-13 時点で変化なし）**:
  1. **Twilio がトライアルのまま** — SMS認証を本番公開する前にアップグレードが必須。
  2. **Instagram の `sessionid` が未取得** — 営業DMが1通も送れない（`/admin/dm` のジョブが流れない）。
  3. `dm_targets` の投入が未完。
  4. 営業DMの自動送信（Playwright ワーカー、Mac mini 上）は **Meta Platform Terms に反する**。
     運営判断で稼働中。**ペースの歯止めと停止条件を緩めないこと。**

## client-ops-platform

- 09-13 に `be5014f`「Cowork 定期タスクの検証結果を反映し `.env*.local` を無視する」。push 済み。
- 未追跡2件（`.claude/settings.local.json` / `.triage-scratch/`）は作業用なので放置で可。

## FanUp / ORIPA / その他（09-12 から**変化なし**）

- **FanUp: 未追跡25ファイルが13日放置**（最終コミット 08-31、Stripe クライアントの遅延生成によるビルド修正）。
- **ORIPA: `feat/stripe-checkout` に居たまま1ヶ月超動いていない**（08-11）。main へのマージ判断が保留。
- **ai-english-coach / ai-orchestrator / rhythm-pop / claude-codex-bridge も動きなし。**
  rhythm-pop は変更10・未追跡7 が 06-22 から放置。

## 共通の制約

- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。
  `git merge` / `git checkout` は必ず失敗する。マージ可否の判定は `/tmp` に `git clone -s` した
  作業用クローンで行う。`git add` / `commit` / `log` / `status --porcelain` は動く。
- **push はサンドボックスからできない**（GitHub 認証情報が無い）。ホスト端末で実行が要る。
  09-13 時点では**未 push のリポジトリは無い**。
