# メモリ更新差分 — 2026-09-03 深夜（nightly-full-progress）

> ⛔ `~/.auto-memory/` は接続フォルダ外のため**今夜も直接書き込めなかった（6夜連続）**。
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つ。
> **恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。**
> 当面は本ファイルと `youtube-factory/HANDOFF.md` を YouTube Factory のメモリ本体として扱う。
>
> 全進捗の一覧は `reports/全進捗_2026-09-03.md`。

---

## 1. ★ 朝の「全13ch失効」は誤診だった。OAuth は正常に動いている

`MEMORY_UPDATE_20260903.md` §1 の「残寿命がプラスのチャンネルは1つも無い / 本日以降に生成される
動画は1本も公開されない」は**事実と異なる。削除して以下に置き換えること。**

**実測（09-03 23:20）: 13ch すべてで `oauth_tokens.updated_at` が本日 16:46〜23:13 に更新され、
`video_status` には本日 12本の `video_id` が付与された。** アップロードには有効トークンが必須なので、
これは OAuth が働いている決定的な証拠。23:00 からの日次 PDCA も analytics API を叩き続けている。

### 誤診の原因: `expires_at` は 9時間ずれている（コードで確認済み）

`backend/pipeline/youtube_oauth.py:640` / `:693` / `:832` が
`int(creds.expiry.timestamp())` を書き込んでいる。
**`google.oauth2.credentials.Credentials.expiry` は naive な UTC datetime** であり、
Python は naive datetime を**ローカル時刻**として解釈するため、JST 環境では
**真の有効期限より 32,400 秒（9時間）手前**の値が入る。
`:245` の `save_credentials_for()` がその値を `oauth_tokens.expires_at` にそのまま格納している。
（読み戻しの `:679` `datetime.fromtimestamp(expiry)` も naive ローカルを返すのでモジュール内では
自己整合しているが、google-auth 側は naive を UTC 扱いするため9時間早く「期限切れ」と判断して
先行リフレッシュする。実害はなく、むしろこれのおかげで動いている。）

実測: `scp-lab` は `updated_at`=1788444810（23:13:30）/ `expires_at`=1788416009（15:13:29）で
差が **正確に 28,800 秒（8時間）**。これは「書込時刻 + 3600（アクセストークン寿命） − 32400」に一致する。
**13ch すべてで差が 28,800 秒だった**ので偶然ではない。

> **教訓: `expires_at` をそのまま `now` と比較して失効判定するな。`expires_at + 32400` で比較する。
> 直近9時間以内に発行されたトークンは、この計算を忘れると必ず「失効」に見える。**
> `backend/check_youtube_tokens.py` と PDCA レポートの判定ロジックも同じ疑いがある。要確認。

### ただし恒久対策の必要性は変わらない

リフレッシュトークン自体は GCP 同意画面が「テスト中」の間は 7日で失効し、
**08-24・08-31・09-02 と3回再発している**。次は 09-09 前後。
**本番公開（https://console.cloud.google.com/auth/audience / project 844705815004）は最優先の未着手タスク。**

---

## 2. ★ 切り抜き系で3つの前進があった（メモリのチャンネル台帳を要更新）

| ch | 旧メモリ | 09-03 実測 |
|---|---|---|
| `clip-animal` | 「一度も動いたことがない」累計0 | **初投稿 `EZZqGk4U4-g` 16:55 / 累計1** |
| `clip-kaneko` | 累計0・最終公開 未 | **初投稿 `mz_5-8LG4b8` 14:00 / 累計1** |
| `clip-lab` | 最終公開 08-27・7日連続ゼロ | **`hmwRNtzCMgM` 16:54 / 累計8** |
| `clip-fukada` | 累計0 | 累計0 のまま（3枠すべて失敗） |

### `clip-animal` が動いた理由 = 設定バグの修正

`clip.external_sources.creative_commons.enabled` が true なのに
**親の `clip.external_sources.enabled` が false** だったため、autopilot が毎日
「`clip.sources` が空で `external_sources` も無効です」で落ちていた。
本日 18:30 に `enabled: true` へ修正（バックアップ `clip-animal.json.bak_20260903_clipfix`）。

⚠️ ただし修正直後には「全ての元動画が切り抜き済みです」に変わっている。
**`clips_per_video: 1` なので素材1本＝クリップ1本で即枯渇する。上げるか素材追加が必要。**

### `clip-fukada` の失敗理由は枠ごとに違う（素材が実質ゼロ）

1. 20:00 枠 — 区間ダウンロード失敗（`yjF8W6-BZd4`）
2. 別枠 — 尺条件に合う区間なし（対象は「急にどうした？」＝媚薬PR回。ゲート対象動画）
3. 別枠 — 切り抜ける元動画が見つからない

