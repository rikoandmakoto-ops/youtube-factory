# メモリ更新差分 — 2026-09-04 深夜（nightly-full-progress）

> ⛔ `~/.auto-memory/` は接続フォルダ外のため**今夜も直接書き込めなかった（7夜連続）**。
> 接続済みは `Developer` / `youtube-factory` / `iCloud Documents` / `Downloads` の4つ。
> **恒久対応: Cowork の接続フォルダに `~/.auto-memory` を追加する。**
> 当面は本ファイルと `youtube-factory/HANDOFF.md` を YouTube Factory のメモリ本体として扱う。

実行: 2026-09-04 23:10–23:30 JST

---

## 1. ★★ OpenAI 429 は 11:16 に解消した。朝のメモ §1「本日の公開本数は0本」は破棄すること

`MEMORY_UPDATE_20260904.md` §1 は **10:35 時点の観測としては正しかったが、11時台に状況が変わった。**
以下に置き換える。

**実測（`data/api_usage.jsonl`）: 09-04 の API 呼び出しは 23:13 時点で 246 件、
最初が 11:16:11。** 09-03 は 18:49 を最後に成功記録がゼロだったので、11:16 に復旧したと判断できる。

> ⚠️ **`api_usage.jsonl` は成功時のみ追記される台帳で、エラーを記録する欄が無い**
> （スキーマは `ts/type/model/prompt_tokens/completion_tokens/total_tokens/cost_usd/channel_id/purpose`）。
> **「エラー行ゼロ」を 429 解消の根拠にしてはいけない。** 根拠は「成功記録が11:16以降に再開したこと」と
> 「17本が公開まで到達したこと」の2つ。
時間帯別: 11時 34 / 12時 22 / 13時 1 / 14時 23 / 15時 16 / 16時 26 / 17時 10 / 18時 47 / 23時 67（23時は日次PDCA実行中で増加中）。
モデル別: `gpt-5.6-terra` 160 / `gpt-5.6-luna` 24 / `gpt-image-1` 18 / `gpt-4o-mini` 16。

**本日の公開は 21 本**（ゆっくり系 17 + 切り抜き 4）。ゆっくり系は `data/job_queue.json` の
09-04 分 17 ジョブが全て `status=completed`、`backend.log` に対応する
`🚀 ショート自動公開完了` と `video_id` が揃っている。

| 時刻 | ch | タイトル | video_id |
|---|---|---|---|
| 11:18 | yokai-watch | 犬神憑きはなぜ家系ごと記録されたのか 恒一 | jBrtIbNN5NM |
| 11:32 | 2ch-matome | 正体を大人が知る3秒の言葉あげてけw😂 | CPhxUakX8mw |
| 11:48 | daily-science | 黙読中の喉、なぜ声なしで1秒だけ動く？ | 6lcWup40vok |
| 11:48 | **clip-lab** | 株を渡されない社長は いつでもクビになれる | -UiTA3tALd8 |
| 12:19 | scp-lab | SCP-6121 毎晩1cm動く椅子、14日目に起きた異変 | 1_OFbz4Xqzk |
| 12:45 | company-facts | 日本マクドナルドの年収576万円、その内訳とは | iTLPgjOJAYE |
| 13:45 | akashic-librarian | なぜ同じ失敗でも、肩書きがある人だけ許されるのか | PuHKm7UzClk |
| 14:00 | **clip-kaneko** | 恋愛を体験できる一冊に | zFzveWT2A8c |
| 14:18 | pokemon-lab | エースバーンのリベロ、1試合でしか変われない!? | saslFdGKLOg |
| 14:47 | fake-paper | 架空論文ファイル #9：行列の最後尾は9%短く待てる | k8LdSuv7Drk |
| 15:18 | yokai-watch | 雪夜に顔を隠す白粉婆…雪女とは違う恐ろしさ | 0F8nNs8IFFQ |
| 16:15 | company-facts | 星野リゾートの推定年収400万円、業界平均と比べると？ | kv1KNLaPkWA |
| 16:18 | daily-science | 泳いでいる脳が3秒ごとに息継ぎを気にするワケ | SzMbnxjh0hM |
| 16:48 | pokemon-lab | 御三家の相性が三すくみになったワケ | FlhD3y4SXSU |
| 17:17 | 2ch-matome | なぜ友達の風呂で3回もやらかしたのか？ｗ | DARoakZbgGk |
| 17:46 | **clip-lab** | 向いていることを やり続ければいい | U0W0HjIPXsg |
| 18:00 | akashic-librarian | なぜ30分待っても列をやめられない？ | XgKZ5b4XDww |
| 18:17 | scp-lab | SCP記録係12名が最後に揃って書いた42字 | rMCy64I45Zs |
| 18:18 | yokai-watch | じんめん犬はなぜ笑い話になった？消えた恐怖の噂 | _0xgJRshAgQ |
| 18:48 | fake-paper | なぜ金魚は帰宅30分前に水面へ集まるのか？ | HYZOis-0Ry0 |
| 20:30 | **clip-kaneko** | 白いゲーミングPCは 中の色まで変えられる | dxph90B2w4o |

