# YouTube Factory 引き継ぎ書

最終更新: 2026-09-01 / 作業ツリー: **未コミット多数あり（`data/` 配下の実行結果が中心）**

> **2026-09-01 の変更まとめ**
>
> | 内容 | 状態 |
> |---|---|
> | `video_status` が 06-07 で止まっていた問題 | ✅ 修正（`pipeline/publish_log.py` 新設 → §5「公開実績DB」） |
> | `data/channels_orchestrator/` との設定乖離 | ✅ 解消（symlink 化。master は `data/channels/`。→ `docs/CHANNEL_CONFIG_SOURCE_OF_TRUTH.md`） |
> | company-facts / akashic / 切り抜き4ch が analytics 未同期 | ✅ 解消（`video_format.analytics.enabled` を追加。clip-fukada / clip-kaneko だけ **OAuth失効で未解決**） |
> | ショート投稿タイトルが `〜【ショート】` になり `#shorts` すら付いていなかった | ✅ 修正（`generate_descriptions` にタイトル行を追加） |
> | fake-paper 登録0 / yokai 登録効率最下位 | ✅ コンフィグ反映（→ §5「2026-09-01 のマーケ改善」） |

> `docs/HANDOFF.md` は 2026-07-02 時点の古い Dispatch 引き継ぎメモ。**このファイルが最新**。
> 仕様の全文は `youtube_factory_full_spec.md`（約 433KB）にある。

---

## 1. プロジェクト概要

「ゆっくり解説」系ショート動画を **台本生成 → 音声合成 → 映像合成 → サムネ生成 → YouTube 投稿 → 分析（PDCA）** まで
全自動で回す動画ファクトリー。1本のパイプラインを設定ファイルで多チャンネルに展開する構成。

現在 **8 チャンネル**を運用（うち 7 チャンネルが autopilot 有効）。

| チャンネル ID | 名前 | autopilot | 投稿時刻 | 登録者 | 総再生 | 本数 |
|---|---|---|---|---:|---:|---:|
| `scp-lab` | ゆっくり異常存在SCPラボ | ✅ | 19:00 | 133 | 133,388 | 146 |
| `daily-science` | リコとマコトのゆっくり日常科学 | ✅ | 18:00 | 52 | 168,282 | 177 |
| `pokemon-lab` | ゆっくりポケラボ | ✅ | 17:30 | 11 | 33,937 | 23 |
| `yokai-watch` | ゆっくり妖怪ラボ | ✅ | 18:30 | 10 | 31,792 | 22 |
| `2ch-matome` | ゆっくり2chスレまとめ劇場 | ✅ | 17:15 | 4 | 14,349 | 15 |
| `company-facts` | 企業のホンネ | ✅ | 17:00 | — | — | — |
| `clip-lab` | ゆっくり解説 切り抜きラボ | ✅ | 17:45（国内）＋ 20:45（海外バイラル） | — | — | — |
| `akashic-librarian` | ラグナロクの司書 | ❌ 停止中 | 18:45 | — | — | — |
| `clip-fukada` | 深田えいみ 切り抜きチャンネル | ✅ 2026-08-24 稼働 | 20:00 | — | — | 1 |
| `clip-kaneko` | 金子みゆ 切り抜きチャンネル | ✅ 2026-08-24 稼働 | 20:30 | — | — | 0 |

数値は `data/reports/latest.md`（2026-08-18 生成）より。`company-facts` / `clip-lab` は当該レポートに集計行なし（投稿実績がまだ薄い）。

`clip-fukada` / `clip-kaneko` は**タレント単独の切り抜きチャンネル**。2026-08-24 に稼働開始。
許諾は**ガジェット通信クリエイターネットワーク（MCN / getnews.jp/mcn/kirinuki）経由**で、両名とも
切り抜き公認リストに掲載されている。ガジェ通方式は「申請 → 承認メール」なので元動画の説明欄に
許諾文言が無く、`require_permission_phrase: false` ＋ `permission_note` に根拠を書く運用。
初投稿: https://youtube.com/watch?v=TJacs9E879U （clip-fukada / 2026-08-24）。

