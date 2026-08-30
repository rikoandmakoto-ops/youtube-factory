# 海外バイラル切り抜き（clip-lab の 20:45 枠）

作成: 2026-08-30 / 最終更新: 2026-08-30 / チャンネル設定: `data/channels/clip-lab.json`

Reddit で今日バズった海外の短尺動画を、**日本語字幕付きの縦型ショート**に翻訳して
量産するパイプライン。

> ⚠️ **2026-08-30 のユーザー決定で構成が変わった。** 当初は専用チャンネル
> `clip-viral` を作る設計だったが、**新規チャンネルは作らず既存の切り抜きラボ
> （`clip-lab`）に同居**させる。`data/channels/clip-viral.json` は削除し、
> 設定は `clip-lab.json` の `clip.viral_sources` 配下に統合済み。

確定している運用（変更する場合はこの4点をまとめて見直すこと）:

| 項目 | 決定 |
|---|---|
| チャンネル | 既存の `clip-lab` に同居（新規チャンネルを作らない） |
| レンダラ | **国内切り抜きと共有しない**。`renderer_overseas.py` に分離 |
| 翻訳失敗時 | スキップせず**3回まで指数バックオフで再試行** |
| 公開設定 | 目視レビューなし。**private を経ず直接 public** |
| 投稿枠 | 毎日 **20:45 に1枠**（国内切り抜きは 17:45 のまま） |

---

## 0. 1チャンネル2系統という構成

```
clip-lab（YouTube チャンネル UCbWZ5quEFE2VpHPh5TGyPCw）
  ├─ 17:45  国内切り抜き    engine=local   許諾済み YouTube 素材（ひろゆき等）
  └─ 20:45  海外バイラル翻訳 engine=viral   Reddit 素材 → Whisper → Claude
```

同居させるにあたって、混ざると壊れる4箇所を分けてある。

| 分けたもの | 場所 | 分けないとどうなるか |
|---|---|---|
| 素材の探索先 | `pipeline._collect_sources(engine=...)` | local エンジンが Reddit 素材（台本も字幕も無い）を掴んで必ず落ちる |
| レンダラ | `renderer_overseas.py` | 海外枠の見た目調整が 17:45 の国内切り抜きにも波及する |
| 尺・CTA | `clip.viral_sources.output` | 国内用の `min_duration_sec: 30` で 10〜25 秒のバイラルが全滅する |
| 説明欄・タグ | `clip.viral_sources.metadata` | 「▼ この切り抜きの本編はこちら」が Reddit 投稿を指して意味が通らない |

スロットとエンジンの紐付けは `autopilot.schedule.times[].engine`
（`api_channel_autopilot` が `generate_clip(engine=...)` に渡す）。
**20:45 スロットの `engine: "viral"` を消すと、海外枠が国内素材で回る。**

---

## 1. 何を作り足したか（既存資産との関係）

```
 調達          区間選定             レンダリング              投稿
  │              │                    │                     │
  ▼              ▼                    ▼                     ▼
viral_sources → engines/viral → renderer_overseas.py → youtube_uploader
  （新規）        （新規）        （新規・国内版と分離）      （既存）
                    │
                    ├─ asr.py        Whisper 書き起こし（新規）
                    └─ translate.py  Claude 日本語化＋安全判定＋再試行（新規）
```

| ファイル | 新旧 | 役割 |
|---|---|---|
| `backend/pipeline/clip_factory/viral_sources.py` | **新規** | Reddit / 手動URL からの調達と内容ゲート |
| `backend/pipeline/clip_factory/asr.py` | **新規** | faster-whisper でローカル書き起こし |
| `backend/pipeline/clip_factory/translate.py` | **新規** | Claude で日本語字幕・フック文・安全判定 |
| `backend/pipeline/clip_factory/engines/viral.py` | **新規** | 上3つを束ねる切り抜きエンジン |
| `backend/run_viral_clip.py` | **新規** | 手動実行・診断の入口 |
| `backend/tests/test_viral_clip.py` | **新規** | 内容ゲートとレイアウトの単体テスト |
| `backend/pipeline/clip_factory/renderer_overseas.py` | **新規** | 海外枠専用の縦型レンダラ。`renderer.py` とコードを共有しない |
| `renderer.py` | 既存 | 国内切り抜き（17:45）専用。**海外枠はここを一切通らない**。以前に足した縦長対応（`video_w` / `reserve_subtitles`）は既定値が従来挙動なので残してある |
| `pipeline.py` | 既存＋追記 | エンジン別の素材探索・`engine` 上書き・海外枠のメタ差し替え |
| `api_channel_autopilot.py` | 既存＋追記 | `schedule.times[].engine`（スロットごとのエンジン指定） |
| `sources.py` | 既存＋追記 | `source_url()` が YouTube 以外の出典 URL も返すように |
| `engines/__init__.py` | 既存＋追記 | `viral` エンジンを登録 |
| `segments.py` / `align.py` / `captions.py` / `acquisition.py` | 既存・無改造 | clip-lab 専用のまま |

