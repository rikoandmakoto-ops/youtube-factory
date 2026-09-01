# YouTube Factory 統合ナレッジベース

最終統合: 2026-08-27
出典: HANDOFF.md / pdca_summary_0710.md / pdca_summary_0822.md / pdca_summary_0823_night.md / pdca_summary_0824.md / 競合分析レポート.md

---

## A. 確定した運用ルール（絶対守るもの）

### 投稿ルール

- **ショートのみ・1日1本・チャンネルごとの固定スロット**（出典: HANDOFF.md §1）
- **投稿設定の変更は必ず実データ分析に基づく**（PDCA厳守）（出典: HANDOFF.md §1）
- **1リポジトリに複数タスクを並行させない**（必ずマージしてから終了）（出典: HANDOFF.md §1）
- **`data/` を消すな。** チャンネル設定・テーマキュー・PDCAメモリ・OAuthトークンが全部ここ。設定と実行結果が同居している（出典: HANDOFF.md §7）

### 台本生成ルール

- **台本はClaudeが自己生成**（OpenAI APIは `gpt-image-1`（画像生成）のみ）（出典: HANDOFF.md §5）
- **GPT台本はChatGPT Webスレッド経由**（API直叩き禁止）。理由: ユーザー（ザキ）が同じスレッドから横で介入・修正できるようにするため（出典: HANDOFF.md §5）
- **A/Bテスト:** 投稿時に `script_source` メタデータ（`"claude"` | `"gpt"`）を記録し、一定本数が溜まったらYouTube Analyticsで比較分析（出典: HANDOFF.md §5）

### 分析ルール

- **タイトル・演出の効果検証は必ずチャンネル内比較**（横断禁止）。横断集計では交絡が発生し見せかけの相関になる（出典: pdca_summary_0822 §2）
- **単純二群比較だけを根拠にした規則変更は禁止**。層別（チャンネル×公開月など）を標準手順にする。Simpsonのパラドックスの実例あり（出典: pdca_summary_0824 §4）
- **直近動画の維持率を額面通りに比較するな。** 維持率には成熟バイアスがあり、公開6日目まで上昇し続ける。維持率比較は「公開6日以上経過」に固定すること（出典: pdca_summary_0824 §3）

---

## B. 実証済みの知見（PDCAから得たファクト）

### 登録転換の予測子

- **高評価率が登録転換の最強予測子。** 成熟動画245本のch内中央値二分で、高評価率上位群の登録/1000再生は0.65、下位群は0.30（倍率2.16）。5chのうち4chで同方向（yokai 4.42倍 / scp 2.40倍 / daily 1.95倍 / 2ch 1.59倍）。四分位でもQ1→Q4で単調増加（0.29→0.83）（出典: pdca_summary_0824 §1）
- **ただし統計的弱点あり:** 登録者合計わずか126人、64.5%が登録者0。95%CIは1.43〜3.40と広い。因果の向きが不明（高評価も登録も同じ潜在変数の別の現れ）。分母が同じ再生数のため見かけの相関も混入。scp-lab依存（登録の53%）（出典: pdca_summary_0824 §1 独立検証）
- **維持率は監視項目に降格（停止ではない）。** ch内維持率四分位での再生数中央値は平坦（946/1015/976/973）で、リーチにも効いていない。並べ替え検定で維持率 p=0.23（否定されたのではなく検出力不足）（出典: pdca_summary_0824 §1）
- **維持率と登録転換の関係はチャンネルごとに符号が違う。** yokai 3.00倍 vs scp 0.95倍。登録者の過半を稼ぐscp-labで維持率が効いていない（出典: pdca_summary_0823_night §6）

### 維持率の注意点

- **維持率には成熟バイアスがある。** 同一動画の日次追跡で公開2日目48.5%→6日目55.6%まで上昇。APIの反映遅れも一部含む可能性あり（出典: pdca_summary_0824 §3）
- **全チャンネル共通の離脱ポイントは再生位置20%。** retention_curve実測で全chが20%地点でaudience_watch_ratio 1.0を割る。30%地点の残存: pokemon-lab 0.83（最良）/ scp-lab 0.64（最下位）（出典: pdca_summary_0822 §4）