> ⚠️ **深田えいみ側はタイトルのブロックリストだけでは性的な回・共演回を防ぎきれない。**
> 婉曲表現が多く、「急にどうした？」＝媚薬PR回、「よろしくお願いします」＝ぷろたん共演回、
> といった取りこぼしが実測で出ている。区間単位のゲート
> （`segment_selection.exclude_text_patterns`。今回追加）で最終防御しているが、
> **無人 autopilot で回すなら公開前の目視ゲートを足すこと。** 詳細は
> `docs/CLIP_TALENT_CHANNELS_SETUP.md` の「2026-08-24 稼働開始」節。

**海外バイラル翻訳切り抜き**は `clip-lab` の **20:45 スロット**として同居する
（2026-08-30 のユーザー決定。当初案の専用チャンネル `clip-viral` は作らず、
`data/channels/clip-viral.json` は削除して設定を `clip-lab.json` の
`clip.viral_sources` に統合した）。Reddit で今日バズった短尺動画を Whisper で
書き起こし → Claude で日本語化 → **専用レンダラ**で縦型ショートに焼く。

| 項目 | 決定（2026-08-30） |
|---|---|
| チャンネル | 既存 `clip-lab` に同居（17:45 = 国内切り抜き / 20:45 = 海外バイラル） |
| レンダラ | 国内と共有せず `renderer_overseas.py` に分離 |
| 翻訳失敗時 | スキップせず3回まで指数バックオフで再試行 |
| 公開設定 | 目視レビューなし。private を経ず直接 public |
| 投稿枠 | 毎日 20:45 に1枠 |

> ⚠️ 同居しているので **`autopilot.schedule.times` の 20:45 スロットにある
> `"engine": "viral"` を消してはいけない。** これが素材の探索先（Reddit か
> 許諾済み YouTube か）も決めている。消すと海外枠が国内素材で回る。

稼働に残っている条件は **`ANTHROPIC_API_KEY`（必須・現在空）** だけ。
YouTube チャンネルと OAuth は clip-lab の既存のものをそのまま使う。
`REDDIT_CLIENT_ID`/`SECRET` は無くても RSS 経路で動く（スコア・NSFW フラグが
取れないので強く推奨）。詳細は `docs/CLIP_VIRAL_CHANNEL.md`。

### 運用ルール（過去の指示・厳守）

- ショートのみ・1日1本・チャンネルごとの固定スロット
- 投稿設定の変更は必ず実データ分析に基づく（PDCA 厳守）
- 動画の大きな見た目変更・画像配置変更は、サンプルを出して承認を得てから反映
- 1リポジトリに複数タスクを並行させない（必ずマージしてから終了）
- ai-orchestrator は**明示的な指示があったときだけ**使う

---

## 2. 技術スタック

| 層 | 使っているもの |
|---|---|
| バックエンド | Python 3.9 + FastAPI（`backend/main.py`、uvicorn `0.0.0.0:8000`） |
| フロントエンド | Next.js 14.2 (App Router) + React 18 + Tailwind（`frontend/`） |
| 音声合成 | VOICEVOX（`VOICEVOX_URL`。ローカル or Docker） |
| 映像合成 | FFmpeg + Pillow（`backend/pipeline/` 配下） |
| 台本・分析 | OpenAI API / Anthropic Claude API |
| 素材収集 | Pexels / Pixabay / Unsplash / Google CSE |
| 投稿 | YouTube Data API v3（OAuth）、TikTok Content Posting API |
| 永続化 | JSON / JSONL + SQLite（`data/` 配下） |
| 外部公開 | ngrok 固定ドメイン（OAuth コールバック・Webhook 受け口） |
| 常駐 | launchd（`~/Library/LaunchAgents/com.youtube-factory.*.plist`） |
| ホスティング | Vercel（フロント + バックエンドを `experimentalServices` で同居） |

`data/` は**設定でもあり実行結果でもある**。`data/channels/<id>.json` がチャンネルの単一の真実（テーマキュー・
競合・サムネ設定・autopilot スケジュール・video_format まで全部ここ）。

---

## 3. デプロイ先・稼働環境

| 項目 | 値 |
|---|---|
| 本番 URL | https://youtube-factory-eight.vercel.app （HTTP 307 → `/login`。**認証ゲート付きで稼働中**） |
| Vercel プロジェクト名 | `youtube-factory` |
| Vercel projectId | `prj_LTRLM22VNZ9Qnp5MTZa6FjOI9BS5` |
| Vercel orgId | `team_r5d4Rpbmwu5q0EryE985968c` |
| ローカル API | `http://localhost:8000`（`/health` は 200 を返す＝稼働中） |
| 外部公開 URL | `https://agreeing-corrode-shabby.ngrok-free.dev` → localhost:8000（ngrok 固定ドメイン） |
| Git リモート | **未設定**。GitHub 等へのバックアップが無い（214 コミットがこのマシンにしか無い） |