**切り抜き4ch のうち最も深刻。素材投入の最優先はここ。**

---

## 3. 🆕 本日から新規に発生したブロッカー2件

### OpenAI API の HTTP 429（Too Many Requests）

`clip-kaneko` の 20:30 枠が **フック生成で 429** を受けて失敗した。
`OPENAI_API_KEY` は `backend/.env` に設定済み（164文字）なので、**残高またはレート上限の問題。**
ログの該当箇所:

```
⚠️ GPT でのフック生成に失敗（ヒューリスティックで続行）: HTTP Error 429: Too Many Requests
⚠️ LLM からフック文を得られませんでした（ranked が空）
RuntimeError: 自動字幕由来の素材で LLM のフック生成に失敗しました。壊れたフック文で公開しないため中止します
```

### Reddit RSS の HTTP 429

`clip-lab` 海外バイラル枠の素材探索で、**8サブレディット中6つが 429 で取得失敗**
（r/HolUp / r/funny / r/WatchPeopleDieInside / r/therewasanattempt / r/instant_regret）。
取得できたのは r/unexpected 5件・r/facepalm 2件・r/ContagiousLaughter 0件のみ。
`REDDIT_CLIENT_ID`/`SECRET` が未設定で RSS 経路しか無いため、レート制限を受けやすい。
**素材の質が落ちている。API キーを入れれば解消する。**

---

## 4. `ANTHROPIC_API_KEY` は `.env` にキー自体が存在しない

`backend/.env` の実在キーは以下だけ:

```
API_KEY(空) / APP_PASSWORD / JWT_SECRET / OPENAI_API_KEY / YOUTUBE_API_KEY /
CORS_ORIGINS / PORT / HOST / VOICEVOX_URL / NGROK_AUTHTOKEN(空) / NGROK_DOMAIN(空) / PEXELS_API_KEY
```

**`ANTHROPIC_API_KEY` という行が無い。「未設定」ではなく「未追加」。**
このため clip-lab 海外枠は毎日失敗し、依頼書が
`data/analytics/viral_translation_pending/` に **8件**まで積み上がった
（09-02 時点4件 → 本日4件増: `viral_1w5arwk` `viral_1w5ixxz` `viral_1w5tauy` `viral_1w639x6`）。

---

## 5. ★ テーマキューは2箇所ある（次回ここで必ず間違える）

朝のメモの「テーマキュー +28本」がどこに入ったのかを確認した結果、**キューは2系統ある**ことが判明した。

| 場所 | 消費するコード | 09-03 実測 | 状態 |
|---|---|---|---|
| **`data/channels/<ch>.json` の `autopilot.theme_queue`** | **`api_channel_autopilot._pop_or_refill_theme()`（autopilot の発火経路）** / `trend_scanner` / `comment_demand` | daily-science 18 / scp-lab 15 / 2ch-matome 23 / pokemon-lab 12 / yokai-watch 18 / company-facts 26 | ✅ **毎日の自動投稿はこちらを使う** |
| `data/channels/<ch>/theme_queue.json` | `auto_scenario/theme_queue.py`（`main.py` の **`POST /factory/run` 手動経路のみ**） | daily-science 12 / scp-lab 23 / 2ch-matome 10 / pokemon-lab 7 / company-facts 9 | ⚠️ **autopilot からは呼ばれない。`last_replenished_at` が 06-22〜08-30 のまま。30字超タイトルが多数残存** |

**コードで確認した根拠**: `backend/api_channel_autopilot.py:532` の `_pop_or_refill_theme()` が
`ap.get("theme_queue")` を読んでおり、`data/channels/<ch>/theme_queue.json` には触れていない。
一方 `backend/main.py:1182` の `POST /factory/run`（`use_theme_queue=True`）は
`data/channels/<id>/theme_queue.json` を消費する。
**つまり「死んでいる」のではなく「手動経路専用」。ただし毎日の投稿には一切効かない。**

**実証: 本日生成された5本のタイトルに全て「正体」が入っている**
（`SCP-███ 正体は0秒の無音録音` / `小豆洗いの正体 127年の川音` / `君が知らないシェイミ2形態の正体127` /
`日本マクドナルドの正体、年収670万円の裏側` / `歩き方を意識した3秒で迷う正体`）。
朝に補充したのは前者なので、**前者が生成に効いていることが確認できた。**

> **教訓: テーマを触るときは `data/channels/<ch>.json` の `autopilot.theme_queue` を編集する。
> 同名の `data/channels/<ch>/theme_queue.json` を編集しても、毎日の自動投稿には何も起きない。**

