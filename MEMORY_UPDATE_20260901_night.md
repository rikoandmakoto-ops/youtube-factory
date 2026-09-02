# メモリ更新差分 — 2026-09-01 深夜（nightly-full-progress）

> ⛔ `~/.auto-memory/` は接続フォルダ外のため今夜も直接書き込めなかった（08-31 / 09-01 昼と同じ、3回連続）。
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つ。
> **恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。** これをやらない限り
> 毎晩この差分ファイルを作るだけになり、メモリ本体は古いままになる。
> 当面は `youtube-factory/HANDOFF.md` を YouTube Factory のメモリ本体として扱っている（今夜も直接編集した）。

---

## 1. reference_all_projects.md / project_orchestrator.md 反映分

チャンネル台帳が実態と食い違っていたので `HANDOFF.md` §1 を全面的に書き換えた。

| 項目 | 旧メモリ | 実際（2026-09-01 実読み） |
|---|---|---|
| チャンネル数 | 8 | **13**（autopilot 有効 12 / 無効は `socio-rx` のみ） |
| 表に無かったch | — | `fake-paper` / `clip-animal` / `socio-rx` |
| `akashic-librarian` | ❌ 停止中 | **✅ 稼働中**（14日で6本・登録者2・平均再生 599.8） |
| `scp-lab` 投稿時刻 | 19:00 | 平日 **09:00 と 19:00 の2枠** / 土日 18:00・19:00 |
| `daily-science` | 18:00 | 平日 **17:00** / 土日 18:00 |
| `yokai-watch` | 18:30 | 平日 **19:00** / 土日 12:00 |
| `2ch-matome` | 17:15 | **18:00**（平日・土日とも） |
| `akashic-librarian` | 18:45 | 平日 18:45 / 土日 **13:45** |
| `clip-kaneko` | 20:30 | **08:00・14:00・20:30 の3枠**（毎日） |

→ 「投稿スケジュールを変えたら §1 の表も直す」というルールを HANDOFF に明記した。

## 2. project_clip_lab_freeze.md / project_clip_channels.md 反映分

**切り抜き4ch（clip-lab / clip-fukada / clip-kaneko / clip-animal）は事実上フリーズしている。**
最終公開は clip-lab の **2026-08-27**。以後5日間ゼロ。原因はch別に別物なので個別に潰す必要がある。

- `clip-lab` 17:45（国内）… ヒカキン素材の未使用区間を使い切った。**素材の追加が唯一の解**
- `clip-lab` 20:45（海外バイラル）… `ANTHROPIC_API_KEY` 未設定。08-31・09-01 とも失敗。
  依頼書が `data/analytics/viral_translation_pending/` に2件溜まっている
- `clip-fukada` … 素材「急にどうした？」で尺条件に合う区間なし。
  ※これは媚薬PR回で本来除外対象の素材。**区間ゲート（`segment_selection.exclude_text_patterns`）は
  意図どおり効いている**ので、これは障害ではなく素材枯渇として扱う
- `clip-kaneko` … 生成は成功したが**アップロードで OAuth 失敗**（下記3）
- `clip-animal` … `clip.sources` が空 ＋ `external_sources` 無効。**一度も成功したことがない**

## 3. 🚨 最優先ブロッカーの格上げ — OAuth 失効は2chではなく全10ch

08-31 / 09-01 昼のメモリには「clip-fukada / clip-kaneko の OAuth が revoked」と書いていたが、
**実際には稼働中の全チャンネルで失敗している**（`logs/backend.log` 集計）:

```
daily-science 40 / scp-lab 27 / yokai-watch 26 / pokemon-lab 26 / company-facts 26
clip-lab 25 / fake-paper 24 / clip-kaneko 17 / akashic-librarian 14 / clip-fukada 13
```