### 常駐プロセス（launchd）の現況

| Label | 内容 | 状態（2026-08-20 時点） |
|---|---|---|
| `com.youtube-factory.backend` | uvicorn `main:app` を KeepAlive | ✅ **稼働中**（pid 20984） |
| `com.youtube-factory.ngrok` | ngrok http 8000（固定ドメイン） | ✅ **稼働中**（pid 37949） |
| `com.youtube-factory.pdca` | 毎日 23:00 に `backend/run_daily_pdca.py` | ⚠️ **ロードされていない**（`launchctl list` に無い） |
| `com.youtube-factory.agent` | `python -m agent run youtube-growth` を KeepAlive | ⚠️ **ロードされていない**（かつ `agent/` は `agent_deprecated/` にリネーム済み。このまま load すると起動失敗する） |

> plist は `~/Library/LaunchAgents/` にある。ロードは `launchctl load -w <plist>`、確認は `launchctl list | grep youtube`。

---

## 4. 認証情報の場所（値は書かない）

| 種別 | 場所 |
|---|---|
| API キー全般 | `backend/.env`（**gitignore 済み**。ひな型は `backend/.env.example`） |
| 必要なキー一覧 | `API_KEY` / `APP_PASSWORD_HASH` / `JWT_SECRET` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `YOUTUBE_API_KEY` / `PIXABAY_API_KEY` / `PEXELS_API_KEY` / `UNSPLASH_ACCESS_KEY` / `GOOGLE_CSE_API_KEY` / `GOOGLE_CSE_ID` / `CORS_ORIGINS` / `PORT` / `HOST` / `VOICEVOX_URL` / `NGROK_AUTHTOKEN` / `NGROK_DOMAIN` |
| YouTube OAuth トークン | `data/youtube_tokens.db`（SQLite。バックアップ `data/youtube_tokens.db.bak_20260520_223338` あり） |
| TikTok トークン | `data/tiktok_tokens.db` |
| Google OAuth クライアント | `backend/pipeline/credentials/oauth.db`（Fernet 暗号化済み。`.gitignore` で明示除外） |
| 管理画面ログイン | `APP_PASSWORD_HASH` + `JWT_SECRET` によるパスワード認証（本番 URL の `/login`） |

`.gitignore` で `.env` / `backend/.env` / `*.db` / `backend/pipeline/credentials/oauth.db` を除外済み。
**トークン DB は git に入っていない＝このマシンが飛ぶと再認可が必要**。

---

## 5. 現在の状態

**本番稼働中。** 毎日 autopilot でショートが自動投稿されている（バックエンドと ngrok は launchd で常駐）。

### 公開実績DB（`data/video_publish.db` の `video_status`）— 2026-09-01 修正

`video_status` は **2026-06-07 を最後に更新が止まっていた**。運用が
`gen_type="short"` の単体公開に移ったのに、その経路
（`api_phase4._start_single_short_publish`）と手動スクリプト経路
（`youtube_uploader.upload_video`）がどちらもこのテーブルに書いていなかったため。
`api_phase3` のペア公開と PublishDialog だけが書き手だった。

これを起点にしていた次の2つが静かに死んでいた:

- `pipeline/analytics/pdca_report.build_report()` — 期間内の動画が0件になり、
  ショート/メインの振り分けも登録者ソース分析も全部 `unknown` に落ちる
- `api_improvement._published_videos_for_channel()` — いいね率改善ループが
  毎回「公開済みの動画がまだありません」で空振り

対応:

| やったこと | ファイル |
|---|---|
| 記録を1箇所に集約（`is_short` / `title` カラムも冪等 ALTER で追加） | `backend/pipeline/publish_log.py`（新規） |
| `upload_video` 成功後に記録（手動スクリプト・clip_factory を含む全経路） | `backend/pipeline/youtube_uploader.py` |
| autopilot の単体ショート/メイン公開から記録 | `backend/api_phase4._record_publish_status` |
| 6〜8月の欠損 496 本を `analytics.db` から埋め戻し（API不使用・冪等） | `backend/backfill_video_status.py` |
| 同じ `video_id` の重複集計を防止 / 記録済み `is_short` を優先 | `pipeline/analytics/pdca_report.py` |

