---
name: chatgpt-image-worker
description: youtube-factory の画像生成キューを、ChatGPT のチャンネル専用スレッドで 生成→目視チェック→修正 のループを回して処理する。「画像キューを回して」「サムネ画像を作って」「pending の画像依頼を処理」で発動。Claude がプロンプト設計と品質判定を持ち、ChatGPT はレンダリング基盤として使う。
---

# ChatGPT 画像キューのワーカー

`backend/pipeline/chatgpt_image_bridge.py` が積んだ画像依頼を処理する。
**ChatGPT は DALL-E を動かすレンダリング基盤**で、プロンプト設計も品質判定も
こちら（Claude）が持つ。仕組みの全体像は `docs/CHATGPT_IMAGE_BRIDGE.md`。

## 絶対に守ること

- **OpenAI Images API を叩かない。** コードからも消してある。
- **1チャンネル = 1スレッド固定。** 依頼の `thread_url` を必ず使う。
  毎回新しい会話を開くと、ChatGPT 側に溜まった文脈も、ユーザーが横から入れた
  修正指示も全部消える。それを消さないことがこの仕組みの目的。
- **スレッド URL が未登録のチャンネルは、勝手に新規スレッドを作らずユーザーに聞く。**
  URL の正は `data/channels/<ch>.json` の `image_generation.chatgpt_thread_url`。
- **画像を見ずに採用しない。** 必ずスクリーンショットで確認してから `deliver`。

## 手順

```bash
python3 scripts/image_bridge.py list        # pending を見る
python3 scripts/image_bridge.py show <id>   # 依頼の詳細とスレッド URL
```

依頼ごとに:

1. `show <id>` の `thread:` を Claude in Chrome で開く。未登録なら止めて聞く。
2. `python3 scripts/image_bridge.py prompt <id>` の文面を **そのまま** 送る。
   要約したり書き換えたりしない（依頼側が構図・禁止事項を細かく指定している）。
3. 生成が終わったら **スクリーンショットを撮って自分の目で確認する。**
4. 下のチェックリストで判定する。
   - NG → `reject <id> "<何がダメか>" --revision "<どう直すか>"`
     依頼は pending のまま残り、`prompt <id>` が修正指示に変わる。
     **同じスレッド**にそれを投げて 3 へ戻る。**往復は3回まで**。
   - OK → 画像をダウンロードして
     `deliver <id> <パス> --qc "<何を見て OK にしたか>"`
5. 3往復してもダメなら `fail <id> "<理由>"` で落とす。
6. 最後に `python3 scripts/image_bridge.py status` を報告する。

## 品質チェックリスト

`purpose` ごとに見るところが違う。**1つでも×なら reject。**

**共通**
- 画像内に文字・数字・ロゴ・透かしが入っていないか（プロンプトで禁止している）
- 破綻（指が6本、顔が崩れている、左右非対称の目）が無いか
- 依頼の題材と実際に描かれたものが合っているか（別物を描く事故が多い）

**`thumbnail_background`（サムネ背景 1536x1024 → 1280x720）**
- 16:9 で切っても主役が切れないか（中央〜上部に寄っているか）
- **下部 25% が空いているか。** ここに日本語の大きい文字を重ねる
- スマホの一覧サイズまで縮めても何の画か分かるか（＝主役が大きいか）
- ハイコントラストか。全体が同じ明度だと文字が乗らない

**`illustration`（解説イラスト）**
- 台詞の内容を**説明できている**か。ただの雰囲気絵になっていないか
- 図解として読めるか（矢印・対比・大小が意味を持っているか）

**`channel_icon` / `channel_branding`**
- 48px の円に縮めて成立するか。要素が1つに絞れているか
- 実在人物の顔、既存 IP のキャラ（ポケモン等）が写り込んでいないか

**`character_sprite`**
- 背景がマゼンタ単色で、グラデ・影・テクスチャが乗っていないか（後で抜くため）
- 髪の外側やアクセサリに背景色が食い込んでいないか

## reject の書き方

`--revision` は**次にスレッドへ送る文そのもの**になる。曖昧に書かない。

- ❌ `--revision "もっと良くして"`
- ✅ `--revision "画面右下に写っている英字のロゴを完全に消して。他は変えないで"`
- ✅ `--revision "被写体が小さすぎる。顔が画面の縦40%を占めるまで寄って"`
- ✅ `--revision "下25%に岩の模様が入っていて文字が乗らない。そこは暗いボケた背景にして"`

## 補点

- 採用すると `data/image_requests/cache/<prompt_hash>.png` に入り、**次に同じ
  プロンプトが来たらパイプラインが即座にそれを使う**。同じ依頼を二度処理しなくてよい。
- 同一プロンプトの重複依頼は自動でまとめられている（`x2` は再依頼回数）。
- `purpose` の一覧: `thumbnail_background` / `illustration` / `channel_icon` /
  `channel_branding` / `character_sprite` / `thumbnail_v4`。