### 動画尺

- **最適な動画尺はチャンネルごとに逆方向。** daily-science: 短いほど良い（24.8秒→59.0% > 32.8秒→52.8%）。yokai-watch: 長いほど良い（33.9秒→63.3% > 22.7秒→58.0%）。一律の尺設定は誤り（出典: pdca_summary_0822 §3）

### タイトル・CTR

- **ショートのCTRは最適化対象として筋が悪い。** フィード視聴がインプレッションに計上されないため、CTRという指標自体が実態を捉えていない（scp-labのimpressions 13,772に対し再生数は8万超）（出典: pdca_summary_0824 §5）
- **「なぜ」型タイトルのマイナスはSimpsonのパラドックス。** 単純二群では なぜ有0.42 < なぜ無0.54 だが、ch×公開月で層別すると なぜ有0.41 > なぜ無0.31 と逆転。7層すべてで有≧無。変更不要（出典: pdca_summary_0824 §4）
- **タイトル短縮は登録転換に悪影響なし。** 移行期のch内比較で短(≤45字) 0.73 対 長(≥60字) 0.42。高評価率も差なし。戻すな（出典: pdca_summary_0824 §6）
- **チャンネル横断のタイトル分析は交絡していた。** 「数字入り -340再生」「99%が知らない -200再生」等はch内比較で消滅または逆転（出典: pdca_summary_0822 §2）

### テーマ重複判定

- **テーマ重複判定に「ショート」語の偽陽性バグがあった（修正済み）。** `_keyword_overlap` が「ショート」(3文字=重み9)を話題語として数えていたため、無関係な2本が0.76（閾値0.62超）に達していた。修正後、実際の重複はdaily-scienceの1件のみ（出典: pdca_summary_0823_night §3）

### チャンネル特性

- **scp-labが登録者獲得の主力。** 30日純増37人は他4ch合計32人を上回る（全体の53〜54%）。1000再生あたり登録0.845人は2位の2.52倍。一方で平均再生765と下位（出典: pdca_summary_0822 §1, pdca_summary_0824 チャンネル数値サマリ）
- **2ch-matomeは維持率最高だが登録転換最低。** 維持率64.3%（全ch最高）なのに登録/1000再生0.21（全ch最低）。維持率が登録に効かないことの最もわかりやすい実例（出典: pdca_summary_0824 チャンネル数値サマリ）

### サムネイル

- **ショートサムネが全チャンネルでdaily-science固定だった（修正済み）。** `generate_short_thumbnail()` が `channel_dict` を受け取っておらず、バッジ文言・配色・キャラ全てハードコード。08-23に改修しch別の配色・バッジ・キャラが反映されるようにした（出典: pdca_summary_0823_night §1）

### その他の方法論的注意

- **video_metricsは1chあたり50本が上限。** `maxResults=50` により直近50本しか記録されない。窓が日々ずれるため日次差分は負値が出て意味を持たない（出典: pdca_summary_0823_night §5）

---

## C. チャンネル別の現在設定

### 投稿時刻（posting_optimizer_cache の実測ブーストに基づく変更済み値）

| チャンネル | 変更後の時刻 | 実測ブースト | 出典 |
|---|---|---|---|
| scp-lab | 09:00（主枠） | +20.0% | pdca_summary_0822 |
| daily-science | 17:00 | +26.2% | pdca_summary_0822 |
| pokemon-lab | 18:00 | +30.3% | pdca_summary_0822 |
| yokai-watch | 19:00 | +48.9% | pdca_summary_0822 |
| 2ch-matome | 18:00 | +26.3% | pdca_summary_0822 |
| company-facts | 17:00 | — | HANDOFF.md |
| clip-lab | 17:45 | — | HANDOFF.md |
| clip-fukada | 20:00 | — | HANDOFF.md |
| clip-kaneko | 20:30 | — | HANDOFF.md |