検証: scp-lab の `subscriber_sources` が「全部 unknown」から
`shorts 100% / 0.626 登録per1000再生` に復旧。

```bash
python3 backend/backfill_video_status.py --dry-run   # 欠損の件数だけ見る
python3 -m unittest tests.test_publish_log           # backend/ で実行
```

### ショート投稿タイトルの取りこぼし — 2026-09-01 修正

`generate_descriptions()` はメイン説明文の先頭にだけ `タイトル: ...` 行を書いており、
ショート説明文には書いていなかった。そのため `_read_desc()` が `title=""` を返し、
autopilot が `job.title + "【ショート】"` のフォールバックに落ちて、
`short_series_name` / `defaults.short_title_hashtags` / `short_title_core_max` で
組んだタイトルが **一度も YouTube に届いていなかった**（`#shorts` すら付いていない）。
実測: yokai-watch の8月投稿 39 本中 37 本がこの経路。

### 2026-09-01 のマーケ改善

**fake-paper（再生4,189・登録0）** — 他chとの比較で分かったこと:

| 指標 | fake-paper | scp-lab | daily-science |
|---|---:|---:|---:|
| 高評価率 | 0.43% | 0.46% | 0.46% |
| 平均視聴維持率 | **27.6%** | 38.3% | 57.2% |
| 登録/1000再生 | **0.00** | 0.79 | 0.37 |

高評価率は他chと同水準なので「刺さっていない」のではない。差は
**(a) 最終行に『高評価』の語が無い唯一のチャンネルだったこと**（`cta_fallback` も未設定で
`cta_enforcer` の文言をチャンネル側から制御できなかった）と、
**(b) 維持率27.6%＝全ch最下位**（実台本 228〜302字で設定帯 190〜235 を常に超過）。
→ 7行目を高評価→登録の順に、尺を 170〜210字に、2行目の「架空の掲載誌名＋研究機関名」を
リスナーの食いつきに差し替え（全ch共通の離脱地点である再生位置20%に報酬が無かった）、
タイトルの `#フィクション` を除去（オチの先出し）。

> ⚠️ fake-paper は電話認証未完了＝**カスタムサムネイルが無効**。`thumbnail_template` を
> いじっても YouTube 側には反映されない。サムネで手を打つには先に電話認証が要る。

**yokai-watch（登録0.28/1000再生）** — 高評価率 0.365% は6ch中5位。
実測四分位（n=322）で 0.2-0.4% 帯の登録転換は 0.32 なので、観測どおり。
`cta_fallback.like` の「ゾッとしたら高評価を押してね」は怖がらなかった視聴者を全部こぼすので
条件を外した。あわせて 30日以内に再投稿して公開3日目の再生が 1/8〜1/10 に沈んだ
「コマさん」「エンマ大王」を `theme_blacklist` に追加。

> 注: 08-20〜08-29 の再生崩壊（年齢を揃えた公開3日目の中央値 1,685 → 416）は
> テンプレ型タイトル（`1分妖怪ファイル #N：👁️〇〇に隠された3つの秘密…`）が原因で、
> 08-31 の PDCA が `title_style` と `short_series_name` を直して対処済み。
> 絵文字を足していた `title_emoji_injector` も 2ch-matome 以外では無効化済み。

### カスタムサムネイル（電話認証）

カスタムサムネイルの利用には YouTube の電話番号認証が必要。API からは認証できないため、チャンネルごとに手動で実施する。

| チャンネル ID | 電話認証 | カスタムサムネイル |
|---|---|---|
| `daily-science` | ✅ 済 | ✅ 有効 |
| `scp-lab` | ❌ 未完了 | ❌ 無効 |
| `pokemon-lab` | ❌ 未完了 | ❌ 無効 |
| `yokai-watch` | ❌ 未完了 | ❌ 無効 |
| `2ch-matome` | ❌ 未完了 | ❌ 無効 |
| `fake-paper` | ❌ 未完了 | ❌ 無効 |
| `company-facts` | ❌ 未完了 | ❌ 無効 |
| `akashic-librarian` | ❌ 未完了 | ❌ 無効 |
| `clip-lab` | ❌ 未完了 | ❌ 無効 |
| `clip-fukada` | ❌ 未完了 | ❌ 無効 |
| `clip-kaneko` | ❌ 未完了 | ❌ 無効 |

