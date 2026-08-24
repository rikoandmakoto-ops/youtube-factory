# 自律 AI オーケストレーター (`agent/`)

人間の代わりに **observe → think → act → check** を Claude で回し続けるエージェント。
まずは YouTube 運用（scp-lab / daily-science）に特化。コアは汎用なので、目的とツールを
差し替えれば他プロジェクトにも転用できる。

## 使い方

```bash
# 1サイクルだけ・実際には生成/投稿しない（最初の動作確認はこれ）
python -m agent run youtube-growth --once --dry-run

# 1サイクルだけ実際に動かす（今日未投稿なら生成→public投稿まで）
python -m agent run youtube-growth --once

# 常駐ループ（既定30分間隔）
python -m agent run youtube-growth

# サイクル数/間隔/モデルを指定
python -m agent run youtube-growth --max-cycles 3 --interval 600 --model claude-sonnet-4-20250514

# エージェントの記憶（学習・タスク・直近ログ）を見る
python -m agent status
```

環境変数 `AGENT_MODEL` / `AGENT_INTERVAL_SECONDS` でも既定値を変えられる。
通知は `SLACK_WEBHOOK_URL` / `LINE_NOTIFY_TOKEN` があればそこへ、無ければ
`agent/state/notifications.log` と標準出力へ。

## しくみ

- `core.py` — 汎用ループ本体。Claude の tool-use を「思考↔行動」の往復として回す。
- `tools/` — エージェントの手:
  - `youtube.py` 投稿状況の観測 / アップロード / トークン更新
  - `video_gen.py` ショート動画生成（既存 `run_short_only`）/ VOICEVOX 死活・再起動
  - `browser.py` フロント(Next.js)のブラウザ操作（Playwright）。ページ遷移/クリック/入力/
    スクショ、`app_login`（アプリへログイン）、`youtube_reauth`（OAuth 再認証の自動化）
  - `shell.py` 任意コマンド, `notify.py` ユーザー通知, `memory_tools.py` 記憶操作
- `memory.py` — `state/` に actions(ログ)/learnings(知見)/tasks(進行中) を永続化。
  毎サイクル冒頭で要約して Claude に渡す＝記憶を踏まえて考える。
- `objectives/youtube_growth.py` — 目的(mission)・運用ルール(guidance)・ツール一式。
  他プロジェクトはこのファイルを雛形に objective を足す。

## 既知の前提

- `backend/.env` の `ANTHROPIC_API_KEY` で「考える」、`OPENAI_API_KEY` は台本生成
  （内部で OpenAI→Claude フォールバック）。
- 動画生成には VOICEVOX(localhost:50021) が必要。落ちていれば `restart_voicevox` で復旧を試みる。
- アップロードには各チャンネルの YouTube OAuth トークンが必要。失効時は `refresh_youtube_token`
  → 駄目（refresh_token 失効）なら `youtube_reauth` でブラウザから OAuth をやり直す
  → それも自動完了できなければ `notify_user` でUI再認証を要求する。

## ブラウザツール（Playwright）

フロント操作・OAuth 再認証の自動化に Playwright を使う。初回だけ導入が必要:

```bash
pip install playwright && playwright install chromium
```

- 既定でフロントは `http://localhost:3000`。別ポートなら `AGENT_APP_BASE_URL` で指定。
- アプリへのログインは `APP_PASSWORD`（`backend/.env`）を使う。永続プロファイル
  (`agent/state/browser_profile/`) に Cookie が残るので 2 回目以降は省略される。
- `youtube_reauth` は **Google のセッションが永続プロファイルに残っていれば headless で
  自動完了**する。初回は `AGENT_BROWSER_HEADLESS=0`（画面ありモード）で一度手動ログイン
  を通しておくと、以後は無人でも再認証できる。OAuth 同意で特定アカウントを優先選択させたい
  場合は `GOOGLE_ACCOUNT_EMAIL` を設定する。
- ログイン/2FA が必要で自動完了できないときは `needs_human=True` とスクリーンショット
  (`agent/state/screenshots/`) を返すので、エージェントは `notify_user` で人に上げる。

## 定期実行（launchd 例）

`--once` を cron / launchd から定期実行するのが安全（常駐より状態がクリーン）。
30分ごとに1サイクル走らせる launchd plist を組むなら `python -m agent run youtube-growth --once`
を `StartInterval 1800` で叩く。
