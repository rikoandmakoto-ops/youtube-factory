# メモリ更新差分 — 2026-09-02 深夜（nightly-full-progress）

> ⛔ `~/.auto-memory/` は接続フォルダ外のため**今夜も直接書き込めなかった（4夜連続）**。
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つ。
> **恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。**
> 当面は `youtube-factory/HANDOFF.md` を YouTube Factory のメモリ本体として直接編集している（今夜も編集した）。

---

## 1. project_orchestrator.md / reference_all_projects.md 反映分

- **youtube-factory に Git リモートが設定され push 済み**（2026-09-02）。
  `origin` / `neworigin` とも https://github.com/rikoandmakoto-ops/youtube-factory.git 。
  `origin/main` はローカル HEAD（`5fac080`）と一致。
  → メモリの「Git リモート未設定・バックアップ皆無」という記述は**古い。削除すること**。
  aiseki（github.com/rikoandmakoto-ops/aiseki）・fanup・oripa も同 org にリモートあり。
  **リモートが無いのは `ai-english-coach` / `ai-orchestrator` / `rhythm-pop` の3つだけ**になった。

- 作業ツリーはほぼクリーン（未コミットは `data/analytics/` の2件のみ）。
  「未コミット114件」というメモリの記述も**古い**。

## 2. project_*_channel.md / チャンネル台帳 反映分

`HANDOFF.md` §1 の表を更新した。

| ch | 旧 | 新（09-02 実測） |
|---|---|---|
| `fake-paper` | 最終公開 08-31 / 累計7 | **09-02 / 累計9** |
| `akashic-librarian` | 最終公開 08-31 / 累計7 | **09-02 / 累計9** |
| `clip-lab` | 最終公開 08-27 | 08-27 のまま＝**6日連続ゼロ** |

**09-02 の公開実績: 生成9本 → 公開2本**（`MWdbvHEeNhc` akashic / `UKKWkdWN1MI` fake-paper）。
残り7本は全て「トークン失効のため要再認可」でスキップ。切り抜き4chは別要因で全滅。

直近14日の1本あたり再生（`video_metrics` 最新スナップショット）:

| ch | 本数 | 総再生 | 平均 |
|---|---:|---:|---:|
| **clip-lab** | 7 | 28,955 | **4,136.4** |
| company-facts | 18 | 26,427 | 1,468.2 |
| 2ch-matome | 20 | 16,022 | 801.1 |
| daily-science | 17 | 12,595 | 740.9 |
| pokemon-lab | 16 | 11,784 | 736.5 |
| scp-lab | 24 | 12,357 | 514.9 |
| yokai-watch | 16 | 8,065 | 504.1 |
| fake-paper | 8 | 4,187 | 523.4 |
| akashic-librarian | 8 | 3,599 | 449.9 |

> **記録しておくべき判断材料: 止まっている `clip-lab` が1本あたり再生で断トツ1位**
> （company-facts の約2.8倍）。素材追加の優先度をここまで低く扱ってきたのは実態と合っていない。

## 3. 🚨 OAuth 失効についての新事実（ここが今夜いちばん重要）

09-02 の PDCA（`data/reports/latest.md` 冒頭）で失効/正常が切り分けられた。

| 状態 | ch |
|---|---|
| ❌ 失効 (9) | clip-fukada / clip-kaneko / daily-science / scp-lab / yokai-watch / 2ch-matome / pokemon-lab / company-facts / clip-lab |
| ✅ OK・**残り4.62日** (4) | akashic-librarian / clip-animal / fake-paper / socio-rx |

**正常な4chの残寿命がそろって 4.62日＝GCP 同意画面が「テスト中」のときの7日上限。**
→ **放置すれば 09-07 前後にこの4chも失効し、全13chが止まる。**
→ **再認可だけでは7日おきに再発する。恒久策は GCP 同意画面の「本番」公開**
（https://console.cloud.google.com/auth/audience / project 844705815004）。

`backend/pipeline/credentials/client_secret.json` は依然として存在せず、
アップロード経路は `FileNotFoundError` で落ち続けている（09-02 に5回）。
`backend/pipeline/youtube_oauth.py` と `backend/check_youtube_tokens.py` は 09-02 に更新されているが、未解決。

## 4. データ基盤の落とし穴（新規発見・毎回ここで間違える）

