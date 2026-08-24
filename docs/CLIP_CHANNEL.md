# 切り抜きチャンネル（clip-lab）

既存の長尺ゆっくり解説（daily-science / scp-lab）から「一番おいしい1シーン」だけを
切り出して縦型ショートにする切り抜きチャンネル。本編への導線を貼るので、母体
チャンネルの再生数も伸ばせる。

---

## 0. 現況サマリ（2026-08-21 更新）

| 項目 | 状態 |
| --- | --- |
| autopilot | ✅ 有効（平日 17:45 / 19:45、土日 12:45 / 14:45） |
| `publish_settings.auto_publish` | ✅ `true`（実際に投稿する） |
| `clip.engine` | `noimos`（フォールバック `local`） |
| `clip.noimos.mode` | `api`（新設。Cloud Functions を直接叩く） |
| NoimosAI 認証 | ❌ **`NOIMOS_API_KEY` 未設定** — これだけが残りブロッカー |
| 在庫 | ✅ 元動画 46 本 / 残り切り抜き枠 132 本 |
| 素材ミラー | ✅ `~/Movies/yf_clip_sources`（46 本ハードリンク済み） |

**キーが入るまでは `local` エンジンで自動的に動く**（＝投稿は止まらない）。
キーを入れた後は `python3 backend/run_clip_channel.py --noimos-check` で
段階的に到達性を確認できる。

### ⚠️ 最重要: macOS TCC で autopilot が死んでいた（2026-08-21 修正）

clip-lab がずっと投稿0本だった**本当の原因**は NoimosAI ではなくこれ。
`backend.log` に次が延々と出続けていた:

```
⚠️ [error] Autopilot 失敗 (clip-lab): [Errno 1] Operation not permitted:
    '/Users/ayukiyamazaki/Desktop/動画出力用'
```

launchd が起動した backend は `~/Desktop` に対して TCC で制限される。
2026-08-21 に launchd 配下で実測した挙動:

| 操作 | 結果 |
| --- | --- |
| `is_dir()` / `is_file()` / `stat()` | ✅ 通る |
| `iterdir()` | ❌ `PermissionError` |
| `glob()` | ⚠️ **例外を投げずに空リストを返す**（静かに死ぬ） |
| `open()` で読む | ❌ `PermissionError`（自プロセスが作ったファイルは可） |
| 書き込み | ✅ 通る |

これが厄介なのは **ターミナルから手で叩くと再現しない**こと
（ターミナルには権限があるため）。「手動では動くのに autopilot だけ 0 本」
という形になる。さらに TCC で読めないファイルを ffprobe に渡すと
**1本あたり 120 秒ぶら下がる**ため、在庫探索が 10 分でも返ってこなかった。

**対策（実装済み・3段構え）**

1. `sources._is_readable()` — ffprobe に渡す前に 1 バイト読んで可読性を確認する。
   これが無いと「エラーも出ないまま数十分固まる」。
2. `sources._folder_videos()` — 列挙できないときは
   `<title>/<channel_id>_メイン.mp4` という命名規則からパスを直接組み立てる。
   glob が**例外なしで空**を返す挙動があるので、空でも必ずこちらに落とす。
3. `sources.MIRROR_BASE`（`~/Movies/yf_clip_sources`）— TCC 保護対象外の
   `~/Movies` に**ハードリンク**でミラーを張る。ディスクは消費しない。
   `discover_sources` はミラーを先に見る（`DEFAULT_SOURCE_ROOTS`）。

```bash
# ミラー作成は「権限のあるコンテキスト」＝ターミナルから実行すること
python3 backend/run_clip_channel.py --mirror
```

新しい長尺動画を作ったら `--mirror` を再実行して差分を張り足す
（既存分はスキップされる）。恒久的に消したいなら次のどちらか:

- `/usr/bin/python3` にフルディスクアクセスを与える
  （システム設定 → プライバシーとセキュリティ → フルディスクアクセス）
- `VIDEO_OUTPUT_BASE` を `~/Desktop` の外（例 `~/Movies/動画出力用`）へ移す

修正の効果: `GET /api/clips/clip-lab/sources` が
**HTTP 500 / 10分タイムアウト → HTTP 200 / 1.8 秒・46 本**になった。

---

## 1. NoimosAI について

### 1-0. 2026-08-21 再調査：**結論が覆った**

以下の 1-1（08-04 の調査）は「NoimosAI では切り抜きができない」と結論して
いたが、**これは現在では誤り**。

1. **クリエイティブエージェントは実在する。** 2026-07-06 のプレスリリースで
   発表された新機能。「一本の長尺動画からエンゲージメントの高いシーンを AI が
   抽出し、被写体を追尾しながら縦型へ自動変換」「冒頭フック違いの複数パターン
   生成（ABテスト）」「各SNS向け最適化」と明記されている。
2. **CLI が別スコープで再公開された。** 旧 `@agos-labs/noimosai-cli` は npm から
   unpublish 済み（404）。新しく **`@noimosai/cli` 0.0.2（2026-08-20 公開）**。