**autopilot は既存の `gen_type: "clip"` 経路をそのまま使う**
（`api_channel_autopilot._run_clip_autopilot` → `clip_factory.generate_clip`）。
新しいスケジューラは足していない。

### NoimosAI を使わなかった理由

`clip.engine: "noimos"` は残っているが、このチャンネルでは使えない。

- `NOIMOS_API_KEY` が `backend/.env` に**未設定**（値が空）。キーが無いと
  `preflight` で落ちて `NoimosUnavailable` になる。
- 仮にキーがあっても、Noimos の切り抜き機能は「長尺1本を渡して縦型に切る」もの。
  今回の素材は元から 10〜60 秒なので**切り抜く必要が無い**。必要なのは
  「翻訳して字幕を焼く」で、そこは Noimos の documented な機能ではない。
- 実測で MP4 が返るかは未検証のまま（`engines/noimos.py` の冒頭コメント参照）。

キーが入って切り抜き能力が確認できたら、`clip.engine` を `noimos` にすれば
既存のエンジン差し替え口でそのまま乗る（`fallback_engine: "viral"` にしておくこと）。

---

## 2. 処理の流れ

```
1. 調達      viral_sources.acquire
             Reddit の top/day から動画投稿を集める
             → 内容ゲート①（NSFWフラグ・タイトル禁止語・block_communities）
             → 既出（viral_acquisition.json）を除外
             → スコア＋コメント数で並べる

2. 尺の確認  yt-dlp --dump-single-json で duration を実測（DLはしない）

3. 素材取得  yt-dlp で丸ごと落とす（数MB・数秒）

4. 書き起こし faster-whisper（ローカル・API不要・コスト0）
             VAD で無音を落としてから認識 → 幻聴（"Thanks for watching"）を除去

5. 区間決定  59秒以下ならそのまま全部。超える素材だけ発話が最も詰まった窓に絞る

6. ゲート②  書き起こしテキストに禁止語ゲート

7. 日本語化  Claude に一括で投げて
             ・各行の日本語字幕
             ・フック文（画面上部・全角28字以内）
             ・ゲート③（YouTubeガイドライン観点の可否判定）
             を同時に返させる

8. 焼き込み  renderer_overseas.render_clip（国内切り抜きとは別実装）
             上：フック帯／中：元映像／下：日本語字幕帯

9. 投稿      youtube_uploader（既存）。**レビューなし＝直接 public**
```

7 で Claude が失敗したら**スキップせず再試行**する（`TRANSLATE_MAX_ATTEMPTS = 3`、
待機は 4秒 → 8秒 の指数バックオフ）。429・529・タイムアウト・壊れた JSON はこれで
拾える。逆に「待っても直らない失敗」（キー未設定・認証エラー・残高不足・SDK 未導入）
は1回目で打ち切る — 3回待ってもスロットを塞ぐだけで結果は同じなので。

**重いものほど後ろ**に置いてある。Whisper と Claude が一番高いので、そこへ
辿り着く前に落とせるものは全部落とす。

---

## 3. 3段の内容ゲート

「ちょいエロ・面白」を狙う以上、**1本の事故でチャンネルが飛ぶ**。ゲートは3段。

| 段 | 場所 | 見るもの | 効かないもの |
|---|---|---|---|
| ① | `viral_sources.apply_gate` | Reddit の `over_18`、タイトルの禁止語、投稿元 | 映像そのもの |
| ② | `engines/viral.generate` | 書き起こしの禁止語 | 無音動画 |
| ③ | `translate.translate_clip` | Claude が文脈を読んで可否判定 | — |

- **既定のハードブロック（`viral_sources.HARD_BLOCK_PATTERNS`）は設定で消せない。**
  性的に露骨・未成年・暴力・性犯罪の語は、channel JSON の
  `block_title_patterns` を空にしても必ず併用される。
- `content_gate.allow_over_18` は **false のまま**にすること。r/NSFW 系の
  サブレディットを `subreddits` に足しても、これが false の間は1本も通らない。