**`video_status` の `published_at` は予約公開だと NULL のまま。**
予約公開（autopilot の通常経路）は `status='scheduled'` / `published_at=NULL` で入る。
そのため `select max(published_at) from video_status` は **08-31 で止まって見える**が、実際には
09-01 の `ryQIYHgujm4` `LJpzN0NJFBw`、09-02 の `MWdbvHEeNhc` `UKKWkdWN1MI` が記録されている。
**日次の公開本数を `published_at` で数えるな。`status` と挿入時刻で見ること。**

あわせて **09-01 09:00 に即時公開できた scp-lab の `iAHGnvpHJwk` は `video_status` に1行も無い**。
即時公開経路の記録漏れが残っている疑い。次に触るとき確認する。

（既存の注意点は据え置き: `video_metrics.views` は累積スナップショット / `impressions`・`ctr` はほぼ使えない /
`channel_metrics` は 08-28〜30 で更新停止）

## 5. コンフィグ変更の記録（09-02 適用分・`MEMORY_UPDATE_20260902.md` と同内容）

`data/channels_orchestrator/*.json` は `data/channels/*.json` への symlink。バックアップは `*.bak_pdca_20260902`。

1. テーマキュー **+37本**（scp-lab **0本＝制作停止**→12 / daily-science 5→13 / pokemon-lab 7→12 /
   yokai-watch 12→16 / company-facts 8→16 / 2ch-matome 18 据え置き）
2. **speed 引き下げ【仮説検証・要追跡】** daily-science・scp-lab・pokemon-lab・yokai-watch 1.3→**1.2** /
   2ch-matome 1.35→**1.25** / company-facts 1.2 据え置き＝**対照群**
3. `short_format.structure` に「答えの遅延」（1行目の問いの答えを5行目まで伏せる）を4chへ追加
4. 2ch-matome の `short_endcard` を登録訴求型へ

**★反証条件（09-05 期限）: 変更した5chの「絶対視聴秒」が改善しなければ speed を元へ戻す
（4ch=1.3 / 2ch-matome=1.35）。判断は AVP ではなく絶対視聴秒で行う。対照群は company-facts。**

なお **2ch-matome は speed 1.35（最速）で AVP 52.4%（2位）＝速度仮説の反例**である点は未解決のまま。

## 6. project_aiseki_lp.md / project_aiseki_new_flow.md 反映分

- **09-02: e2e 検証スクリプト9本（計1,792行）を追加・コミット。** 招待・DM・電話番号・管理画面ゲート・
  本名・フルフロー・ジョブが対象（`.e2e-invite.mjs` ほか）
- **09-02: LP の作り直しに着手（未コミット15件・新規725行）。**
  新規 `lp/faq.js` `lp/seo.js` `lp/socialProof.js` `lp/market.js` `lp/icons.jsx`
  `src/lib/brand.js` `scripts/generate_lp_icons.mjs`、変更 `GuestPage.jsx` `HostPage.jsx` `LpKit.jsx`
  `host.html` `guest.html` `sitemap.xml` `legal.js` `vite.config.js`。
  **未コミットのまま置かないこと**
- `HANDOFF.md`（aiseki）の最新節は §33（09-01 の営業DM自動送信）で、**09-02 分がまだ書かれていない**。
  次に aiseki を触るとき §34 として e2e と LP 改修を追記すること

## 7. 他プロジェクトの状態（09-02 は作業なし）

- **FanUp**: 最終コミット 08-31 / 未コミット25件 / ブロッカーは Stripe・Resend 環境変数のまま
- **ORIPA**: 最終コミット 08-11 / ブロッカーは古物商許可（審査約40日・未着手）
- **ai-english-coach**: 最終コミット 08-18 / リモート未設定 / LINE Pay 加盟店申込が未着手
- **ai-orchestrator**: 最終コミット 08-09 / アーカイブ継続の判断が保留のまま
- **rhythm-pop**: 未コミット19件のまま放置。アーカイブ予定

## 8. 前夜から変わっていない（＝2日連続で止まっている）もの

- OAuth 失効（→3）
- `ANTHROPIC_API_KEY` 未設定 → clip-lab 海外枠が失敗し続け、依頼書が
  `data/analytics/viral_translation_pending/` に **4件**（`viral_1w2l6rn` `viral_1w45v54` `viral_1w4f5op` ほか）
- 切り抜き4ch の素材枯渇（clip-lab 国内 / clip-fukada / clip-animal）
- `socio-rx` の運用可否が未決
- BGM 全ch未設定
- CTA 遵守率の効果測定（09-01 メモの「09-02 以降に取り直す」）は**今夜も未実施**
- 電話認証は daily-science 以外の12chで未完了（fake-paper は 09-02 もサムネ 403）