3. **`uploadMedia` が新設された（決定的）。** 08-04 に「無人自動化は不可能」と
   結論した根拠は「素材を渡す口が無い」ことだった。新 CLI には
   `POST /providersPostApi/api/media/upload` があり、返る `path` を chat の
   `mediaPaths` に載せられる。**ローカルの長尺 mp4 を直接渡せる。**
4. **ツールブリッジが新設された。** `GET /noimosToolBridge/tools` /
   `POST /noimosToolBridge/tools/{server}/{name}`。メディア生成を含む
   カタログを型付きで叩ける。
5. **疎通確認済み。** 認証なしで叩くと `401 {"error":"Invalid API key format"}`
   ＝エンドポイントは実在し、認証ゲートだけが立っている。

実測したエンドポイント（ベース `https://us-central1-seo-saas-970de.cloudfunctions.net`）:

| 用途 | メソッド・パス |
| --- | --- |
| APIキー検証 | `POST /chatApiGateway/apiKey/validate` |
| ワークスペース一覧 | `GET /chatApiGateway/workspaces` |
| セッション履歴 | `GET /chatApiGateway/messages?sessionId=` |
| **メディアアップロード** | `POST /providersPostApi/api/media/upload?workspaceId=&filename=` |
| ツール一覧 / 実行 | `GET,POST /noimosToolBridge/tools[/{server}/{name}]` |
| **エージェント実行** | `POST {region}/runNoimosMainAgentHttp`（NDJSON ストリーム） |

エージェント実行だけリージョン解決が入る（TZ が `Asia/` なら
`asia-northeast1`）。実装は `engines/noimos_client.py`。

**残る未検証点は「実際に MP4 が返るか」だけ**で、これは API キーが無いと
確かめられない。返らなければ `NoimosUnavailable` を投げて `local` に落ちる。

**必要なもの（人間しか用意できない）**

```
# backend/.env
NOIMOS_API_KEY=...          # app.noimosai.com で発行
NOIMOS_WORKSPACE_ID=...     # 任意。未設定なら先頭のワークスペース
```

---

### 1-1. 旧調査（2026-08-04）※ 上の 1-0 に上書きされた

**当時の結論: NoimosAI の SaaS は、現時点では無人自動化の切り抜きエンジンとして使えない。**

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

### 再調査メモ（2026-08-09）

08-04 以降で変わった点と、変わっていない点。

**変わった点**

- `app.noimosai.com` にブラウザから到達できるようになった（08-04 はポリシー遮断）。
  ログイン／サインアップ画面を実測できた。
