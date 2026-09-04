# 画像生成を ChatGPT のブラウザスレッドへ移した（2026-09-04）

## なぜ変えたか

画像生成は `gpt-image-1` を **OpenAI API で直叩き**していた。これには2つ問題があった。

1. **ユーザーが横からプロンプトを直せない。** API は毎回まっさらな1回きりの呼び出しなので、
   「もっと暗く」「顔を大きく」「この構図はやめて」といった指示が積み上がらない。
   結果としてサムネの品質が**ずっと同じところで止まっていた**。
2. **投稿パイプラインが API の都合で止まる。** 2026-09-03 18:49 の 429（レート上限）で
   `clip-kaneko` 20:30 枠が落ちている。billing hard limit で `gpt-image-1` が丸ごと
   使えなくなった時期もある（残タスク 10）。

移行後は **ChatGPT の Web UI スレッド**で画像を作る。チャンネルごとに1本の会話を維持し、
そこにパイプラインの依頼も、ユーザーの修正指示も、同じ流れで積む。
**ユーザーがそのスレッドを開いて直接書き込めば、次の生成からその文脈が乗る。**

台本などのテキストは Claude が本命（`pipeline/claude_client.py`）。
方針の切り替えは `pipeline/openai_policy.py` 1箇所で決まる。

## 仕組み

```
  autopilot / 手動スクリプト
        │  request_image(prompt, size, channel_id)
        ▼
  data/image_requests/cache/<prompt_hash>.png ── あればここで即返る（納品済み）
        │ なければ
        ▼
  data/image_requests/pending/<req_id>.json    ── 依頼をキューに積んで **待たずに** None
        │                                          （呼び出し側は Pillow 等にフォールバック）
        ▼
  Claude in Chrome を持つ Claude セッション（ワーカー）
        │  ChatGPT の当該スレッドにプロンプトを送る → 画像をダウンロード
        ▼
  scripts/image_bridge.py deliver <req_id> <落とした画像>
        │
        ▼
  cache/<prompt_hash>.png へ格納 → **次回の同一プロンプトで即ヒット**
```

要点は「**パイプラインは絶対に待たない**」こと。autopilot は無人で回るので、
画像が来るまでブロックすると投稿枠を落とす。初回は繋ぎ（Pillow 図解 / グラデ背景）で出し、
納品されたら次の生成から本物に差し替わる。

同期的に欲しい手動スクリプトは `generate_or_queue()` を使い、未納品なら
`chatgpt_image_bridge.Queued` が飛ぶ。**1回目で全部キューに積む → まとめて処理 →
もう一度実行するとキャッシュヒットで全部揃う**、という2パス運用になる。

## ディレクトリ

`data/image_requests/`

| パス | 中身 |
|---|---|
| `threads.json` | チャンネル ID → ChatGPT スレッド URL。`_default` は未登録チャンネルの受け皿 |
| `pending/<id>.json` | 未処理の依頼（プロンプト・サイズ・用途・チャンネル） |
| `delivered/<id>.json` | 納品済みの依頼メタ |
| `failed/<id>.json` | 処理できなかった依頼（理由つき）。TTL 7日超過の pending もここへ |
| `images/<id>.png` | 納品された画像そのもの |
| `cache/<prompt_hash>.png` | プロンプト+サイズのハッシュ引き。**再生成の即時ヒットはここ** |

同じ (prompt, size) の依頼が既に pending にあれば積み直さない（`request_count` が増えるだけ）。
autopilot が毎日同じプロンプトを投げてもキューは膨らまない。

## 使い方

### 1. チャンネルのスレッドを登録する（最初に1回）

ChatGPT で「このチャンネルのサムネを作るスレッド」を新規に1本作り、その URL を登録する。

```bash
python3 scripts/image_bridge.py thread set scp-lab https://chatgpt.com/c/xxxxxxxx
python3 scripts/image_bridge.py thread set _default https://chatgpt.com/c/yyyyyyyy
python3 scripts/image_bridge.py thread get scp-lab
```

**このスレッドがユーザーの介入点。** 「今日から背景はもっと暗く」「文字は入れるな」等を
ユーザーが直接書き込むと、以降そのスレッドで生成される画像に効く。

### 2. キューを見る