- `backend/pipeline/credentials/client_secret.json` が**存在しない**
- 同ディレクトリの `oauth.db` は **0 バイト**（May 21 作成のまま）
- 一方 `data/youtube_tokens.db`（61KB）は生きており、**投稿経路だけは通っている**
  → 認可情報の置き場が2系統あり、片方が空。ここが根本原因の第一候補

**壊れた時刻: 2026-09-01 11:36〜11:40。** 同日 09:00 の scp-lab は正常に公開できている（`iAHGnvpHJwk`）。
`cta_enforcer` 反映のための 11:40 再起動を挟んだ **17:00 以降の枠から全部失効**。
`backend/pipeline/credentials/` の**ディレクトリ mtime が 09-01 11:36**。ここを最初に疑う。

**実害1 — 09-01 は生成9本のうち3本しか公開できていない:**

| 結果 | ch |
|---|---|
| ✅ 公開/予約 3本 | scp-lab(09:00 `iAHGnvpHJwk`) / akashic-librarian(`ryQIYHgujm4`) / fake-paper(`LJpzN0NJFBw`) |
| ❌ 失効でスキップ 6本 | company-facts / daily-science / pokemon-lab / 2ch-matome / yokai-watch / scp-lab(19:00) |
| ❌ 切り抜き 4ch | 全滅 |

動画自体は生成済みで手元にあるので、**再認可さえ通れば手動で上げ直せる**。

**実害2 — 分析が全部死んだ:** 09-01 23:00 の PDCA レポートは 12ch 中 **9ch が
「登録者ソースが取得できないため判断保留」＋ 0本/0再生**。
数字が出たのは akashic-librarian / fake-paper / 2ch-matome のみ。
`data/analytics/analytics.db` の `channel_metrics` も **08-28〜29 で更新停止**。

> **運用判断としてメモリに残す: この状態の PDCA レポートを根拠にコンフィグを変えないこと。**
> 前日までの実測値のほうが信用できる。09-01 昼の PDCA（高評価率 6.3倍・n=322）は
> まだ有効なので、そちらを判断根拠として使い続ける。

## 4. cta_enforcer の効果測定は依然として未実施

09-01 昼のメモリに書いた「0-b. CTA 遵守率は 09-02 以降に取り直す」は**まだ未実施**。
09-01 に生成された8本は補正後のはずなので、明日 `scripts/verify_cta_20260901.py 2026-09-01` で測れる。
基準値は 高評価37% / 登録36% / 両方19%。

## 5. project_aiseki_dm_tool.md 反映分（新規）

2026-09-01 に **営業DMの自動送信**を実装・コミット済み（`aiseki` main、当日コミット）。
`/admin/dm` からジョブを積むと Mac mini 上の Playwright ワーカー（`worker/dm_worker.mjs`）が
30〜120秒間隔で1件ずつ送る。

> 🚨 **これは Meta Platform Terms に反する**（人の操作を模した自動化）と分かったうえで、
> §29-a の「自動化しない」という結論を運営判断で覆して入れたもの。**アカウント停止リスクは残る。**
> 歯止め3点（1日30件上限 / 30〜120秒の乱数間隔 / 停止条件）は**絶対に緩めない**。
> とくに「操作がブロックされました」が出た日は**その日はもう動かさない**。

手作業の経路（`api/dm/_start.js`）はそのまま残してあるので、自動送信が止まっている間はそちらで進む。

## 6. その他コンフィグ状態の記録

- `2ch-matome` のテーマ重複は 15件（08-31）→ **5件（09-01）に改善**。
  残りの最悪ペアは「ワイ、◯◯歴N年やけど質問ある？」テンプレの相互重複（0.667）。テンプレ側を絞るのが早い
- `socio-rx` は autopilot も `video_format.analytics.enabled` も未設定のまま。運用可否の判断が要る
- BGM が全ch未設定（`data/channels_assets/<channel>/bgm/` が空でログに毎回スキップが出る）
- 残タスク13「akashic-librarian の autopilot 有効化判断」は**決着済み**として消し込んだ