※ 全5ch `auto_optimize_schedule = false`（実測ベースの設定が自動再最適化で上書きされるのを防ぐため）（出典: pdca_summary_0822）

### 台本の尺（short_format.total_chars）

| チャンネル | 設定値 | 目標尺 | 出典 |
|---|---|---|---|
| scp-lab | 230-290 | 22秒 | pdca_summary_0822 |
| daily-science | 260-300（240→260に復帰） | 25秒 | pdca_summary_0824 |
| yokai-watch | 320-390 | 34秒（延長） | pdca_summary_0822 |

daily-scienceの `total_chars_min` は08-23に維持率目的で240に短縮されたが、維持率の根拠が消滅したため08-24に260に復帰（出典: pdca_summary_0824）。

### CTA設定

全チャンネルのCTAを**高評価優先**に書き換え済み（08-24実施）。従来は全chがチャンネル登録のみを求めており「高評価」の語が一度もなかった。2ch-matomeは8行目CTA自体が存在しなかったため新設（共感→高評価→答えはコメントへ）。`extra_rules` の先頭に「8行目には必ず『高評価』を入れ、登録より先に置く」を追加（出典: pdca_summary_0824 §2）。

### 電話認証ステータス

| チャンネル | 電話認証 | カスタムサムネイル |
|---|---|---|
| daily-science | ✅ 済 | ✅ 有効 |
| その他全ch | ❌ 未完了 | ❌ 無効 |

認証手順: YouTube Studio → 設定 → チャンネル → 機能の利用資格 → 「電話番号を確認」（出典: HANDOFF.md §5）

---

## D. 競合分析サマリ

### 2chまとめ市場の概要

- **1,348チャンネル**がユーチュラに登録。超レッドオーシャン（出典: 競合分析レポート §1）
- 上位は登録者30〜74万人・再生数10〜40億回規模
- ショート特化上位: 「そんな夜には2ch」37万人、「涙の中心で愛を叫ぶ」36.2万人、「菊太郎」35.9万人

### 動画フォーマット3種

1. **ゆっくり解説型（長尺）** — 東方キャラ＋合成音声、10〜30分。登録者上位に多い
2. **ショート字幕スクロール型** — 2chスレの書き込みが字幕で縦スクロール。量産しやすい
3. **VOICEVOX/合成音声ナレーション型** — ゆっくり以外の音声で差別化。増加中

（出典: 競合分析レポート §1）

### 企業ファクト系の競合

| チャンネル名 | 登録者 | 特徴 |
|---|---|---|
| 俺たち天下のゆとりーマン | 84.6万人 | ブラック企業あるある。仮面4人組のアニメーション |
| カカチャンネル | 42.4万人 | 「しくじり企業」ゆっくり解説 |
| ゆっくり企業解説&決算 | 8.7万人 | 決算データから企業解説 |
| オワコン対策ゆっくり研究所 | 7.05万人 | 企業倒産・衰退をゆっくり解説 |

（出典: 競合分析レポート §2）

### サムネ・タイトルの勝ちパターン

- **強い煽り文句:** 「衝撃！」「悲惨な末路」等の太い白文字＋縁取り
- **色使い:** 赤・黄色の背景 or 暗い背景＋明るいテキスト
- **表情素材:** 驚き・怒り・泣きのイラスト or フリー素材人物写真
- **ショート向け:** 縦長9:16、大きな文字1〜2行

（出典: 競合分析レポート §1）

---

## G. 運用フロー

> **⚠️ 動画制作・投稿を行う際は、必ず以下のパイプラインに従うこと。手順を飛ばすな。**

### パイプライン（実行順序を厳守）