> **朝のメモ §7-1「429 の解消が全ての前提」は達成済み。次のボトルネックは 429 ではない。**
> なお朝に入れ替えた 44 件のテーマキューが実際に効いており、生成タイトルは全て
> 「隠された秘密」型を含まず、数字＋単位が入っている（§4 参照）。

---

## 2. 🆕 本日の最大の設計変更 — 画像生成を OpenAI API から ChatGPT スレッドへ移した

`youtube-factory` に本日 5 コミット。うち 2 件が画像パイプラインの作り替え。

| 時刻 | hash | 内容 |
|---|---|---|
| 10:23 | 009d695 | タイトル・テーマ・演出の施策を自然文から**機械ゲート**へ移す |
| 10:23 | 3a0dba4 | 投稿量を倍増し、機械ゲートと判断軸を全チャンネルへ反映 |
| 10:23 | 284df19 | 09-03 の実行結果と HANDOFF を記録 |
| **17:00** | **9b03b40** | **画像生成を OpenAI API から ChatGPT のブラウザスレッドへ移す** |
| **19:59** | **a08c70d** | **画像は 1ch=1スレッド固定にし、OpenAI Images API を削除する** |

### 変更の中身（コミットメッセージから）

- 新設 `pipeline/chatgpt_image_bridge.py` が `data/image_requests/` にファイルキューを持つ。
  パイプラインは依頼を積んで**待たずに `None` を返し**、従来どおり Pillow へ落ちる
  （autopilot は無人なので待つと投稿枠を落とすため）。
- **OpenAI Images API の呼び出しコードを `video_generator` / `thumbnail_generator` から削除。**
  フラグ無効化ではなく経路ごと削除。再混入は `TestNoOpenAIImageCalls` が監視。
- スレッド URL の置き場は **`data/channels/<ch>.json` の `image_generation.chatgpt_thread_url`**。
  設定ファイルの無い `_default` だけ `data/image_requests/threads.json` に残る。
- 方針は `pipeline/openai_policy.py` 1箇所で決まる。**画像の API 直叩きは既定で禁止。**
  テキストは `OPENAI_TEXT` の既定が 1 のまま（塞ぐと台本生成が全ch止まるため）。
  **`ANTHROPIC_API_KEY` を入れた時点で OpenAI は呼ばれなくなる。**
- 操作は `scripts/image_bridge.py`、ワーカー手順は `.claude/skills/chatgpt-image-worker/`、
  全文は `docs/CHATGPT_IMAGE_BRIDGE.md`。

### 🚨 ただし現時点でブリッジは死んでいる（本日の新規ブロッカー）

**実測: 13ch すべてで `image_generation.chatgpt_thread_url` が未設定。
`data/image_requests/threads.json` は `{}`。**

