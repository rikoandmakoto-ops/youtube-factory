# アプリ系プロジェクトの状態

**最終確認: 2026-09-11 23:10 JST**（git の実測。各リポジトリの `HANDOFF.md` が一次情報）

| プロジェクト | パス | ブランチ | 最終コミット | 未コミット | 本番URL |
|---|---|---|---|---:|---|
| aiseki（相席） | `~/Developer/aiseki` | main | 09-08 `1538169` | 0 | **aisekimatch.com**（独自ドメイン・08-22移行） |
| client-ops-platform | `~/Developer/client-ops-platform` | main | 09-08 `b9b84d1` | 4 | Vercel Cron 30分ごと |
| ai-english-coach | `~/Developer/ai-english-coach` | main | 09-08 `cd2c8c5` | 0 | — |
| FanUp | `~/Developer/fanup` | main | 08-31 `2681dfd` | **25** | fanup-rouge.vercel.app |
| ORIPA | `~/Developer/oripa` | **feat/stripe-checkout** | 08-11 `5c15784` | 1 | oripa-omega.vercel.app |
| ai-orchestrator | `~/Developer/ai-orchestrator` | main | 08-09 `052a617` | 1 | — |
| rhythm-pop | `~/Developer/rhythm-pop` | main | 06-22 `1cfde97` | 19 | — |
| claude-codex-bridge | `~/Developer/claude-codex-bridge` | main | 07-04 `eb23d8a` | 1 | — |

## aiseki（最も動いている）

- 本番は **aisekimatch.com**。Supabase は **新ref `melfyxfvhyknqhruytms`**（旧 `tvydtsqirogdxglkoicz` は接続先ではない）。
- Git: https://github.com/zaki21016/aiseki（private）。**origin/main に対し4コミット先行 — push 未完。**
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

- **FanUp: 25ファイルが未コミットのまま 11日放置。** 最後の作業は Stripe クライアントの遅延生成によるビルド修正。
- **ORIPA: `feat/stripe-checkout` に居たまま1ヶ月動いていない。** main へのマージ判断が保留。

## 共通のブロッカー

- **サンドボックスから GitHub へ push できない**（認証情報が無い）。ホストの端末で実行が必要:
  ```
  cd ~/Developer/youtube-factory && git push origin main   # 15コミット先行
  cd ~/Developer/aiseki          && git push origin main   # 4コミット先行
  ```