- `content_gate.require_manual_review` は **false（2026-08-30 のユーザー決定）**。
  目視レビューを挟まず `publish_settings.default_privacy`（public）で直接公開する。
  つまり **①②③の機械ゲートだけが防波堤**になっている。
  true に戻すと、チャンネル既定が public でも private で上がる（`force_privacy`）。

> ⚠️ 権利について。元投稿者から個別に許諾を取る運用ではない（運営判断）。
> そのぶん説明欄には投稿ページURL・サブレディット名・投稿者名を必ず載せ、
> 削除要請の窓口を書いてある（`viral_sources.attribution_text`）。
> Content ID や権利者申立てのリスクはゼロにならないので、収益化は
> 実績が溜まってから判断すること。

---

## 4. 稼働手順（残る人の手）

`clip-lab` の autopilot は既に `enabled: true`（国内切り抜きが 17:45 で稼働中）。
YouTube チャンネルと OAuth も既存のものをそのまま使うので、**残る条件は
`ANTHROPIC_API_KEY` だけ**。入れば 20:45 スロットがそのまま回り始める。

### (1) `ANTHROPIC_API_KEY`（**必須**）

翻訳とフック文は Claude 固定（運用ルール：台本・テキスト生成は Claude、
OpenAI API は画像生成のみ）。2026-08-30 時点で `backend/.env` の値は**空**。

キーが無いときは翻訳を機械任せにせず**その日を落とす**（意味の通らない字幕が
付いた動画を公開する方が損害が大きいため）。代わりに依頼書が
`data/analytics/viral_translation_pending/<id>.json` に出るので、Claude Code の
セッションから `prompt` を読んで `result` に JSON を書けば、次の実行が続きから作る。

### (2) `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`（強く推奨）

**2026-08-30 実測の Reddit 事情（ここを知らないと必ずハマる）:**

| 経路 | 結果 |
|---|---|
| `https://www.reddit.com/r/<sub>/top.json` | ❌ 403（bot wall の HTML が返る。UA を名乗っても同じ） |
| `https://api.reddit.com/...` | ❌ 403 |
| `https://old.reddit.com/...json` | ❌ ログインへ 302 |
| `https://www.reddit.com/r/<sub>/top.rss` | ✅ 200（ただし連打すると 429） |
| `https://oauth.reddit.com/r/<sub>/top` | ✅ OAuth トークンがあれば 200 |
| **`yt-dlp` に投稿ページ URL を渡す** | ❌ `Account authentication is required` |
| **`https://v.redd.it/<id>/HLSPlaylist.m3u8`** | ✅ **認証なしで取れる（音声込み）** |

最後の2行が肝。**投稿ページを yt-dlp に渡してはいけない**。Reddit エクストラクタが
認証を要求して落ちる。動画の実体は v.redd.it の CDN にあり、そこは認証不要なので、
`media_url` には必ず HLS/DASH の直リンクを入れる（`_post_to_candidate` と
`fetch_subreddit_rss` の両方でそうしている。RSS 本文にも v.redd.it の ID が
埋まっているので拾える）。

- OAuth（https://www.reddit.com/prefs/apps で script アプリを1つ作る）を入れると
  スコア・NSFWフラグ・尺・`hls_url` が全部 API から取れる。**本番はこれ。**
- 無いと RSS 経路に落ちる。動画は落とせるが **スコアと NSFW フラグが取れない**
  （一次ゲートが1つ効かない状態）。しかも 429 が頻発するので
  `request_interval_sec: 4.0` ＋3回まで待って再試行で凌いでいる。
  OAuth を入れたら 1.0 に戻してよい。
- RSS 経路では画像投稿が大半を占める（実測: r/funny の top 12 件中、動画は2件）。

### (3) YouTube チャンネルと OAuth → **不要**

`clip-lab` に同居させたので、チャンネル作成も OAuth 認可も要らない
（`UCbWZ5quEFE2VpHPh5TGyPCw` / `data/youtube_tokens.db` の既存トークンを使う）。
20:45 は既存チャンネル（clip-lab 17:45 / clip-fukada 20:00 / clip-kaneko 20:30）と
重ならない枠。

---

## 5. 使い方