```
Step 1: テーマ選定
  └→ data/channels/<ch>.json の theme_queue からポップ
  └→ テーマ重複チェック（theme_dedup.py、閾値0.62）
  └→ ブラックリスト照合

Step 2: 台本生成
  └→ Claude系統: Claudeタスク内で自己生成（API不要）
  └→ GPT系統: Claude in ChromeでChatGPTスレッド経由（API直叩き禁止）
  └→ script_source メタデータ（"claude" | "gpt"）を記録
  └→ auto_scenario/generator.py → 8行構成ショート台本
  └→ 8行目CTA: 高評価を登録より先に置く（全ch共通）
  └→ チャンネル別 style_rules / extra_rules 適用

Step 3: 音声合成（VOICEVOX）
  └→ synthesize() → VOICEVOX localhost API
  └→ チャンネル別 speaker_id（キャラ設定）
  └→ speed パラメータはチャンネル設定から

Step 4: 映像合成（FFmpeg + Pillow）
  └→ generate_short_video() or generate_full_video()
  └→ キャラ立ち絵配置（char_config）
  └→ 背景: AI生成 or グラデーション
  └→ 字幕テロップ重畳
  └→ BGM合成（bgm_volume設定）

Step 5: サムネイル生成
  └→ generate_short_thumbnail()（9:16）
  └→ generate_thumbnail()（16:9）
  └→ チャンネル別配色・バッジ・キャラ反映（channel_dict必須）
  └→ 画像生成はgpt-image-1のみ使用可

Step 6: YouTube投稿
  └→ YouTube Data API v3（OAuth）
  └→ タイトル・説明文・タグ・サムネイル設定
  └→ post_upload.py: プレイリスト追加・コメント固定等

Step 7: PDCA分析
  └→ run_daily_pdca.py（毎日23:00）
  └→ analytics.db にスナップショット保存
  └→ 分析結果は YouTube_HANDOVER.md に追記（このファイル）
  └→ コンフィグ変更があれば data/channels/*.json を更新
```

**全ステップを `generate_all()` が統合実行する。** autopilot はこれをAPSchedulerで毎日固定時刻に自動発火する。

### 自動実行

- **autopilot:** APSchedulerが毎日チャンネルごとの固定時刻に自動発火
- **バックエンド:** launchd（`com.youtube-factory.backend`）で常駐、`localhost:8000`
- **ngrok:** 固定ドメイン（`agreeing-corrode-shabby.ngrok-free.dev`）で外部公開
- **PDCA:** `com.youtube-factory.pdca`（毎日23:00、現在未ロード）

（出典: HANDOFF.md §3, §8）

### 手動実行

```bash
cd /Users/ayukiyamazaki/Developer/youtube-factory
python3 backend/run_daily_science.py       # 日常科学
python3 backend/run_scp_short_upload.py    # SCP
python3 backend/run_daily_pdca.py          # PDCAレポート
```

（出典: HANDOFF.md §8）

### バックエンド再起動

```bash
launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend
```

または `restart_backend.command`（Finderからも実行可）（出典: HANDOFF.md §8）

### 動作確認

```bash
curl -s http://localhost:8000/health          # ローカル
curl -s https://agreeing-corrode-shabby.ngrok-free.dev/health   # 外部
```

（出典: HANDOFF.md §8）

### 技術スタック

- Python 3.9 + FastAPI（`backend/main.py`）
- Next.js 14.2（`frontend/`）
- VOICEVOX（ローカル or Docker）
- FFmpeg + Pillow
- YouTube Data API v3（OAuth）
- JSON/JSONL + SQLite（`data/`）
- Vercel（本番: `youtube-factory-eight.vercel.app`）

（出典: HANDOFF.md §2）

### 認証情報

- **APIキー全般:** `backend/.env`（gitignore済み）
- **YouTube OAuthトークン:** `data/youtube_tokens.db`
- **Google OAuthクライアント:** `backend/pipeline/credentials/oauth.db`（Fernet暗号化）
- **トークンDBはgitに入っていない**（このマシンが飛ぶと再認可が必要）

（出典: HANDOFF.md §4）

---

## E. 未解決課題

### 最優先

