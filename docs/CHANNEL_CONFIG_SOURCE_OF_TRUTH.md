# チャンネル設定の単一の真実 — `data/channels/`

最終更新: 2026-09-01

## 結論

**`data/channels/<id>.json` が master of record。ここだけ更新すればよい。**

`data/channels_orchestrator/<id>.json` は 2026-09-01 から
`../channels/<id>.json` への相対 symlink になっている。実体は1つしか無いので、
**どちらのパスに書いても同じファイルに届き、乖離は起こりえない。**

## なぜ2つあったのか / 何が壊れていたか

`channels_orchestrator/` は別リポジトリの `ai-orchestrator` 用に置かれたミラー
だったが、実際には**どこからも読まれていなかった**:

- `backend/` 配下は例外なく `data/channels/` を見ている
  （`ChannelManager` / `post_upload` / `auto_comment` / `playlist_manager` /
  `shorts_length_guard` / `youtube_analytics` / `series_counter` /
  `description_blocks` / `run_daily_pdca` ほか）
- 別リポジトリの `ai-orchestrator` にも `channels_orchestrator` の参照は無い
- 書いていたのは `scripts/apply_*_2026MMDD.py` 系の PDCA 反映スクリプトだけで、
  これらが `DIRS = [channels, channels_orchestrator]` の形で両方に書いていた

「両方に書く」運用は、片方だけに当たる事故を必ず生む。実際に起きたもの:

| 日付 | 事故 |
|---|---|
| 2026-08-23 | `theme_blacklist` が daily-science で 33件 vs 22件に乖離 |
| 2026-08-30 | `applied_changes` の target は両方と書いてあるが channels 側にしか当たっていない変更があった |
| 2026-08-31 | **2ch-matome の `theme_blacklist` +4件 と `theme_seeds` -5件 が orchestrator 側にしか当たらなかった。** master 側は公開済みテーマを seeds に残したままで、再投稿が起きうる状態だった（2026-09-01 に master へ反映済み） |

symlink 化の直前の実体は `data/channels_orchestrator_pre_symlink_20260901/` に
退避してある。orchestrator 側にしか無かった値を後から追う必要が出たらここを見る。
そのときの全差分は `data/reports/2026-09-01/channel_config_divergence.txt`。

## 運用ルール

1. **チャンネル設定の変更は `data/channels/<id>.json` にだけ書く。**
   新しく反映スクリプトを書くときも `DIRS` に2つ並べない。
2. 変更後は **バックエンドを再起動する**。稼働中の `ChannelManager` は
   `_raw` をメモリに保持しているので、ファイルを書いただけでは効かないうえ、
   サーバ側の保存とぶつかると書いた内容が消える。

   ```bash
   launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend
   ```

   稼働中サーバの状態を壊さずに更新したいなら、`run_daily_pdca.py` と同じく
   HTTP API 経由（`PUT /api/channels/{id}` 等）で更新する。
3. 乖離していないことの確認:

   ```bash
   python3 scripts/unify_channel_configs.py --check   # 差分があれば exit 1
   ```

   何らかの理由で symlink が実ファイルに戻ってしまったら
   `--apply` で張り直す（実体は退避されてから置き換わる）。

## 補足: `production.*` キーについて

orchestrator 側にだけ `production.tool` / `production.pipeline` /
`production.modules` / `production.auto_publish` があったが、
リポジトリ内にこれを読むコードは存在しない（grep 済み）。symlink 化で消えるが、
影響は無い。値は上記の退避ディレクトリに残っている。