```bash
cd /Users/ayukiyamazaki/Developer/youtube-factory

python3 backend/run_viral_clip.py --check      # 依存・認証の診断
python3 backend/run_viral_clip.py --acquire    # 調達とゲート判定だけ（DLしない）
python3 backend/run_viral_clip.py --dry-run    # 翻訳まで（レンダリングなし）
python3 backend/run_viral_clip.py              # 1本生成（投稿なし）
python3 backend/run_viral_clip.py --upload     # 生成して投稿（public）

# 対象は既定で clip-lab。エンジンは常に viral を明示して呼ぶので、
# 同じチャンネルの 17:45 枠（国内切り抜き）とは干渉しない。

# TikTok / Instagram / X の個別URLを手動キューに積む（次回の実行で拾う）
python3 backend/run_viral_clip.py --add-url "https://www.tiktok.com/@x/video/123"
```

REST からも既存の口がそのまま使える:

```
POST /api/clips/generate  {"channel_id": "clip-lab", "count": 1, "upload": false}

⚠️ この口は engine を渡せないので clip.engine（local＝国内切り抜き）で走る。
   海外枠を回すなら run_viral_clip.py か 20:45 の autopilot スロットを使うこと。
```

テスト:

```bash
cd backend && python3 -m unittest tests.test_viral_clip -v
```

---

## 6. 設定の勘所（`data/channels/clip-lab.json` の `clip.viral_sources`）

**海外枠の設定は全部 `clip.viral_sources` の下にある。** `clip.*` 直下の値は
17:45 の国内切り抜き用なので、海外枠を触るときにそちらを書き換えないこと。

| キー | 既定 | 意味 |
|---|---|---|
| `viral_sources.subreddits` | 8サブ | `unexpected` / `HolUp` が「ちょいエロ」枠。SFW の範囲で意外性のあるオチが集まる |
| `viral_sources.min_score` | 3000 | Reddit スコアの下限。RSS 経路では効かない（スコアが取れないため） |
| `viral_sources.max_duration_sec` | 180 | 調達側の足切り。これ超はコンピレーションが多い |
| `viral_sources.output.min_duration_sec` | 8 | **国内枠は 30。ここを国内値に揃えると短いバイラルが全滅する** |
| `viral_sources.output.max_duration_sec` | 59 | ショートの尺上限。超える素材は発話が濃い窓に絞る |
| `viral_sources.output.max_source_attempts` | 4 | ゲート落ちしたとき次の素材へ進む回数 |
| `viral_sources.asr.model` | `small` | 精度が要るなら `medium`、速さなら `base` |
| `viral_sources.layout_spec.source_crop_bottom_ratio` | 0.0 | 海外素材は切り落とさない（国内は 0.22） |
| `viral_sources.metadata` | — | タイトルのハッシュタグ・説明欄・タグ・カテゴリ（23=Comedy）の上書き |
| `content_gate.require_manual_review` | **false** | レビューなし＝直接 public。true にすると private で上がる |
| `content_gate.require_speech` | false | true にすると無音動画（映像オチ）を捨てる |
| `autopilot.schedule.times[].engine` | `viral` | 20:45 スロットのエンジン。**消すと海外枠が国内素材で回る** |
| `translate.TRANSLATE_MAX_ATTEMPTS` | 3 | 翻訳の試行回数（コード側の定数） |

---

## 7. 既知の落とし穴

- **`~/Desktop` の下にダウンロード先を置くな。** launchd 配下では TCC で ffmpeg の
  書き込みが無言でハングし、autopilot だけが静かに死ぬ（clip-lab で実測済み）。
  既定は `~/Movies/yf_viral_downloads`。
- **Whisper の言語判定は当てにしない。** ロボット音声や BGM 混じりだと英語を
  日本語と誤判定する（実測）。翻訳は Claude がテキストを見て判断するので実害は無いが、
  `segment.language` を分析に使うときは注意。
- **無音動画は普通にある。** `require_speech: false` の既定では字幕なし・フック文
  だけで作る。r/funny 系は映像で完結する投稿が多いのでこれで成立する。
- **レンダラを共有に戻すな。** 国内切り抜きと同じチャンネルに同居しているので、
  `renderer.py` を海外枠から呼ぶと 17:45 の見た目まで動く。分離は
  `tests/test_viral_clip.RendererSeparationTest` で見張っている。
- **無音動画では字幕帯を確保しない。** `render_clip` は字幕が1行も無いとき
  `reserve_subtitles=False` でレイアウトを組み直し、映像を大きく置く。
  サムネ側にも同じ値を渡さないと本編とサムネで映像の位置がズレる。
- **同じ投稿を二度作らない仕組みは `data/analytics/viral_acquisition.json`。**
  採用も不採用も記録するので、毎日同じ NSFW 投稿にダウンロード帯域を使わない。
  作り直したいときはこのファイルから該当エントリを消す。
- **`data/` を消すな。** 調達履歴・翻訳依頼書もここにある。