キューの状態:

| ディレクトリ | 件数 |
|---|---:|
| `pending` | **1**（`20260904_154708_488fd9.json` / 15:47 から滞留） |
| `delivered` / `cache` / `images` / `failed` | 0 |

**つまり依頼は積まれるが処理する側の宛先が1つも登録されていない。**
画像は全て Pillow フォールバックで生成されている。
**次の作業は「13ch 分の ChatGPT スレッドを開いて URL を各 config に登録する」。**
これをやらない限り 17:00/19:59 のコミットは効果ゼロのまま。

---

## 3. 🆕 サムネイル 403 は fake-paper だけの問題ではない（記述の訂正）

09-03 のメモは「電話認証未完了 → fake-paper のサムネ403の直接原因」と書いていたが、
**本日公開したゆっくり系17本を1本ずつログと照合したところ、13本が 403 だった。**

| ch | 本日公開 | うち403 | 判定 |
|---|---:|---:|---|
| yokai-watch | 3 | **3** | ❌ 権限なし |
| 2ch-matome | 2 | **2** | ❌ 権限なし |
| scp-lab | 2 | **2** | ❌ 権限なし |
| company-facts | 2 | **2** | ❌ 権限なし |
| pokemon-lab | 2 | **2** | ❌ 権限なし |
| fake-paper | 2 | **2** | ❌ 権限なし |
| **daily-science** | 2 | **0** | ✅ **権限あり** |
| **akashic-librarian** | 2 | **0** | ✅ **権限あり** |

エラーは全て
`The authenticated user doesn't have permissions to upload and set custom video thumbnails.`（reason: `forbidden`）。
**動画のアップロード自体は成功しており、サムネだけが YouTube 既定の自動生成のまま公開されている。**

> **電話認証が通っているのは `daily-science` と `akashic-librarian` の2ch。**
> 09-03 のメモは「daily-science 以外の12chで未完了」としていたが、**akashic-librarian も通っている**ので訂正する。
> 本日サンプルが取れた8ch中6chが未完了。**サムネは CTR に直結するので、電話認証の優先度を上げること。**

---

## 4. テーマキュー入替（朝実施）は生成に効いていることを確認

本日生成された 17 本のタイトルを検査した結果:

- **「〜に隠された秘密／設定／メッセージ」型はゼロ**（朝に `forbid_patterns` へ追加した型）
- 数字＋単位を含むもの: 「3秒」「1cm」「14日目」「576万円」「400万円」「30分」「42字」「9%」「1,284人」「1試合」など
- 疑問符は残っているが必須化はしていない（09-03 に撤回済み）
- **09-03 に問題視した「127」のような意味を持たない数字の混入は本日はゼロ。**
  `require_number_with_unit` の副作用の疑い（09-03 §8）は、朝の機械ゲート化（009d695）で
  解消した可能性が高い。**09-05 も継続監視。**

`2ch-matome` の「正体を大人が知る3秒の言葉あげてけw😂」は
`theme_priority` が最優先と定める**参加型・大喜利**で、朝の入替が意図通りに効いた実例。

---

## 5. 🆕 clip-lab に新しい素材経路が通った（ひろゆき allowlist）

`data/analytics/clip_acquisition.json` の在庫は 18 本。

| 提供元 | 本数 |
|---|---:|
| 金子みゆ / kaneko_miyu | 8 |
| **ひろゆき, hiroyuki** | **4** |
| 深田えいみ / Eimi Fukada | 4 |
| 岡田斗司夫 | 1 |
| Cat Kitty | 1 |

**09-04 17:46 に `daulqJwmooE`「神を信じない経営者は傲慢である。」を取得。**
取得理由は `説明欄に許諾文言『切り抜き用にガジェ通クリエイターベータベース』を確認（allowlist 登録チャンネル）`。
duration 12,967 秒（3時間36分）の長尺なので、**clip-lab の国内枠は当面枯渇しない。**
本日 clip-lab が 2 本出せたのはこれが理由。

