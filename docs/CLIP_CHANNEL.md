# 切り抜きチャンネル（clip-lab）

既存の長尺ゆっくり解説（daily-science / scp-lab）から「一番おいしい1シーン」だけを
切り出して縦型ショートにする切り抜きチャンネル。本編への導線を貼るので、母体
チャンネルの再生数も伸ばせる。

---

## 1. NoimosAI について（調査結果 2026-08-04）

**結論: NoimosAI の SaaS は、現時点では無人自動化の切り抜きエンジンとして使えない。**

| 経路 | 状況 |
| --- | --- |
| REST API | **存在しない。** `docs.noimosai.com/api-reference/openapi.json` は Mintlify のサンプル（"OpenAPI Plant Store" / `sandbox.mintlify.com`）のままで実体が無い |
| CLI (`@agos-labs/noimosai-cli` 0.0.9) | あり。公開コマンドは `login` / `chat` / `post` / `workspace` / `integration` / `agent list` |
| MCP (`@agos-labs/noimosai-mcp` 0.0.9 / `https://mcp.noimosai.com/mcp`) | あり。公開ツールは `chat` / `list_workspaces` / `list_integrations` / `post` の4つのみ |

CLI 0.0.9 の内部 API クライアント（`dist/lib/api-client.js`）にあるのは
`postMessage` / `listWorkspaces` / `listProviderAccounts` / `listSessions` /
`getSessionMessages` / `createPost` / `listTriggers` / `testApiKey` だけで、

- 素材動画をアップロードするエンドポイント
- 切り抜きジョブを起動 / ポーリングするエンドポイント
- 完成 MP4 をダウンロードするエンドポイント

のいずれも無い。チャット要求には `mediaPaths` というパラメータがあるが、CLI は
常に空配列で送っており、素材を渡す口として使えない。`agent list` もトリガーの
一覧取得だけで実行はできない。

つまり「クリエイティブエージェントの切り抜き機能」は Web UI 前提の機能で、
autopilot から無人で叩ける公開インターフェースが用意されていない。
加えて API キーの発行には有料プラン（$99/月〜）の契約が必要。

### それでも実装した NoimosAI エンジン

唯一考えられる自動化経路（チャットに元動画 URL を渡し、応答の
NoimosPostJson `media[].url` から MP4 を拾う）を
`backend/pipeline/clip_factory/engines/noimos.py` に実装済み。

```jsonc
// data/channels/clip-lab.json
"clip": { "engine": "noimos", "fallback_engine": "local" }
```

`NOIMOS_API_KEY` を `backend/.env` に入れ、`npm i -g @agos-labs/noimosai-cli` を
実行すれば有効になる。キーが無い / CLI が無い / 元動画が YouTube に公開されて
いない場合は `NoimosUnavailable` を投げ、`fallback_engine`（既定 `local`）へ
自動的に落ちるので autopilot は止まらない。

**この経路はアカウントが無いため未検証。** 実際に切り抜き MP4 が
チャット応答に添付されるかどうかは、契約後に
`python3 backend/run_clip_channel.py --count 1` を1回流せば判定できる
（添付されなければ「動画メディアが返りませんでした」というエラーになる）。

---

## 2. 演出仕様（競合横断分析にもとづく）

`data/research/clip_shorts_visual_analysis.json` に生データ。
再生数 500万〜3300万の切り抜き / 解説ショート **7本**（ひろゆき切り抜き 3371万、
らいす 2ch 1320万、岡田斗司夫切り抜き 1151万、闇のゆっくり放送局 1148万 ほか）の
サムネ＋本編フレームを取得して実測した。

観測された共通フォーマット（4/4 で一致）:

```
┌─────────────────────┐
│  フック帯（常時表示・極太・2〜3行）      │  ← サムネの代わり。スクロールを止める
├─────────────────────┤
│  元動画 16:9 を横幅いっぱい            │  ← 9:16 クロップは 0/7 本
├─────────────────────┤
│  打ち直し字幕（巨大・2行・太縁）        │
│  CTA帯（本編誘導・常時表示）           │
└─────────────────────┘
```

- **9:16 へのクロップ・被写体追従は誰もやっていない。** 解説系は図解とテロップが
  情報の本体なので、寄ると成立しない。
- **フック帯は常時表示**。元動画のタイトルではなく「切り抜いたシーンの結論」を書く。
- **字幕は必ず打ち直す**。元の焼き込み字幕は 1080px 幅に落とすと 24px 相当まで
  潰れるため、下部字幕ボックス（22%）ごと切り落として大きく打ち直す。
- **エフェクトはゼロ**（ズーム / シェイク / グリッチ / トランジションとも 0/7 本）。
  「加工していない感」が切り抜きの信頼性なので、意図的に足さない。
  `video_format.effects` は `preset: minimal` / 全 `allow_*: false`。

縦位置は固定値ではなく毎回組み直す（`renderer.compute_layout`）。16:9 を横幅に
合わせると高さが 486px にしかならず、固定レイアウトだと帯の間に大きな黒余白が
できるため、フック行数と元動画のアスペクト比から積み直している。

---

## 3. パイプライン構成

```
backend/pipeline/clip_factory/
├── sources.py    在庫探索（長尺mp4 × 台本JSON）・消化済み区間の記録
├── align.py      台本行 → 秒数のアライメント
├── segments.py   切り抜き区間の選定・フック文生成
├── renderer.py   9:16 レンダリング（ffmpeg + Pillow）
├── pipeline.py   オーケストレーション・メタ生成・投稿
└── engines/
    ├── local.py   内製エンジン（既定）
    └── noimos.py  NoimosAI SaaS エンジン
```

