# MEMORY UPDATE 2026-09-06（指揮者・朝）

## 最重要：サムネイルが全チャンネルで1枚も適用されていない

YouTube Data API が `403 forbidden` を返し続けている。

```
The authenticated user doesn't have permissions to
upload and set custom video thumbnails.
```

- 影響: **86動画 / 失敗ログ 365回**、moviepy系6ch全部（scp-lab 14・pokemon-lab 11・2ch-matome 11・company-facts 11・yokai-watch 10・fake-paper 10）
- `gen_thumbs_v4_all.py` が生成したサムネは**1枚も反映されず**、YouTube の自動切り出しフレームで公開されている
- 原因はコードではなく**アカウント未認証**。カスタムサムネイルには YouTube の本人確認が必要
- 対処: 各チャンネルで https://www.youtube.com/verify を実施する。**ユーザー本人が行う必要がある**（Claudeは実行しない）
- 制約「サムネ品質最優先改善」は、この403が解けるまで前提が成立しない

## データ状況

- `video_metrics` 最終取得 2026-09-05 23:15 JST。`channel_metrics` は 09-02 までしか確定していない
- YouTube Analytics の 48〜72時間遅延により **09-04/09-05 公開分は views=0**。当日評価に使ってはいけない
- 09-01/09-02 の全ch急減も遅延アーティファクトであり、実際の失速ではない

## 分析で判明したこと

### 1. 登録転換率に4.5倍の格差（至上目標に直結）

published_at>=2026-08-07、登録/千再生：

| ch | 登録/千再生 | 総再生 | 登録者増 |
|---|---|---|---|
| company-facts | **0.76** | 38,343 | 29 |
| scp-lab | 0.63 | 31,702 | 20 |
| daily-science | 0.62 | 27,546 | 17 |
| pokemon-lab | 0.26 | 30,563 | 8 |
| yokai-watch | **0.20** | 29,359 | 6 |
| 2ch-matome | **0.17** | 35,663 | 6 |

**yokai-watch が最大の機会損失**。再生2000超で登録0の動画が上位を占める（鬼の元ネタ2346・のっぺらぼう2251・ふじのやま1952、いずれも登録0）。再生は取れている。転換だけが死んでいる。

### 2. 再生位置0.1→0.3で全ch崩落。中盤を保てるのは2chだけ

平均視聴維持カーブの 0.3→0.7 減衰pt：

- company-facts **16.6pt**（最良）/ fake-paper 18.9 / akashic 21.6 / pokemon 22.0 / scp 23.6 / yokai 25.0 / daily-science 25.2 / 2ch 28.0
- ※fake-paper は 0.1→0.3 で 66.9pt 落ちた後の残骸なので減衰ptが小さく見えるだけ。絶対値は最下位

**同尺比較が決定的だった**（実測尺 = 平均視聴時間 ÷ 平均視聴率）：

| ch | 中央尺 | 平均維持率 | 4行目のルール |
|---|---|---|---|
| daily-science | 36.1秒 | **61.3%** | たとえ話で自分ゴト化・新情報を足さない |
| pokemon-lab | 36.7秒 | 44.4% | 意外な展開（新情報を追加） |
| scp-lab | 34.6秒 | 45.6% | 異常性の核心＋侵食（新情報を追加） |
| yokai-watch | 33.3秒 | 47.9% | 恐怖の転換（新情報を追加） |

ほぼ同じ尺で16pt差。差分は4行目の情報設計のみ。**中盤の離脱は「4行目で新しい事実を足すことによる認知負荷」が主因**という仮説に至った。

### 3. 尺は律速ではない

尺帯別では 20-26秒帯が維持率60.1%・中央再生1144で最良だが、**company-facts は中央55.7秒で維持57.7%**（同尺帯平均40.1%を大きく上回る）。短くすれば勝てるのではなく、構成が効いている。

ただし全ch config の `target_seconds_hint=26` に対し実測は 33〜37秒（company-facts は55.7秒）で、**設定と実態が30〜60%乖離**している。

### 4. 年齢正規化トレンド（公開後3日時点の中央再生）

8月中旬 1100〜1375 → 8月下旬以降 800〜900 へ約25%低下し、以降2週間は横ばい。
投稿本数は 09-04で26本・09-05で28本まで増やしたが、1本あたりの品質は維持できている。

## 本日のコンフィグ変更（実装済）

バックアップ: `data/channels/{scp-lab,pokemon-lab,yokai-watch}.json.bak_pdca_20260906_orch`
※ `data/channels_orchestrator/*.json` は `../channels/*.json` へのシンボリックリンクなので同時反映される。

1. **scp-lab / pokemon-lab / yokai-watch**: `short_format.structure` の4行目を
   「新情報追加型」→「**比較・言い換えで自分ゴト化（新情報の追加は禁止）**」に変更。
   旧文は `short_format._prev_structure_20260906.line4` に保存
2. **pokemon-lab**: `total_chars` 175-225 → **170-205**（実測尺の超過是正）
3. **yokai-watch**: `theme_queue` からコンセプト外2件（「動画作りの裏に潜む妖怪の影」「半導体と妖怪の関係？」= trend_scanner由来）を除去し、実測の勝ち筋「〇〇の正体／元ネタが怖すぎる」型5件を先頭に補充（24件）

**反証条件: 2026-09-13 に3chの 0.3→0.7減衰pt を再測定。09-06時点（scp 23.6 / pokemon 22.0 / yokai 25.0）を下回らなければ仮説を棄却し4行目を元に戻す。**

## 意図的にやらなかったこと

- **cta_position を触っていない。** 2026-09-04 に yokai-watch と pokemon-lab で after_hook→end の A/B が始まっており、**反証期限は 2026-09-11**。ここを今日動かすと4行目の介入と交絡して両方測れなくなる。登録転換の最大の構造的差分はおそらくCTA位置（scp-lab は after_hook のまま 0.63、同ジャンルの yokai は end で 0.20）なので、09-11 の判定を必ず待つこと
- **投稿時間を触っていない。** `posting_optimizer_cache` の推奨枠は sample_size が1〜3本しかなく、boost_percent 100%超も単一動画のバズに引きずられた値。各枠5本以上積み上がるまで再評価しない
- **手動 trigger を打っていない。** APScheduler が自律稼働中で、06:15〜09:30 に 2ch-matome / daily-science / company-facts / pokemon-lab / clip-kaneko / akashic-librarian / clip-animal が発火済み。手で叩くと重複投稿になる。config変更は 10:04 に全ch の theme_queue へ反映済みで、本日の残枠（yokai 11:15・scp 12:15・pokemon 14:15 以降）から新ルールが適用される
- **2ch-matome の構成を触っていない。** 登録転換は最下位（0.17）だが、3〜5行目のボケ積み上げがチャンネルの核であり、他chと同じ4行目ルールを当てると形式が壊れる
- **fake-paper / socio-rx / clip-\* を触っていない。** 指揮者スキルのスコープ外

## その他の障害（スコープ外・要対応）

- `clip-lab`: autopilot 失敗。`ANTHROPIC_API_KEY 未設定` で viral 翻訳エンジンが3回試行後に中止。依頼書が `data/analytics/viral_translation_pending/viral_1w7j3u1.json` に残っている
- `clip-kaneko`: autopilot 失敗。「全ての元動画が切り抜き済み」= `clips_per_video` を上げるか元動画の追加が必要

## 成果物

`reports/youtube_analysis_20260906.xlsx`（サマリー / チャンネル別詳細 / 動画別パフォーマンス / 改善アクション / トレンド）