```bash
python3 scripts/image_bridge.py status      # 件数とスレッド一覧
python3 scripts/image_bridge.py list        # pending の一覧
python3 scripts/image_bridge.py show <id>   # ChatGPT に貼るプロンプト全文
python3 scripts/image_bridge.py show <id> --prompt-only
```

### 3. 処理して納品する（Claude in Chrome セッションの仕事）

`.claude/skills/chatgpt-image-worker/SKILL.md` に手順がある。要約:

1. `list` で pending を取る
2. 依頼の `thread_url` を Claude in Chrome で開く（未登録なら `_default`、それも無ければ人間に聞く）
3. `show <id> --prompt-only` のプロンプトをそのスレッドに送る
4. 出てきた画像をダウンロードする
5. `python3 scripts/image_bridge.py deliver <id> <落としたファイル>`
6. 作れなかったら `fail <id> "理由"`（コンテンツポリシー拒否など）

### 4. 掃除

```bash
python3 scripts/image_bridge.py gc          # TTL(7日)超過の pending を failed へ
```

## 環境変数

| 変数 | 既定 | 意味 |
|---|---|---|
| `IMAGE_BRIDGE` | `1` | ブリッジの有効/無効。`0` にすると従来の API 直叩きに戻る（緊急退避） |
| `IMAGE_BRIDGE_WAIT_SECONDS` | `0` | 依頼後に納品を待つ秒数。**0＝待たない**（autopilot 用） |
| `IMAGE_BRIDGE_TTL_DAYS` | `7` | pending の寿命 |
| `IMAGE_BRIDGE_DIR` | `data/image_requests` | キューの置き場 |
| `OPENAI_IMAGE` | `0` | `1` で画像 API 直叩きを明示許可（原則使わない） |
| `OPENAI_TEXT` | `1` | `0` でテキストの OpenAI 退避口も塞ぐ。**`ANTHROPIC_API_KEY` を入れたらこれを 0 にする** |

## 移行した箇所

| ファイル | 内容 |
|---|---|
| `backend/pipeline/video_generator.py` | `_call_openai_image()` がブリッジ経由に。`OPENAI_API_KEY` の有無で判定していたイラスト生成のゲート4箇所を `_image_generation_available()` に置換 |
| `backend/pipeline/thumbnail_generator.py` | 背景生成 `generate_background()` がブリッジ経由。未納品時は繋ぎのグラデ背景を描いてサムネ生成自体は通す。デザインブリーフは **Claude → GPT → ローカル機械生成** の順に落ちる（`OPENAI_API_KEY` 不在でもう落ちない） |
| `backend/api_phase5.py` | イラスト試作・サムネ生成 API の `OPENAI_API_KEY` 必須チェックを撤去。未納品時は 202 でスレッド URL を返す |
| `gen_thumbs_v4.py` / `gen_thumbs_v4_all.py` | `generate()` がブリッジ経由（未納品は `Queued`） |
| `gen_channel_icons.py` | `generate_image()` がブリッジ経由 |
| `backend/scripts/setup_channel_branding.py` | `_gen_image()` がブリッジ経由 |
| `backend/scripts/generate_character_sprites.py` | `_generate()` がブリッジ経由。ChatGPT では `background=transparent` が使えないので、プロンプトでマゼンタ単色背景を指定して後段で抜く |

**未移行（意図的）**: `scripts/gen_wrinkly_fingers.py` / `scripts/gen_morning_height.py` /
`scripts/regen_wrinkly_thumbnail.py` / `scripts/expand_rain_smell*.py` は
公開済み動画1本のために書かれた過去の単発スクリプト。実行する予定が無いので触っていない
（実行すると従来どおり `OPENAI_API_KEY` を要求する）。

## テキスト側の残件

`ANTHROPIC_API_KEY` が `backend/.env` で**コメントアウトされたまま**なので、台本生成は
現状 OpenAI が本番経路になっている（`auto_scenario/generator.py` は GPT と Claude の
デュアル生成だが、Claude 側がキー不在で常にスキップされている）。
ここを塞ぐと全チャンネルの生成が止まるため、`OPENAI_TEXT` の既定は `1` のまま。

**キーを入れたら `OPENAI_TEXT=0` にすること。** それで OpenAI 依存はゼロになる。
