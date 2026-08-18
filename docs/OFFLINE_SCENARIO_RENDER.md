# Anthropic API を使わない動画生成ワークフロー

`ANTHROPIC_API_KEY` が失効している間も動画を作り続けるための手順。
シナリオ本文だけを Claude（Claude Code のセッション自身など）が直接書き、
レンダリングはローカルのコマンドで実行する。

## なぜ動くのか

パイプラインのうち LLM を必要とするのは**シナリオ生成だけ**。
`pipeline/video_generator.py` の `generate_all()` は Anthropic を一切呼ばない。

| 工程 | 依存 | APIキー |
|---|---|---|
| シナリオ生成 | Anthropic / OpenAI | ← ここだけ失効の影響を受ける |
| タイトル・説明文生成 | 純粋な文字列処理 | 不要 |
| 音声合成 | ローカル VOICEVOX (`http://localhost:50021`) | 不要 |
| 背景・図解画像 | `image_mode` 次第（`collect` なら Pexels） | Anthropic は不要 |
| サムネ・動画エンコード | Pillow / MoviePy / ffmpeg | 不要 |

つまりシナリオ JSON さえ手元にあれば、キーが死んでいても最後まで通る。

## 手順

### 1. シナリオ JSON を書く

`data/scenarios/<channel-id>/_<name>.json` に置く（`_` 始まりは自動生成分と区別するため）。

```json
{
  "title": "動画タイトル兼・出力フォルダ名",
  "video_title": "YouTube 用タイトル（省略時は title）",
  "theme": { "title": "...", "angle": "..." },
  "generated_by": "claude-direct",
  "short_scenario": [
    { "speaker": "ユイ", "text": "...", "expression": "happy", "mood": "bright" }
  ],
  "full_scenario": [ "... 長尺を作るときだけ ..." ],
  "thumb_info": {
    "hook_lines": ["サムネ1行目", "サムネ2行目"],
    "subtitle": "...",
    "tagline": "..."
  }
}
```

書くときは対象チャンネルの `data/channels/<id>.json` に必ず目を通す:

- `short_format` … 行数・1行あたりの字数・合計字数・構成の規定
- `voice_style` … 一人称／語尾／`forbidden`（禁止語）
- `characters` … 使える `speaker` 名と `expressions`
- `content_policy` … 扱ってよい題材、`short_end_line.wording`
- `theme_priority` / `theme_seeds` … 題材の選び方

`data/scenarios/<id>/archive/_index.json` を見れば既出テーマが分かるので重複を避けられる。

### 2. 検証（レンダリングしない）

```bash
python3 backend/run_scenario_render.py \
  -c 2ch-matome \
  -s data/scenarios/2ch-matome/_claude_kenmei.json \
  --dry-run
```

行数・合計字数・禁止語・未定義スピーカーを `short_format` と突き合わせて警告を出す。

### 3. レンダリング

```bash
# VOICEVOX が起動していること（起動確認）
curl -s -m 3 http://127.0.0.1:50021/speakers > /dev/null && echo UP

python3 backend/run_scenario_render.py \
  -c 2ch-matome \
  -s data/scenarios/2ch-matome/_claude_kenmei.json
```

主なオプション:

| オプション | 既定値 |
|---|---|
| `--gen-type short\|full\|both` | `autopilot.gen_type` → `short` |
| `--duration <秒>` | `defaults.target_duration` |
| `--output-dir <path>` | `~/Desktop/動画出力用/<title>/` |
| `--prefix <str>` | `<channel>_<gen_type>_<unixtime>` |
| `--dry-run` | 検証のみ |

出力先に動画・サムネ・説明文・`_run_meta.json` が揃い、
`data/scenarios/<id>/archive/` にもシナリオが自動アーカイブされる（テーマ重複判定に効く）。

### 4. 投稿

このスクリプトはレンダリングまで。アップロードは既存の
`backend/upload_short_from_meta.py` など従来の経路を使う。

## 注意点

- **`assets/characters/<dir>/` に立ち絵が無いチャンネルは立ち絵なしで描画される**（エラーにはならない）。
  `characters.<名前>.dir` が指すディレクトリに `normal.png` などを置くと反映される。
- **`image_mode: "collect"` は実写を拾ってくる。** チャンネルによっては
  `content_policy` の「実在人物の写真・企業ロゴを使わない」に抵触しうるので、
  出来上がりのフレームを確認すること。
- BGM は `data/channels_assets/<channel>/bgm/` に音源が無ければ黙ってスキップされる。
- API キーが復旧したら通常の autopilot に戻せばよい。このスクリプトは並存しても副作用がない。