なお **`theme_priority.series_lineup` はテーマではなく「シリーズ名のリスト」**
（`generator.py:322` / `:2833` が参照）。テーマ補充先と混同しないこと。

---

## 6. 🆕 `trend_scanner` が切り抜き4chを除外していない（ゴミデータ）

切り抜きchは元動画から区間を切り出す方式で、**テーマキューを一切使わない。**
にもかかわらず `trend_scanner` と `series_engine` がゆっくり解説用のテーマを流し込んでいる。

| ch | `autopilot.theme_queue` 件数 | 中身の例 |
|---|---:|---|
| `clip-kaneko` | **38** | 「久保建英選手の成功の秘訣！サッカーの科学」「嵐の魅力を科学する！」 |
| `clip-lab` | **37** | 「アベンジャーズ/エンドゲームから学ぶチームワークの科学」 |
| `clip-fukada` | **31** | 「アリアナ・グランデの音楽と心理学」「バーガーキングのクーポン活用法」 |
| `clip-animal` | **14** | 「マックの動物メニュー！？」 |

**完全に無意味なデータで、120件が溜まっている。`trend_scanner` / `series_engine` の
対象chから `style: clip` 系を除外する設定が必要。**

---

## 7. `client_secret.json` 不在は実害を出していない（記述の訂正）

`backend/pipeline/credentials/` の実在ファイルは `api_key.txt`（47バイト）と
空の `oauth.db` だけで、`client_secret.json` は依然として無い。

**ただしアップロードは `data/youtube_tokens.db` の `oauth_tokens` 経由で成立している**
（本日12本が成功）。したがって
「アップロード経路が `FileNotFoundError` で落ち続けている」というメモリの記述は**実態と合っていない。**
`client_secret` 関連のログは本日8件だが、投稿の失敗要因にはなっていない。**優先度を下げてよい。**

---

## 8. ⚠️ 「数字＋単位を必須」ルールの副作用の疑い

本日の生成タイトル2本に**同じ「127」が現れた**:

- `pokemon-lab`: 「君が知らないシェイミ2形態の正体**127**」← 数字が文として意味を持っていない
- `yokai-watch`: 「小豆洗いの正体 **127**年の川音」

09-03 朝に `require_number_with_unit` と `title_style` の「具体数字＋単位」既定を入れた直後の現象。
**LLM が数字を無理に差し込んでいる疑いがある。要調査。**
放置すると「正体」の効果測定（09-08 期限）が壊れたタイトルで汚染される。

---

## 9. コンフィグ現況（09-03 23:20 実読み）

| ch | autopilot | speed | queue | 備考 |
|---|---|---:|---:|---|
| daily-science | ✅ | 1.2 | 18 | speed 検証群 |
| scp-lab | ✅ | 1.2 | 15 | speed 検証群 |
| pokemon-lab | ✅ | 1.2 | 12 | speed 検証群 |
| yokai-watch | ✅ | 1.2 | 18 | speed 検証群 |
| 2ch-matome | ✅ | 1.25 | 23 | speed 検証群 |
| company-facts | ✅ | 1.2 | 26 | **対照群（据え置き）** |
| akashic-librarian | ✅ | 1.15 | **8** | 登録効率1位。キュー最少で次回補充対象 |
| fake-paper | ✅ | 1.3 | 20 | |
| clip-lab | ✅ | 1.0 | 37 | ゴミキュー（→6） |
| clip-fukada | ✅ | 1.0 | 31 | ゴミキュー（→6） |
| clip-kaneko | ✅ | 1.0 | 38 | ゴミキュー（→6） |
| clip-animal | ✅ | 1.0 | 14 | ゴミキュー（→6） |
| socio-rx | ❌ | 1.1 | 4 | 運用可否が未決 |

- BGM は **13ch すべて未設定**（変化なし）
- `analytics.enabled` は socio-rx 以外の12chで true（変化なし）
- 本日の変更バックアップ: `data/channels/*.bak_pdca_20260903b` / `clip-animal.json.bak_20260903_clipfix`
- **未コミット87件**（09-02 は2件）。コンフィグ変更・実行結果・レポートが全部未保存

---

## 10. 反証条件の期限（更新）

- **speed 引き下げ（09-05 期限）→ 判定可能になった。**
  朝のメモは「変更後データが1件も無いので延長」としたが、OAuth は動いており
  `video_metrics` は 09-01〜09-02 分まで取得済み。**09-04 に絶対視聴秒で判定すること。**
  対照群 company-facts（1.2 据え置き）。改善しなければ 4ch=1.3 / 2ch-matome=1.35 へ戻す。