---

## 6. 全チャンネル コンフィグ現況（09-04 23:20 実読み）

| ch | autopilot | queue | 投稿枠 | cta_position | 本日公開 |
|---|---|---:|---:|---|---:|
| daily-science | ✅ | 46 | 3 | `end_of_video` | 2 |
| scp-lab | ✅ | 41 | **6**（平日3・土日3） | `after_hook`（**対照群**） | 2 |
| pokemon-lab | ✅ | 30 | 3 | `end`（**変更アーム**） | 2 |
| yokai-watch | ✅ | 31 | 3 | `end`（**変更アーム**） | 3 |
| 2ch-matome | ✅ | 46 | 3 | `end`（**変更アーム**） | 2 |
| company-facts | ✅ | 49 | 3 | `end` | 2 |
| akashic-librarian | ✅ | 35 | 3 | `end` | 2 |
| fake-paper | ✅ | 38 | 3 | `after_hook`（**対照群**） | 2 |
| clip-lab | ✅ | 33 | 3（うち20:45は `engine: viral`） | `end` | 2 |
| clip-kaneko | ✅ | 38 | 3 | `end` | 2 |
| clip-fukada | ✅ | 32 | **2** | `end` | **0** |
| clip-animal | ✅ | 14 | **2** | `end` | **0** |
| socio-rx | ❌ | 5 | 2 | `end` | 0 |

> ⚠️ **投稿枠は `autopilot.schedule.times` の要素数。`slots` というキーは存在しない。**
> 09-03 以前のメモに出てくる「スロット5」は出所不明なので使わないこと。
> **`clip-lab` の 20:45 枠だけ `engine: viral` が付いており、ここが毎日
> `ANTHROPIC_API_KEY` 未追加で落ちている海外バイラル枠の実体。**

- **朝のメモの「akashic キュー最少 8」は解消**（35 に増）。09-03 比で全ch キューが増えている。
- **BGM は「13ch 未設定」ではなく「12ch 未設定」。** `data/channels_assets/` に
  `bgm/` を持つのは **`daily-science` だけ（7ファイル）**で、本日のログには
  `🎵 BGM per-scene mix: 3シーン, crossfade=1.5s, volume=0.30` が出ており**実際に適用されている**。
  他12chは `🎵 BGM: 音源が見つからないためスキップ` のまま。
  > ⚠️ **config の `bgm_path` は 13ch すべて null だが、これは未設定の証拠にならない。**
  > `backend/pipeline/video_generator.py:663` が `data/channels_assets/<ch>/bgm/` を直接探索するため。
  > **BGM の有無は config ではなく音源ディレクトリの実在で判定すること。**
- 切り抜き4ch の `clip.sources` は全て 0 件（外部素材のみで回っている）。
  `clip.external_sources.enabled` は 4ch とも true（09-03 の clip-animal 修正が維持されている）。
- `clips_per_video`: clip-animal **1** / clip-fukada 4 / clip-kaneko 4 / clip-lab 5。
  **clip-animal の 1 が枯渇の直接原因**（09-03 から未対応）。

---

## 7. ⚠️ 09-03 の「ゴミキュー →6」は実行されていない

09-03 のメモ §9 は切り抜き4ch のキューを「37→6」等と書いていたが、**実測は減っていない。**

| ch | 09-03 記載 | 09-04 実測 |
|---|---:|---:|
| clip-lab | 37（→6） | **33** |
| clip-fukada | 31（→6） | **32** |
| clip-kaneko | 38（→6） | **38** |
| clip-animal | 14（→6） | **14** |

切り抜きchはテーマキューを一切使わないので実害は出ていないが、
**`trend_scanner` / `series_engine` が毎日補充し続けているので減らない。**
恒久対応は「対象chから `style: clip` 系を除外する」であり、キューを手で削っても翌日戻る。
**09-03 の「→6」は計画であって実施ではなかった。メモの書き方を改めること。**

