# アプリ系プロジェクトの状態

**最終確認: 2026-09-12 23:10 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

| プロジェクト | パス | ブランチ | 最終コミット | 変更 | 未追跡 | origin先行 | 本番URL |
|---|---|---|---|---:|---:|---|---|
| aiseki（相席） | `~/Developer/aiseki` | main | 09-08 `1538169` | 0 | 0 | **4** | **aisekimatch.com** |
| client-ops-platform | `~/Developer/client-ops-platform` | main | 09-08 `b9b84d1` | 2 | 2 | 0 | Vercel Cron 30分ごと |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | 0 | **測定不能** | — |
| FanUp | `~/Developer/fanup` | main | 08-31 `2681dfd` | 0 | **25** | **測定不能** | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | 08-11 `5c15784` | 0 | 1 | **測定不能** | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 0 | 1 | **測定不能** | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 12 | 11 | **測定不能** | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 0 | 1 | **測定不能** | — |
| youtube-factory | `~/Developer/youtube-factory` | main | 09-12 `88d1a18` | 4 | — | **22** | — |

> 🆕 **2026-09-12 訂正**: `fanup` / `oripa` / `ai-english-coach` / `ai-orchestrator` /
> `rhythm-pop` / `claude-codex-bridge` は **upstream(origin) が設定されていない**。
> これまで「origin先行 0」と記録していたのは**測定できていなかっただけ**で、
> **push 済みを意味しない**。upstream を設定するか、リモートの有無自体を確認すること。
> upstream があるのは **aiseki / client-ops-platform / youtube-factory の3つだけ**。

## aiseki（最も動いている）

- 本番は **aisekimatch.com**。Supabase は **新ref `melfyxfvhyknqhruytms`**（旧 `tvydtsqirogdxglkoicz` は接続先ではない）。
- Git: https://github.com/zaki21016/aiseki（private）。**origin/main に対し4コミット先行 — push 未完（09-08 から変化なし）。**
- **設計の根幹（絶対に壊さない）**: インターネット異性紹介事業に該当しないこと。
  ホスト側は必ず2名以上（ゲスト側1名は 08-28 に解禁済み。**ホスト側の下限2を1に下げると前提が壊れる**）／
  個人間DMを作らない／性別を参加条件・表示に使わない／20歳以上限定／ランクを性別で分けない。
  いずれも UI だけでなく RLS まで含めて担保してある。
- **ブロッカー**:
  1. **Twilio がトライアルのまま** — SMS認証を本番公開する前にアップグレードが必須。
  2. **Instagram の `sessionid` が未取得** — 営業DMが1通も送れない（`/admin/dm` のジョブが流れない）。
  3. 営業DMの自動送信（Playwright ワーカー、Mac mini 上）は **Meta Platform Terms に反する**。
     運営判断で稼働中。**ペースの歯止めと停止条件を緩めないこと。**

## FanUp / ORIPA

- **FanUp: 未追跡25ファイルが12日放置**（最終コミット 08-31、Stripe クライアントの遅延生成によるビルド修正）。
- **ORIPA: `feat/stripe-checkout` に居たまま1ヶ月動いていない**（08-11）。main へのマージ判断が保留。

## 共通のブロッカー

- **サンドボックスから GitHub へ push できない**（認証情報が無い）。ホストの端末で実行が必要:
  ```
  cd ~/Developer/youtube-factory && git push origin main   # 22コミット先行
  cd ~/Developer/aiseki          && git push origin main   # 4コミット先行
  ```
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可**（EPERM）。
  `git merge` / `git checkout` は必ず失敗する。マージ可否の判定は `/tmp` に `git clone -s` した
  作業用クローンで行う。
