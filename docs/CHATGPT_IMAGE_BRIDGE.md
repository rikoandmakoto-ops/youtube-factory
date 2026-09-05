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

## 仕組み — Claude 主導の 生成 → チェック → 修正

ChatGPT スレッドは **DALL-E を動かすレンダリング基盤**としてだけ使う。
プロンプトの設計も品質の判定も Claude が持つ（bot 任せにしない）。

```
  autopilot / 手動スクリプト
        │  request_image(prompt, size, channel_id)
        ▼
  cache/<prompt_hash>.png ── あればここで即返る（採用済み）
        │ なければ
        ▼
  pending/<req_id>.json ── 依頼を積んで **待たずに** None
        │                    （呼び出し側は Pillow 等にフォールバック）
        ▼
  ┌── Claude in Chrome ─────────────────────────────────────┐
  │  1. そのチャンネル専用スレッドを開く（毎回同じ1本）      │
  │  2. `prompt <id>` の文面を送る                          │
  │  3. 出た画像を **スクリーンショットで確認**              │
  │  4. NG → `reject <id> "理由" --revision "修正指示"`      │
  │        → 同じスレッドに投げ直して 3 へ戻る               │
  │  5. OK → `deliver <id> <画像> --qc "見た点"`             │
  └─────────────────────────────────────────────────────────┘
        ▼
  cache/<prompt_hash>.png ── **次回の同一プロンプトで即ヒット**
```

要点は「**パイプラインは絶対に待たない**」こと。autopilot は無人で回るので、
画像が来るまでブロックすると投稿枠を落とす。初回は繋ぎ（Pillow 図解 / グラデ背景）で出し、
採用されたら次の生成から本物に差し替わる。

`reject` しても依頼は **pending のまま残る**。差し戻し履歴は `attempts` と `revisions` に
積み上がり、`next_prompt()` は2回目以降「直前の画像を、この指摘で直せ」という
**修正指示だけ**を返す（同じスレッドなので元の指定は文脈に残っている）。

同期的に欲しい手動スクリプトは `generate_or_queue()` を使い、未納品なら
`chatgpt_image_bridge.Queued` が飛ぶ。**1回目で全部キューに積む → まとめて処理 →
もう一度実行するとキャッシュヒットで全部揃う**、という2パス運用になる。

## 1チャンネル = 1スレッド固定

**スレッド URL は `data/channels/<ch>.json` の
`image_generation.chatgpt_thread_url` に保存する。**

```json
{
  "id": "scp-lab",
  "image_generation": {
    "chatgpt_thread_url": "https://chatgpt.com/c/xxxxxxxx",
    "note": "サムネ背景。共通ルールをスレッド冒頭で合意済み",
    "updated_at": "2026-09-04T17:00:00+00:00"
  }
}
```

チャンネル設定と同じ場所に置くことで、チャンネルを増やしたときの登録漏れが
コンフィグ差分として見える（`image_bridge.py missing` でも一覧できる）。

**毎回新しい会話を開いてはいけない。** ChatGPT 側に溜まった文脈も、
ユーザーが横から入れた修正指示も全部消える。それを消さないことがこの仕組みの目的。

`_default`（チャンネルに紐づかない依頼の受け皿）だけは設定ファイルが無いので
`data/image_requests/threads.json` に入る。チャンネル設定側が常に優先される。

## ディレクトリ

`data/image_requests/`

| パス | 中身 |
|---|---|
| `threads.json` | `_default` 専用。チャンネルのスレッドは `data/channels/<ch>.json` が正 |
| `pending/<id>.json` | 未処理の依頼（プロンプト・サイズ・用途・チャンネル） |
| `delivered/<id>.json` | 採用済みの依頼メタ（`attempts` に差し戻し履歴と採用判定が残る） |
| `failed/<id>.json` | 処理できなかった依頼（理由つき）。TTL 7日超過の pending もここへ |
| `images/<id>.png` | 納品された画像そのもの |
| `cache/<prompt_hash>.png` | プロンプト+サイズのハッシュ引き。**再生成の即時ヒットはここ** |

同じ (prompt, size) の依頼が既に pending にあれば積み直さない（`request_count` が増えるだけ）。
autopilot が毎日同じプロンプトを投げてもキューは膨らまない。

## 使い方

### 1. チャンネルのスレッドを登録する（チャンネルごとに1回だけ）

ChatGPT で「このチャンネルの画像を作り続けるスレッド」を1本作り、URL を登録する。

```bash
python3 scripts/image_bridge.py thread set scp-lab https://chatgpt.com/c/xxxxxxxx \
    --note "サムネ背景。共通ルールをスレッド冒頭で合意済み"
python3 scripts/image_bridge.py thread get scp-lab
python3 scripts/image_bridge.py missing     # 未登録のチャンネルを洗い出す
python3 scripts/image_bridge.py backfill    # ★ 登録したら必ず走らせる
```

> 🚨 **登録したら `backfill` を必ず走らせること。**
> 依頼は**キューに積まれた時点のスナップショット**なので、あとからスレッドを
> 登録しても既存 pending の `thread_url` は空のまま残り、ワーカーは宛先を
> 決められない。`backfill` は `channel_id` / `thread_url` を今の設定で貼り直す
> （`channel_id` が空の依頼は、プロンプト先頭の `art_style` が ch ごとに固有の
> 長文なので、そこから決定論的に復元する）。
>
> 09-05 にこれを踏んだ: 12ch 分の URL が **`image_generation` ブロックではなく
> トップレベル**の `chatgpt_thread_url` に書かれていて、読む側が見ていなかった。
> 加えてイラスト依頼側は `channel_id` を渡していなかった。結果、
> **設定にも依頼にも URL があるのに一度も配送されず、pending が 49件・delivered 0** に
> なった。読む側は旧置き場（トップレベル）も見るようにしてあるが、
> 書くときは必ず `image_bridge.py thread set` を使うこと（`set` は旧キーを畳む）。