---

## 8. ⚠️ `video_status` DB はゆっくり系の公開を記録していない（新規発見）

`data/video_publish.db` の `video_status` に本日入っているのは**切り抜き4本のみ**。
ゆっくり系17本は `backend.log` に `upload_done` があるのに DB に行が無い。

`video_status` の ch別 `max(published_at)`:

```
2ch-matome        2026-08-31   akashic-librarian 2026-08-31
company-facts     2026-08-31   daily-science     2026-08-31
fake-paper        2026-08-31   pokemon-lab       2026-08-31
yokai-watch       2026-08-31   scp-lab           2026-09-03
clip-animal       2026-09-03   clip-kaneko       2026-09-04
clip-lab          2026-09-04
```

**08-31 で止まっているのは「公開していない」のではなく「書き込み経路が違う」から。**
切り抜き経路（`clip_factory`）だけが `video_status` に書き、
ゆっくり経路（`short_publish` / `api_phase4`）は書いていない。

> **教訓: 公開実績を `video_status` だけで判定するな。ゆっくり系は `job_queue.json` の
> `status=completed` と `backend.log` の `upload_done` で数えること。**
> このDBを根拠に「8-31 から止まっている」と書くと誤診になる。

---

## 9. 実績（09-03 → 09-04 スナップショット差分・**暫定**）

⚠️ **23:00 開始の日次 PDCA が本レポート作成中も実行中**（23:09 時点で pokemon-lab を処理中、
scp-lab / yokai-watch / socio-rx が未取得）。以下は確定値ではない。

| ch | Δ再生 | Δ登録 | 登録/千再生 |
|---|---:|---:|---:|
| pokemon-lab | 1,669 | 2 | 1.20 |
| scp-lab | 1,110 | 0 | 0.00 |
| 2ch-matome | 1,096 | 0 | 0.00 |
| fake-paper | 778 | 0 | 0.00 |
| clip-kaneko | 181 | 0 | 0.00 |
| clip-fukada | 82 | 0 | 0.00 |
| company-facts | 49 | 0 | 0.00 |
| yokai-watch | 9 | 0 | 0.00 |
| daily-science | 4 | 0 | 0.00 |
| clip-lab | 1 | 0 | 0.00 |
| akashic-librarian | 0 | 0 | — |
| **合計** | **4,979** | **2** | **0.402** |

- `video_metrics` は 09-04 で 313 行取得済み（09-03 は 296 行）。累計値なので負の差分は 0 に丸めた。
- **登録/千再生 0.402 は 09-03 の 0.394 とほぼ同水準。**
  cta_position A/B の判定日は **09-11**。本日の数値で判断してはいけない。
- `channel_metrics` は **09-01 が最新**（08-31 → 09-01 と1日進んだが依然3日欠測）。
  09-01 の値は views が極端に小さく（akashic 0 / pokemon 6 / 2ch 7）、**取得不全の疑いが濃い。**
  日次の登録増減は引き続き `video_metrics` 差分で見ること。

---

## 10. 継続ブロッカー（日数が伸びているもの）

