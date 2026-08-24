# YouTube Factory 引き継ぎ書

最終更新: 2026-08-20 / 対象コミット: `b680410`（`main`）/ 作業ツリー: **未コミット 114 件あり**

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
| `clip-lab` | ゆっくり解説 切り抜きラボ | ✅ | 17:45 | — | — | — |
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

### インフラ・運用

1. **未コミット 114 件の整理とコミット**（新規 62 ファイルが無保護。最優先）
2. **Git リモートを用意して push**（214 コミットがローカルのみ。バックアップ皆無）
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