1. **impressions / CTR が全件0。** `video_metrics` 全4,850レコードで `impressions=0, ctr=0`。`thumbnail_ab_tests` 18件も `last_check_ctr=0`。サムネ改善が定量評価不能（出典: pdca_summary_0822 §5, pdca_summary_0710 §未解決1）
2. **company-facts の実績データ0件。** `autopilot.enabled=true`・テーマキュー11件だが `video_metrics` / `channel_metrics` ともに0行。投稿が到達しているか要確認（出典: pdca_summary_0822 §6）
3. **Git リモート未設定。** 214コミットがローカルのみ。バックアップ皆無（出典: HANDOFF.md §3, §6）

### インフラ

4. **全チャンネル電話認証未完了**（daily-scienceのみ済み）。カスタムサムネイルが使えない（出典: HANDOFF.md §5）
5. **未コミット114件の整理とコミット。** 新規62ファイルが無保護（出典: HANDOFF.md §5, §6）
6. **`com.youtube-factory.pdca` が未ロード。** 毎日のPDCAレポート生成が止まっている（出典: HANDOFF.md §3）
7. **OAuth / API関連:** daily-scienceの `redirect_uri_mismatch`、GCP consent screenのPublish、Anthropic APIキー無効（401）（出典: HANDOFF.md §6）

### コンテンツ

8. **再生0の動画の棚卸し:** daily-science 21本 + scp-lab 29本（出典: HANDOFF.md §6）
9. **OpenAI billing hard limit で `gpt-image-1` が使えない**（出典: HANDOFF.md §6）
10. **深田えいみchの無人autopilotリスク。** 婉曲表現による不適切動画の取りこぼしが実測で発生。公開前の目視ゲートを足すこと（出典: HANDOFF.md §1）

---

## F. 次回検証課題

| 期日 | 内容 | 出典 |
|---|---|---|
| **08-31** | 高評価CTA施策の効果測定。08-25以降公開分の高評価率中央値を比較し、0.30%→0.40%に届かなければCTA施策を撤回する（現状の全ch中央値は0.22〜0.47%） | pdca_summary_0824 §次回検証1 |
| 継続 | pokemon-labの高評価率と登録転換が逆方向（0.84倍）。n=20で確定できないので本数が増えたら再確認 | pdca_summary_0824 §次回検証3 |
| 継続 | scp-labの維持率と登録転換の関係（0.95倍で逆方向）。維持率は「否定された」のではなく「検出できていない」（p=0.23）。nが増えたら再検定 | pdca_summary_0824 §1, pdca_summary_0823_night §6 |
| 継続 | 08-23サムネ改修の効果。新規レンダリング実績がまだ出ていないため評価保留。高評価率と登録/1000再生で測る（CTRでは測れない） | pdca_summary_0824 §判定して変更しなかったもの |

---

## 付録: チャンネル一覧（2026-08-24時点）

| チャンネルID | 名前 | autopilot | 登録者 | 総再生 | 本数 |
|---|---|---|---|---|---|
| scp-lab | ゆっくり異常存在SCPラボ | ✅ | 135 | 136,011 | 154 |
| daily-science | リコとマコトのゆっくり日常科学 | ✅ | 55 | 173,839 | 183 |
| pokemon-lab | ゆっくりポケラボ | ✅ | 13 | 40,775 | 28 |
| yokai-watch | ゆっくり妖怪ラボ | ✅ | 10 | 36,117 | 28 |
| 2ch-matome | ゆっくり2chスレまとめ劇場 | ✅ | 5 | 23,644 | 24 |
| company-facts | 企業のホンネ | ✅ | — | — | — |
| clip-lab | ゆっくり解説 切り抜きラボ | ✅ | — | — | — |
| clip-fukada | 深田えいみ 切り抜きチャンネル | ✅ | — | — | 1 |
| clip-kaneko | 金子みゆ 切り抜きチャンネル | ✅ | — | — | 0 |
| akashic-librarian | ラグナロクの司書 | ❌ 停止中 | — | — | — |

数値出典: pdca_summary_0823_night チャンネル数値サマリ / HANDOFF.md §1