| ブロッカー | 状態 | 継続 |
|---|---|---|
| `ANTHROPIC_API_KEY` が `.env` に**未追加** | clip-lab 海外枠が毎日失敗。**依頼書 9 件に増**（09-03 は 8 件、本日 `viral_1w6etlj` 追加） | 継続 |
| GCP 同意画面の本番公開 | **未着手**。失効は 08-24・08-31・09-02 と3回再発。**次は 09-09 前後** | 継続 |
| 電話認証未完了 | サムネ 403 が **5ch** に拡大（§3） | 継続・悪化 |
| clip-fukada の素材ゼロ | 本日も 3 枠全滅。`UCRUdyowhXEQhoNT7uNEvGJA` が「チャンネルが見つかりません」/ `yjF8W6-BZd4` の区間DL失敗 / 尺条件に合う区間なし | 継続 |
| clip-animal の `clips_per_video=1` | 本日も「全ての元動画が切り抜き済み」で3枠全滅 | 継続 |
| `REDDIT_CLIENT_ID`/`SECRET` 未設定 | RSS 経路のみで 429 頻発。`viral_acquisition` は 4 件全て `skipped`（尺範囲外） | 継続 |
| BGM **12ch** 未設定 | daily-science のみ音源あり・適用済み。他12ch は未設定 | 継続 |
| `socio-rx` の運用可否 | 未決。autopilot ❌ のまま | 継続 |
| CTA 遵守率の効果測定 | **09-01 から5日連続で未実施** | 継続 |
| `channel_metrics` 欠測 | 09-01 が最新（3日） | 継続 |
| `~/.auto-memory` が接続フォルダ外 | **7夜連続** | 継続 |
| **ChatGPT 画像ブリッジの thread_url 未登録** | 🆕 本日発生。13ch 全て未設定 | 新規 |
| 未コミット 82 件（youtube-factory） | 内訳は `data/` 配下の実行結果が中心（config 10 / series_links 8 / originality 8 / analytics 5 / scenarios 25 ほか）。**コードの未コミットは無し** | 継続 |

---

## 11. 他プロジェクト（09-04 23:20 実読み）

### ⚠️ リモート組織の記述を訂正する

09-03 のメモ §11 末尾「`youtube-factory` と `aiseki` は `zaki21016` org」は**誤り。**
実測:

```
youtube-factory  origin    = github.com/zaki21016/youtube-factory.git
                 neworigin = github.com/rikoandmakoto-ops/youtube-factory.git
aiseki           origin    = github.com/zaki21016/aiseki.git
                 neworigin = github.com/rikoandmakoto-ops/aiseki.git
fanup            origin    = github.com/rikoandmakoto-ops/fanup.git （1つだけ）
oripa            origin    = github.com/rikoandmakoto-ops/oripa.git （1つだけ）
```

**youtube-factory と aiseki は2つ登録されている。09-03 メモの `zaki21016` は
「古い」のではなく `origin` として現役。**
`origin` が旧 org を指しているので `git push` の既定の宛先は `zaki21016` 側。
**どちらを正とするか決めて、`origin` を張り替えるか `neworigin` へ明示 push するかを統一すること。**
fanup / oripa はリモート1つで `rikoandmakoto-ops`。

### aiseki — https://aiseki-xi.vercel.app（canonical `https://aisekimatch.com/`）

- ✅ 稼働中。SEO メタ・OG 画像・構造化データが 09-03 の LP 改修どおり出ている。
- ⚠️ **最終コミット 09-03 11:08（`af5f442`）から2日停滞。**
- ⚠️ **未push 1コミット（`af5f442`）が 09-03 から解消していない。** 作業ツリーはクリーン。
- ⚠️ **`HANDOFF.md` は §33（09-01 営業DM自動送信）が最新のまま。ファイル更新日時も 09-01 20:17。**
  09-02 の e2e 検証（`e37c670`・`0ea61b3`）と 09-03 の LP 改修（`af5f442`）が
  **3日分まとめて未記載。§34 として要追記。**

### FanUp — https://fanup-rouge.vercel.app

- ✅ 稼働中。トップに サポーター **1,248** / 進行中 **3** 件 / 達成 **8** ch。
  注目クリエイター3名（みみき / けけんた / ああかり）、プロジェクト3件（82% / 45% / 60% 達成）が表示。
- ⚠️ 最終コミット 08-31 14:22（`2681dfd`）から**4日停滞**。未push 0。
- 📝 **未コミット25件の内訳: 事業計画書 docx/pdf/pptx 3 / ページ画像 page-01〜19.jpg 19 /
  `HANDOFF.md` 1 / `lu469vdwg.tmp` 1 / `supabase/apply_missing_functions.sql` 1。**
  アプリのソースコードは無いので消失リスクは低いが、
  **SQL マイグレーション1件はコード資産**なので「全部ただの文書」ではない。
  `apply_missing_functions.sql` は未適用の可能性があるので要確認。