**認証手順:** YouTube Studio → 設定 → チャンネル → 機能の利用資格 → 「電話番号を確認」

### 台本 A/B テスト（Claude vs GPT）

台本生成を **Claude（自己生成）** と **GPT（Claude in Chrome 経由）** の 2 系統で並行運用し、データドリブンで勝者を決める。

| 項目 | Claude 系統 | GPT 系統 |
|---|---|---|
| 生成方法 | Claude タスク内で自己生成（API 不要） | Claude in Chrome で ChatGPT スレッド上に会話して生成 |
| API 依存 | なし（Claude 自身が書く） | **API 直叩き禁止。** 必ず ChatGPT の Web UI スレッド経由 |
| スレッド管理 | — | チャンネルごとに ChatGPT スレッドを 1 つ維持 |

> ⚠️ **GPT 側を ChatGPT スレッド経由にしている理由:** ユーザー（ザキ）が同じスレッドから横で介入・修正できるようにするため。API で叩くとその会話コンテキストが失われる。

**運用フロー:**

1. 投稿時に `script_source` メタデータ（`"claude"` | `"gpt"`）を記録
2. 一定本数が溜まったら YouTube Analytics で **再生数・維持率・エンゲージメント** を比較分析
3. 勝者を標準採用

**OpenAI API の用途:** 画像生成（`gpt-image-1`）**のみ**。台本生成には使わない。

### 未コミット変更: **あり（114 件）**

| 種別 | 件数 | 中身 |
|---|---:|---|
| リネーム（`R`） | 17 | `agent/` → `agent_deprecated/` 一式（旧・内蔵エージェントの退役） |
| 変更（`M`） | 35 | `backend/main.py` / `auto_comment.py` / `auto_scenario/generator.py` / `theme_queue.py` / `post_upload.py` / `video_generator.py`、および `data/` 配下の実行結果（channels 8件・pdca-memory・analytics・reports・series_links・scenarios の index） |
| 未追跡（`??`） | 62 | `backend/pipeline/` に新規追加された演出・最適化モジュール群（`comment_bait_injector.py` `completion_rate_optimizer.py` `contrast_amplifier.py` `cross_channel_bridge.py` `cta_rotator.py` `curiosity_gap_enforcer.py` `hook_ab_selector.py` `originality_guard.py` `retention_feedback_loop.py` `round6〜8_enhancer.py` `swipe_stop_injector.py` ほか多数） |

> ⚠️ **未追跡 62 ファイルは一度もコミットされていない実装。** `data/` 配下の差分は日々の実行で常に動くので、
> コミットするならコード（`backend/`）と実行結果（`data/`）を分けて積むこと。

---

## 6. 残タスク

### 2026-09-01 に判明して未解決のもの（最優先）

0-a. **`clip-fukada` / `clip-kaneko` の OAuth トークンが失効している。**
   `invalid_grant: Token has been expired or revoked.`。analytics 同期も自動投稿も
   通らない（＝この2chは 08-24 の稼働開始以降ずっと止まっている可能性が高い）。
   コードでは直せない。管理画面から再認可すること。
   確認: `python3 -c "import sys;sys.path.insert(0,'backend');from pipeline import youtube_oauth as yo;print(yo.get_credentials_for('clip-fukada'))"`

0-b. **CTA 遵守率の実測は 2026-09-02 以降に取り直すこと。**
   `pipeline/cta_enforcer.py` は 09-01 10:30 に入ったが、稼働中バックエンドは
   08-31 起動でこのコードを持っていなかった（09-01 11:40 に再起動して反映済み）。
   `scripts/verify_cta_20260901.py` が見ている 08-25〜31 のアーカイブは全て補正前なので、
   高評価37% / 登録36% / 両方19% という数字は**修正の効果を測っていない**。

0-c. **`data/channels/` 以外に設定を書かないこと。** `data/channels_orchestrator/` は
   symlink になった。詳細は `docs/CHANNEL_CONFIG_SOURCE_OF_TRUTH.md`。
   確認: `python3 scripts/unify_channel_configs.py --check`

0-d. **既存の赤いテスト2件**（今回の変更とは無関係）:
   `tests.test_description_blocks.TestRealChannelHashtags` が `clip-animal` /
   `clip-kaneko` の `short_hashtags` 本数で落ちる。
   `tests.test_cta_enforcer` は `pytest` 未導入で import エラー。

