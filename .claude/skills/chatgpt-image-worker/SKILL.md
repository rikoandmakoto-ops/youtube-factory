---
name: chatgpt-image-worker
description: youtube-factory の画像生成キューを ChatGPT のブラウザスレッドで処理する。「画像キューを回して」「サムネ画像を作って」「pending の画像依頼を処理」で発動。Claude in Chrome で ChatGPT の固定スレッドにプロンプトを送り、生成画像を回収して data/image_requests へ納品する。
---

# ChatGPT 画像キューのワーカー

`backend/pipeline/chatgpt_image_bridge.py` が積んだ画像生成の依頼を、
**ChatGPT の Web UI スレッド**で処理する。仕組みは `docs/CHATGPT_IMAGE_BRIDGE.md`。

## 絶対に守ること

- **OpenAI Images API を叩かない。** ブラウザの ChatGPT スレッド経由だけ。
  ユーザーが同じスレッドを開いて横からプロンプトを直せることが要件。
- **チャンネルごとに1本のスレッドを使い続ける。** 毎回新しい会話を開くと、
  ユーザーが積み上げた修正指示（「もっと暗く」等）が全部消える。
- **スレッド URL が未登録のチャンネルは、勝手に新規スレッドを作らずユーザーに聞く。**

## 手順

1. キューを見る

   ```bash
   python3 scripts/image_bridge.py list
   ```

2. 依頼ごとに:

   ```bash
   python3 scripts/image_bridge.py show <req_id>
   ```

   `thread:` の URL を確認する。未登録なら `_default` を試し、それも無ければ止めて聞く。

3. Claude in Chrome (`mcp__claude-in-chrome__*`) でそのスレッドを開き、
   `show <req_id> --prompt-only` のプロンプト全文をそのまま送る。
   **プロンプトを要約したり書き換えたりしない**（依頼側が構図・禁止事項を細かく指定している）。

4. 画像が出たら右クリック等でダウンロードし、パスを控える。

5. 納品する。

   ```bash
   python3 scripts/image_bridge.py deliver <req_id> ~/Downloads/xxxx.png
   ```

6. 作れなかったとき（コンテンツポリシー拒否・スレッドが開けない等）は理由を残して落とす。

   ```bash
   python3 scripts/image_bridge.py fail <req_id> "content policy で拒否された"
   ```

7. 最後に件数を報告する。

   ```bash
   python3 scripts/image_bridge.py status
   ```

## 補足

- 納品すると `data/image_requests/cache/<prompt_hash>.png` に入り、**次に同じプロンプトが
  来たときはパイプラインが即座にそれを使う**。だから同じ依頼を二度処理する必要はない。
- 同一プロンプトの重複依頼は自動でまとめられている（`x2` 等の表示は再依頼回数）。
- `purpose` で用途が分かる: `thumbnail_background` / `illustration` /
  `channel_icon` / `channel_branding` / `character_sprite` / `thumbnail_v4`。