- ブロッカーは **Stripe・Resend の環境変数**で変化なし。

### ORIPA — https://oripa-omega.vercel.app

- ⚠️ **トップページが本日も空レスポンス**（HTML シェルのみ、本文ゼロ）。09-03 から変化なし。
- 最終コミット 08-11 11:09（`5c15784`）から**24日停滞**。
- ⚠️ **ブランチが `feat/stripe-checkout` のまま main 未マージ。** 未コミット 1 件。
  （09-03 の「未push 9件」は現在 upstream 未設定のため計上されない。要確認）
- ブロッカーは **古物商許可（審査約40日・未着手）**。

### ai-english-coach

- 最終コミット 08-18 22:14（`a90c4ad`）から**17日停滞**。未コミット 2 件。
- ⚠️ **リモート未設定＝バックアップなし。**
- ブロッカーは **LINE Pay 加盟店申込が未着手**。

### ai-orchestrator

- 最終コミット 08-09 16:04（`052a617`）から**26日停滞**。未コミット 1 件。リモート未設定。
- **アーカイブ継続の判断が保留のまま**（09-03 から変化なし）。

### rhythm-pop / claude-codex-bridge

- rhythm-pop: 06-22 17:17 停止・未コミット19件・リモートなし・アーカイブ予定のまま放置。
- claude-codex-bridge: 07-04 02:45 停止・未コミット1件・リモートなし。

> **リモート未設定は `ai-english-coach` / `ai-orchestrator` / `rhythm-pop` / `claude-codex-bridge` の4つ**（変化なし）。

---

## 12. 反証条件の期限（更新）

- **cta_position A/B（09-11 期限）** — 変更アーム yokai / pokemon / 2ch（`end`）vs
  対照 scp-lab / fake-paper（`after_hook` 据え置き）。
  baseline: 妖怪 0.23 / ポケモン 0.23 / 2ch 0.17。**上回らなければ `after_hook` に戻す。**
  本日の数値（pokemon 1.20 / yokai 0.00 / 2ch 0.00）は n が小さすぎるので判断に使わない。
- **「正体」効果の再測定（09-08 期限）** — 本日 17 本投入で母数が増えた。
  `pokemon-lab` を除く3chでの効果量も併記すること。
- **speed 引き下げ（09-05 期限）** — 本日時点で config に `speed` キーが見つからない
  （`video` / `voice` / `audio` / `tts` / `voicevox` のいずれにも無い）。
  **09-03 メモの speed 値の出所を再確認してから判定すること。存在しない設定を判定しても意味が無い。**

---

## 13. 明日（09-05）の優先順

1. **ChatGPT 画像ブリッジの thread_url を 13ch 分登録する。** これが無いと本日のコミット2件が死んだまま。
2. **`ANTHROPIC_API_KEY` を `.env` に追加。** 依頼書9件が消化され、`gpt_insights` が全ch復活し、
   `openai_policy` により OpenAI テキスト呼び出しも自動で止まる。**1手で3つ解決する最安の手。**
3. **電話認証**（サムネ403 が5chに拡大している）。
4. **GCP 同意画面の本番公開**（次の失効が 09-09 前後）。
5. clip-animal の `clips_per_video` を上げる / clip-fukada の素材投入。
6. aiseki の未push 1件を push し、`HANDOFF.md` に §34 を追記。
7. `trend_scanner` / `series_engine` から `style: clip` 系を除外（キューを手で削っても翌日戻る）。

---

## 14. 生成物

- `reports/全進捗_2026-09-04.md`（本日の全進捗レポート）
- `MEMORY_UPDATE_20260904_night.md`（本ファイル）