- ヘルプに [Create and edit images, videos, and audio](https://docs.noimosai.com/help-center/chat/create-and-edit-media)
  が追加され、動画能力の記述が「台本生成」止まりではなくなった。
  Videos の例として *"Short videos, ad videos, explainer videos, video outlines, captioned videos"*、
  用途に *"Adjusting composition, color, aspect ratio, or text based on existing images or videos"* とある。
- Chat に**ファイル添付**がある（[Upload Files](https://docs.noimosai.com/help-center/chat/upload-files)。1メッセージ5件まで）。

**変わっていない点（＝結論は据え置き）**

- **長尺動画を区間で切り出す機能はどこにも documented されていない。** 動画能力は
  「生成」と「生成物への生成的な編集」であって、20分の元動画から50秒を抜く編集ではない。
- 公開 REST API は依然無い（`api-reference/openapi.json` は Mintlify サンプルのまま）。
  CLI / MCP の公開ツールも `chat` / `list_workspaces` / `list_integrations` / `post` の4つだけ。
- 料金は Pro **$99**／Team $249／Advanced $499（いずれも user/月）。動画編集・API は
  どのプランの説明にも出てこない。

**ログイン画面の実測結果（08-04 の記録と食い違うので上書き）**

| 項目 | 08-04 の記録 | 08-09 の実測 |
| --- | --- | --- |
| 言語 | 英語 | **日本語がデフォルト** |
| OAuth | 無し | **Google ログインあり** |
| メール欄 | `input[type=email]` 想定 | `type="text"` / `name`・`placeholder`・`autocomplete` すべて空 / `id` は React 生成のランダム値 |
| ボット対策 | 記録なし | **reCAPTCHA Enterprise（`render=explicit`）** |

属性で特定できないため `engines/noimos.py` の `_login()` を
「フォーム内の非パスワードテキスト入力を拾う」方式に修正済み。ログインボタンも
日本語「ログイン」を先に試す順序に変更した。

**reCAPTCHA があるので headless の自動ログインは弾かれうる。** その場合は人間が
一度ログインして `~/.youtube-factory/noimos_session.json`（storage_state）を作り、
以後はそれを使い回す。CAPTCHA 突破は実装しない。

### それでも実装した NoimosAI エンジン

唯一考えられる自動化経路（チャットに元動画 URL を渡し、応答の
NoimosPostJson `media[].url` から MP4 を拾う）を
`backend/pipeline/clip_factory/engines/noimos.py` に実装済み。

```jsonc
// data/channels/clip-lab.json
"clip": { "engine": "noimos", "fallback_engine": "local" }
```

経路は `clip.noimos.mode` で2つ。現在の clip-lab.json は `browser`。

| mode | 必要なもの | 現状 |
| --- | --- | --- |
| `browser`（既定） | Playwright + Chromium、`NOIMOS_EMAIL` / `NOIMOS_PASSWORD` | Playwright 1.217 / Chromium 導入済み ✅ ／ **認証情報が未設定** ❌ |
| `cli` | `NOIMOS_API_KEY`（Pro $99/月〜）、`npm i -g @agos-labs/noimosai-cli` | どちらも未 ❌ |

いずれも足りなければ `preflight()` が理由を返して `NoimosUnavailable` を投げ、
`fallback_engine`（既定 `local`）へ自動的に落ちるので autopilot は止まらない。

**残作業（人間しかできない）**

1. https://app.noimosai.com/signup でアカウントを作る（利用規約の同意が必須。
   Google ログインも可）。**有料プランの契約は browser mode では不要**（API キーが
   要るのは cli mode だけ）。ただし無料トライアルの範囲は未確認。
2. `backend/.env` に追記する:
   ```
   NOIMOS_EMAIL=...
   NOIMOS_PASSWORD=...
   ```
3. reCAPTCHA で headless ログインが弾かれる場合は、`clip.noimos.headless` を一時的に
   `false` にして有人で1回通し、`~/.youtube-factory/noimos_session.json` を作る。
4. `clip.engine` を `"local"` → `"noimos"` に変える。

**未検証。** 実際に切り抜き MP4 が返るかは、上記を済ませてから
`python3 backend/run_clip_channel.py --count 1` を1回流せば判定できる
（返らなければ「NoimosAI が …s 以内に動画を返しませんでした」というエラーになり
local に落ちる）。返らなかった場合の次の一手は、プロンプトに YouTube URL を書く
現状の方式をやめ、Chat のファイル添付（5件/メッセージ）でローカルの長尺 mp4 を
アップロードする経路を `_submit_prompt()` に足すこと。

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

## 6. 素材調達（外部ソース）

`backend/pipeline/clip_factory/acquisition.py`。既定は **off**
（`clip.external_sources.enabled = false`）。自社動画の在庫（残り 132 本）が
ある間は不要。

### ⚠️ ライセンスゲートが本体

「YouTube のトレンド動画やニュースを切り抜く」は**そのままやると著作権侵害**。
標準ライセンス（`youtube` = All Rights Reserved）の動画を切り出して再アップ
すると、Content ID による収益剥奪・著作権警告・チャンネル削除に直結する。
報道映像は特に厳しい。

そこで調達した候補は必ず2つに仕分ける。判定は `acquisition.classify()` の
一箇所だけ（**fail-closed**：判定できないものは全部 `theme_only`）。

| 区分 | 対象 | 扱い |
| --- | --- | --- |
| `clippable` | CC BY / 自社ch / 許諾済み allowlist | 切り抜いて再アップしてよい |
| `theme_only` | 標準ライセンスのトレンド・ニュース | **映像は一切触らない。** 題材シグナルとしてのみ使う |

`theme_only` の動画は `download_candidate()` が `PermissionError` で撥ねる
（呼び出し側のミスで落ちないよう、ダウンロード関数の入口で止める）。
これなら「今この話題が伸びている」という情報だけを権利問題なしに取り込める。

### 経路

| 経路 | API | 既定 |
| --- | --- | --- |
| 急上昇 | `videos.list(chart=mostPopular, regionCode=JP)` | theme_only |
| CC検索 | `search.list(videoLicense=creativeCommon)` | clippable |
| 許諾済みch | `allowlist_channels[]` に `permission_note` 付きで登録 | clippable |

CC検索は `search.list` の `videoLicense` を信用せず、`videos.list` の
`status.license` で**再検証**してから通す（search 側の値がずれるため）。
ダウンロードは `yt_dlp`（Python モジュール。CLI バイナリは不要）。

CC BY は**帰属表示が義務**。`attribution_text()` が説明欄に貼れる形で返す。

```bash
# 調達候補を見るだけ（ダウンロードしない）
python3 backend/run_clip_channel.py --acquire --force

# clippable だけ実際に落とす
python3 backend/run_clip_channel.py --acquire-download --force --count 3
```

実測（2026-08-21）: CC検索で **clippable 16 本**、急上昇から
**theme_only 50 本**。急上昇の 50 本は全て `license=youtube` で、
正しく theme_only に落ちている。

---

## 7. 既知の制約

- **切り抜き元は自社チャンネルの動画に限定**。他者コンテンツは対象外
  （`content_policy.guidelines` に明記）。
- ローカルに長尺 mp4 が残っていることが前提（`~/Desktop/動画出力用/<タイトル>/`）。
  YouTube からの再ダウンロードには対応していない。
- 視聴維持率は元動画の OAuth が生きているチャンネルでのみ取得できる。
  取れない場合は台本スコアだけで選ぶ（品質は落ちるが動作はする）。
- Claude API のクレジットが切れているとフック文がヒューリスティックになる。
  復旧すれば自動的に Claude 側が使われる（設定変更は不要）。