### 行タイムラインの復元がキモ

`video_generator` は字幕のタイミングを保存していない。音声から取ろうとしても
BGM とノイズフロアに負ける（実測: -45dB では 7分の動画に無音区間が 4個しか出ない）。

そこで **映像** を使う。yukkuri レイアウトは画面下部 20% が字幕ボックスで、
そこは行が切り替わった瞬間にだけ変化する。この帯だけを切り出してシーン検出を
かけると行境界がほぼそのまま出る。

- daily-science: 64行 → 境界 65個（ほぼ完全一致）
- scp-lab: 90行 → 境界 820個（画面エフェクトで過剰検出）

数が合わないケースがあるので、最後に「行の尺は文字数に比例する」
（実測 0.135±0.015 秒/字）という前提で DP アライメントを行い、
とりこぼしと余分をまとめて吸収する。

実測検証（scp-lab / 最悪ケース）:

| 元動画の焼き込み字幕 | 生成した切り抜きの字幕 |
| --- | --- |
| 352s「SCP-914の収容プロトコルが異常に厳重なのも…」 | clip 3s「SCP-914の収容 / プロトコルが異常に厳重なの」 |
| 379s「…『Ultra Fine』で処理した鉄の金属片が、厚さ30センチの…」 | clip 30s「で処理した鉄の金属片が、厚 / さ30センチの強化コンクリ」 |

### 区間の選び方

1. **視聴維持率**（YouTube Analytics の `audienceWatchRatio`）— 実際に視聴者が
   食いついた区間そのもの。取れるときはこちらを重く見る（既定 50%）。
2. **台本スコア** — 数字・断定・種明かしの語彙が濃い区間。台本 JSON が手元に
   あるので字幕を起こし直さずに内容で判断できる。

導入の挨拶とエンディングの CTA は除外（`exclude_head_sec` / `exclude_tail_sec`）。
既出区間とは `min_gap_sec` 以上離す。

### フック文

Claude が使えるときは `refine_with_claude` が採用順とフック文を作る。
使えないとき（クレジット切れ等）は節単位のヒューリスティックにフォールバックする。

解説台本は「2011年のピサ大学の研究では、家族間のあくび伝染率は約50%だった」の
ように *前半が出典・後半が結論* という形が多いので、文ではなく **節** を単位に
選ぶ。結論側の節を採ればそのままフックになる。

---

## 4. 使い方

```bash
cd backend

# 在庫確認（切り抜ける元動画と残り枠）
python3 run_clip_channel.py --list

# 1本生成（投稿しない）
python3 run_clip_channel.py --count 1

# 区間選定だけ確認（レンダリングなし・数秒）
python3 run_clip_channel.py --dry-run --count 3

# 元動画を指定して2本、YouTube へ投稿
python3 run_clip_channel.py --source "なぜあくびが…" --count 2 --upload
```

REST API:

```
GET  /api/clips/clip-lab/sources   在庫一覧
GET  /api/clips/clip-lab/state     消化済み区間
POST /api/clips/generate           生成（既定は非同期。wait:true で同期）
```

出力先は `~/Desktop/動画出力用/_clips/`。消化済み区間は
`data/analytics/clip_state.json` に記録され、同じ動画の同じ場所は二度出ない。

---

## 5. autopilot

`autopilot.gen_type = "clip"` のときだけ、テーマキュー / ScenarioGenerator /
JobQueue を通らず `clip_factory.generate_clip` を直接叩く別系統に入る
(`api_channel_autopilot._run_clip_autopilot`)。レンダリングに数十秒かかるので
スケジューラスレッドは塞がず別スレッドで回す。

関連ガード:

- `theme_queue.ensure_stock` は `style == "clip"` を巡回補充の対象外にする
  （テーマ在庫の概念が無いのに 30分ごとに AI 補充が走るのを防ぐ）
- `POST /api/generate` は `style == "clip"` を 400 で弾く
  （キャラクター未定義のまま対話用レンダラーに入って落ちるため）

### 有効化の手順

1. YouTube に切り抜き用チャンネルを作る
2. `data/channels/clip-lab.json` の `youtube_channel_id` と
   `video_format.youtube.channel_id` を埋める
3. UI から clip-lab の OAuth 連携を行う（`auth_channel_id = "clip-lab"` で保存される）
4. `publish_settings.auto_publish` を `true` に
5. `autopilot.enabled` を `true` に（既定のスケジュールは 12:00 / 21:00 の1日2本）

在庫は 2026-08-04 時点で **元動画 46本 / 残り切り抜き枠 138本**
（`clips_per_video: 3`）。1日2本なら約2ヶ月分。

---

## 6. 既知の制約

- **切り抜き元は自社チャンネルの動画に限定**。他者コンテンツは対象外
  （`content_policy.guidelines` に明記）。
- ローカルに長尺 mp4 が残っていることが前提（`~/Desktop/動画出力用/<タイトル>/`）。
  YouTube からの再ダウンロードには対応していない。
- 視聴維持率は元動画の OAuth が生きているチャンネルでのみ取得できる。
  取れない場合は台本スコアだけで選ぶ（品質は落ちるが動作はする）。
- Claude API のクレジットが切れているとフック文がヒューリスティックになる。
  復旧すれば自動的に Claude 側が使われる（設定変更は不要）。