### インフラ・運用

1. ~~未コミット 114 件の整理とコミット~~（2026-09-01 にコード分をコミット済み）
2. **Git リモートを用意して push**（コミットがローカルのみ。バックアップ皆無）
3. **`com.youtube-factory.pdca` を load**（毎日の PDCA レポート生成が止まっている）
4. **`com.youtube-factory.agent` の扱いを決める**（`agent/` は退役済み＝この plist は今 load すると失敗する。削除するか ai-orchestrator に寄せる）

### 機能・コンテンツ

5. Anthropic API キー無効（401）問題 — 分析を Claude タスク方式に移行してキー依存を廃止する方針だった
6. Analytics API の views 取得が壊れている（時間帯分析が全部 0 を返す）
7. `daily-science` の OAuth `redirect_uri_mismatch` — UI からの再認可がブロックされている
8. GCP consent screen を Published にする（永続 OAuth 用。ユーザー操作が必要）
9. 再生 0 の動画を非公開にする（daily-science 21本 + scp-lab 29本の棚卸し）
10. OpenAI billing hard limit で `gpt-image-1` が使えない → 復旧後に `gen_images.py` を実行すれば完了
11. TikTok セットアップ（アカウント作成 → 開発者登録 → 審査申請）。手順は `docs/TIKTOK_SETUP.md`
12. 過去の SCP 非公開動画 5本（`dItYJed2Qog` 等）の手動公開 or スコープ拡張
13. `akashic-librarian` の autopilot 有効化判断（現在 `enabled: false`）
14. テーマ重複が多い（`2ch-matome` で類似ペア 15 件・閾値 0.62）→ 重複閾値の厳格化

---

## 7. 既知の制約・注意点

- **`data/` を消すな。** チャンネル設定・テーマキュー・PDCA メモリ・OAuth トークンが全部ここ。設定と実行結果が同居している。
- **`youtube_factory_full_spec.md` は約 433KB。** 丸ごと読むとコンテキストが飛ぶ。必要な節だけ grep すること。
- **Python は 3.9（システム標準）。** launchd も `/usr/bin/python3` を直指定。venv を使っていないので、`pip install` はシステムに入る。
- **`agent/` は退役済み**（`agent_deprecated/`）。自律運用は独立リポジトリの `ai-orchestrator` 側に移っている。
- YouTube Data API のクォータ上限に注意（分析ジョブを連打すると投稿ができなくなる）。
- ngrok は固定ドメイン契約。ドメインが変わると OAuth の redirect_uri が全部ズレる。
- バックエンドを `--reload` で起動すると、外部から叩いている処理が途中で死ぬ。`.command` スクリプト経由の再起動を使う。

---

## 8. 前回成功した方法

### バックエンドの起動・再起動

```bash
# launchd 経由（推奨。KeepAlive で落ちても復活する）
launchctl kickstart -k gui/$(id -u)/com.youtube-factory.backend

# 手動起動する場合（backend/ で実行すること。main:app のパス解決がカレント依存）
cd /Users/ayukiyamazaki/Developer/youtube-factory/backend
python3 -u -m uvicorn main:app --host 0.0.0.0 --port 8000
```

ルートに `restart_backend.sh` / `restart_backend.command` / `RestartBackend.app` があり、Finder からも再起動できる。

### 動作確認

```bash
curl -s http://localhost:8000/health          # → 200
curl -s https://agreeing-corrode-shabby.ngrok-free.dev/health   # 外部からの疎通
```

### 単発の動画生成・投稿

ルートの `.command` / `backend/run_*.py` がチャンネルごとの実行入口になっている。

```bash
cd /Users/ayukiyamazaki/Developer/youtube-factory
python3 backend/run_daily_science.py       # 日常科学
python3 backend/run_scp_short_upload.py    # SCP ショート投稿
python3 backend/run_daily_pdca.py          # PDCA レポート生成 → data/reports/latest.md
```

### フロントエンド

```bash
cd frontend && npm run dev     # http://localhost:3000
npm run typecheck              # tsc --noEmit
```

### 本番 API の叩き方

`/api/*` は JWT 認証。`APP_PASSWORD` でログインしてトークンを取り、`Authorization: Bearer` を付ける
（ai-orchestrator も同じ手順で叩いている。実装は `ai-orchestrator/src/tools/youtube_factory.py` が参考になる）。