- **「正体」効果の再測定（09-08 期限）** — 本日5本投入で母数は増えた。
  `pokemon-lab` は n=3 と少ないので **pokemon-lab を除く3chでの効果量も併記する。**
  ただし →8 の「127」問題があるので、**壊れた数字を含むタイトルは除外して集計すること。**

---

## 11. 他プロジェクト（09-03 実読み）

### aiseki — https://aiseki-xi.vercel.app（canonical は **`https://aisekimatch.com/`**）

- ✅ **09-03 11:08 に LP 改修をコミット（`af5f442`「広告用LPに料金比較・FAQ・構造化データを足す」）。**
  15ファイル / +1,479行 −160行。09-02 時点で未コミット15件だったものが確定した。作業ツリーはクリーン。
  内訳: `lp/GuestPage.jsx` `lp/HostPage.jsx` `lp/LpKit.jsx` `lp/faq.js` `lp/seo.js`
  `lp/market.js` `lp/socialProof.js` `lp/icons.jsx` `lp/guest.html` `lp/host.html`
  `public/sitemap.xml` `scripts/generate_lp_icons.mjs` `src/lib/brand.js` `src/lib/legal.js` `vite.config.js`
- ⚠️ **未push が1コミット。**
- ⚠️ **`HANDOFF.md` の最新節は §33（09-01 営業DM自動送信）のまま。**
  09-02 の e2e 検証9本（1,792行）と 09-03 の LP 改修が**2日分まとめて未記載。§34 として要追記。**
- 📝 **リモートが `github.com/zaki21016/aiseki` に変わった**（旧メモリの `rikoandmakoto-ops` は古い）。

### FanUp — https://fanup-rouge.vercel.app
✅ 稼働中（トップに サポーター1,248 / 進行中3件 / 達成8ch）。
最終コミット 08-31 14:22（3日停滞）。**未コミット25件が放置。**
ブロッカーは **Stripe・Resend 環境変数**で変化なし。リモートは `rikoandmakoto-ops/fanup` のまま。

### ORIPA — https://oripa-omega.vercel.app
⚠️ **トップページが空レスポンス（HTML シェルのみ）。要目視確認。**
最終コミット 08-11 11:09（23日停滞）。**ブランチが `feat/stripe-checkout` のまま main 未マージ・未push 9件。**
ブロッカーは **古物商許可（審査約40日・未着手）**。リモートは `rikoandmakoto-ops/oripa`。

### ai-english-coach
最終コミット 08-18 22:14（16日停滞）。**リモート未設定＝バックアップなし。**
ブロッカーは **LINE Pay 加盟店申込が未着手**。

### ai-orchestrator
最終コミット 08-09 16:04（25日停滞）。リモート未設定。**アーカイブ継続の判断が保留のまま。**

### rhythm-pop / claude-codex-bridge
rhythm-pop: 06-22 停止・未コミット19件・リモートなし・アーカイブ予定のまま放置。
claude-codex-bridge: 07-04 停止・リモートなし。

> **リモート未設定は `ai-english-coach` / `ai-orchestrator` / `rhythm-pop` / `claude-codex-bridge` の4つ。**
> **`youtube-factory` と `aiseki` は `zaki21016` org、`fanup` と `oripa` は `rikoandmakoto-ops` org。**

---

## 12. 前夜から変わっていない（＝日数が伸びているもの）

- GCP 同意画面の本番公開（**未着手**。失効は 08-24・08-31・09-02 と3回再発）
- `ANTHROPIC_API_KEY` 未追加 → clip-lab 海外枠が毎日失敗・依頼書8件滞留
- 切り抜き素材の枯渇（clip-fukada が実質ゼロ / clip-lab 国内 / clip-animal は clips_per_video=1）
- `socio-rx` の運用可否が未決
- BGM 全ch未設定
- **CTA 遵守率の効果測定（09-01 から4日連続で未実施）**
- 電話認証が daily-science 以外の12chで未完了（fake-paper のサムネ403の直接原因）
- `2ch-matome` の企画構造改善（登録/千 0.16 が最下位）未着手
- `~/.auto-memory` が接続フォルダ外（**6夜連続**）

---

## 13. 生成物

- `reports/全進捗_2026-09-03.md`（本日の全進捗レポート）
- `MEMORY_UPDATE_20260903_night.md`（本ファイル）
- `HANDOFF.md`（§1 のチャンネル表と OAuth 記述を 09-03 実測へ更新）
- `reports/youtube_analysis_20260903.xlsx`（朝の指揮者タスク生成分・5シート）