スレッドを開いたら最初に共通ルール（16:9・文字を入れない・下部を空ける 等）を
一度伝えておくと、以降のプロンプトが短くて済む。

**このスレッドがユーザーの介入点。** 「今日から背景はもっと暗く」等をユーザーが
直接書き込むと、以降そのスレッドで生成される画像に効く。

### 2. キューを見る

```bash
python3 scripts/image_bridge.py status      # 件数・スレッド一覧・未登録チャンネル
python3 scripts/image_bridge.py list        # pending の一覧
python3 scripts/image_bridge.py show <id>   # 依頼の詳細＋次に送る文面
python3 scripts/image_bridge.py prompt <id> # 次に送る文面だけ
```

### 3. Claude が回す 生成 → チェック → 修正

`.claude/skills/chatgpt-image-worker/SKILL.md` に手順がある。要約:

1. `show <id>` で依頼とスレッド URL を確認する
2. Claude in Chrome でそのスレッドを開き、`prompt <id>` の文面を送る
3. 出た画像を**スクリーンショットで確認**して判定する
4. NG なら差し戻す。依頼は pending のまま残り、次の文面が修正指示に変わる

   ```bash
   python3 scripts/image_bridge.py reject <id> "文字が入っている" \
       --revision "画像内の文字・数字を完全に消して"
   ```

   → `prompt <id>` を**同じスレッド**に投げ直して 3 へ戻る（最大3往復が目安）
5. OK なら採用する

   ```bash
   python3 scripts/image_bridge.py deliver <id> ~/Downloads/xxx.png --qc "文字なし・下部空きOK"
   ```
6. 何度直してもダメなら落とす: `fail <id> "content policy で拒否された"`

### 4. 掃除

```bash
python3 scripts/image_bridge.py gc          # TTL(7日)超過の pending を failed へ
```

## 環境変数

| 変数 | 既定 | 意味 |
|---|---|---|
| `IMAGE_BRIDGE` | `1` | ブリッジの有効/無効。`0` にすると画像生成が丸ごと止まる（Pillow フォールバックのみ） |
| `IMAGE_BRIDGE_WAIT_SECONDS` | `0` | 依頼後に納品を待つ秒数。**0＝待たない**（autopilot 用） |
| `IMAGE_BRIDGE_TTL_DAYS` | `7` | pending の寿命 |
| `IMAGE_BRIDGE_DIR` | `data/image_requests` | キューの置き場 |
| `IMAGE_BRIDGE_CHANNELS_DIR` | `data/channels` | スレッド URL を読み書きするチャンネル設定の置き場 |
| `OPENAI_TEXT` | `1` | テキストの OpenAI 退避口。**Claude が使えるようになった時点で自動的に呼ばれなくなる**（明示的に塞ぐなら `0`） |

## 移行した箇所

| ファイル | 内容 |
|---|---|
| `backend/pipeline/video_generator.py` | `_call_openai_image()` は**ブリッジ専用になり、OpenAI API のコードごと削除**。`OPENAI_API_KEY` の有無で判定していたイラスト生成のゲート4箇所を `_image_generation_available()` に置換 |
| `backend/pipeline/thumbnail_generator.py` | 背景生成 `generate_background()` は**ブリッジ専用**（API 分岐を削除）。未納品時は繋ぎのグラデ背景を描いてサムネ生成自体は通す。デザインブリーフは **Claude → GPT → ローカル機械生成** の順に落ちる |
| `backend/api_phase5.py` | イラスト試作・サムネ生成 API の `OPENAI_API_KEY` 必須チェックを撤去。未納品時は 202 でスレッド URL を返す |
| `gen_thumbs_v4.py` / `gen_thumbs_v4_all.py` | `generate()` がブリッジ経由（未納品は `Queued`） |
| `gen_channel_icons.py` | `generate_image()` がブリッジ経由 |
| `backend/scripts/setup_channel_branding.py` | `_gen_image()` がブリッジ経由 |
| `backend/scripts/generate_character_sprites.py` | `_generate()` がブリッジ経由。ChatGPT では `background=transparent` が使えないので、プロンプトでマゼンタ単色背景を指定して後段で抜く |

**未移行（意図的）**: `scripts/gen_wrinkly_fingers.py` / `scripts/gen_morning_height.py` /
`scripts/regen_wrinkly_thumbnail.py` / `scripts/expand_rain_smell*.py` は
公開済み動画1本のために書かれた過去の単発スクリプト。実行する予定が無いので触っていない
（実行すると従来どおり `OPENAI_API_KEY` を要求する）。

## OpenAI Images API はコードから消した

`backend/tests/test_chatgpt_image_bridge.py::TestNoOpenAIImageCalls` が
`video_generator.py` / `thumbnail_generator.py` に `v1/images/generations` が
再び入らないことを監視している。

## テキスト側の残件

`ANTHROPIC_API_KEY` が `backend/.env` で**コメントアウトされたまま**なので、台本生成は
現状 OpenAI が本番経路になっている（`auto_scenario/generator.py` は GPT と Claude の
デュアル生成だが、Claude 側がキー不在で常にスキップされている）。
ここを塞ぐと全チャンネルの生成が止まるため、`OPENAI_TEXT` の既定は `1` のまま。

`openai_policy.direct_text_api_allowed()` は **Claude が使えるかを毎回見る**ので、
`ANTHROPIC_API_KEY` を入れた時点で OpenAI は呼ばれなくなる（環境変数の変更は不要）。
明示的に塞ぎ切りたいときだけ `OPENAI_TEXT=0`。
