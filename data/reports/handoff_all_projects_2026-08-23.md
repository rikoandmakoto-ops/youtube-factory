# 全プロジェクト 引き継ぎレポート — 2026-08-23

生成: 2026-08-23（自動タスク `daily-project-handoff`）
調査方式: **全プロジェクト読み取りのみ**。youtube-factory 以外への書き込み・変更は一切なし。

---

## 0. エグゼクティブサマリ

| プロジェクト | URL | ステータス | 一言 |
|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 要対応 | 6ch autopilot 稼働中。未コミット274件が最大リスク |
| aiseki | https://aisekimatch.com（旧 https://aiseki-xi.vercel.app） | 🟢 正常（公開可） | P0 全完了。残りは人手（実機確認・運営体制・CAPTCHA） |
| fanup | https://fanup-rouge.vercel.app | 🟡 要対応 | MVP完了・決済env待ち・集客未着手 |
| oripa | https://oripa-omega.vercel.app | 🟡 要対応 | Phase1 MVP。古物商許可待ち・ブランチ分岐 |
| ai-english-coach | 未発行（未デプロイ） | 🟡 要対応 | Phase1+1.5 実装済／実機・音声課金未着手 |
| 切り抜きラボ（clip-lab） | — | 🔵 凍結 | youtube-factory 内チャンネル。autopilot=false |
| rhythm-pop | — | 🟡 要対応 | 完成済みだが未コミット17件が未保存 |
| claude-codex-bridge | — | 🟢 完成 | 作業ツリークリーン。追加作業なし |

---

## 1. youtube-factory

**パス**: `/Users/ayukiyamazaki/Developer/youtube-factory`
**ステータス**: 🟡 **要対応**（稼働自体は正常。リポジトリ衛生とAPIキーが課題）

### 1-1. チャンネル別 autopilot 状態（全9ch）

| チャンネル | autopilot | 登録者 | 総再生 | 本数 | 投稿スロット |
|---|:--:|---:|---:|---:|---|
| ゆっくり異常存在SCPラボ (`scp-lab`) | ✅ ON | **135** | 136,011 | 154 | 平日 9:00 / 19:00・土日 13:00 / 19:00 |
| リコとマコトのゆっくり日常科学 (`daily-science`) | ✅ ON | **55** | 173,839 | 183 | 平日 17:00・土日 13:00 |
| ゆっくりポケラボ (`pokemon-lab`) | ✅ ON | **13** | 40,775 | 28 | 平日 17:30・土日 12:00 |
| ゆっくり妖怪ラボ (`yokai-watch`) | ✅ ON | **10** | 36,117 | 28 | 平日 19:00・土日 12:00 |
| ゆっくり2chスレまとめ劇場 (`2ch-matome`) | ✅ ON | **5** | 23,644 | 24 | 平日 18:00・土日 12:00 |
| company-facts | ✅ ON | 未計測 | — | — | 平日 17:00・土日 14:00 |
| 虚構論文チャンネル (`fake-paper`) | ⛔ OFF | 0 | 1,101 | 1 | （19:30 設定あり・停止中） |
| akashic-librarian | ⛔ OFF | — | — | — | （18:45 設定あり・停止中） |
| **切り抜きラボ (`clip-lab`)** | ⛔ OFF | — | — | — | **凍結中** |

合計登録者（計測できた5ch）: **218人** / 総再生 約41万回。

### 1-2. 直近の投稿状況・PDCA

- PDCA 日次レポートは **2026-08-23 23:00 に正常生成**（`data/reports/latest.md` / `2026-08-23/`）。8/12〜8/23 まで欠落なく毎日出力（8/19-20 のディレクトリのみ無いが handoff は生成済み）。
- Act フェーズで続編キュー投入: `2ch-matome` 2本（PCパーツ到着 deep_dive / contrast）、`yokai-watch` 2本（のっぺらぼう deep_dive / contrast）。他4chは「絶対再生30以上のバズ続編が未検出」で投入なし。
- 全チャンネルで判定が **「サンプル不足 — もう少し様子見」**。直近30日のショート実績が 0本 として集計されており、**30日窓の集計ロジックが実データを拾えていない疑いがある**（動画自体は5〜24日前に投稿されているため矛盾）。

### 1-3. エラー・警告（本日分 backend.log）

| 件数 | 内容 | 深刻度 |
|---:|---|---|
| 32 | `rss fetch UCjs5hqhQ_fBMjxXvJC5TGig` 失敗（他8チャンネルIDも各5件） | 中 — 競合RSS監視が実質機能していない |
| 12 | `short_scenario` 警告 | 中 |
| 7×3 | `ScenarioValidator` / `ViralScore` の検証スコア低下（scp-lab, daily-science, 2ch-matome, company-facts）<br>例: score=5「冒頭フックが該当しない／転換ワード無し／CTA無し」 | 中 — 品質ゲートを通っていない台本が生成されている |
| 6 | **サムネイル設定失敗 HTTP 403** `The authenticated user doesn't have permissions to upload and set custom video thumbnails` | 高 — **YouTube アカウントの電話番号確認が未完了**。カスタムサムネが一切設定できない |
| 6 | `JobQueue persist failed: No such file or directory data/job_queue.json.tmp` | 高 — ジョブキューが永続化に失敗している |
| 全ch | `Claude分析: スキップ（ANTHROPIC_API_KEY 未設定）` | 高 — 成功パターン分析・視聴維持率分析が**全チャンネルで動いていない** |

その他: テーマ重複チェックで類似度 **1.0（完全重複）** のペアが daily-science に複数（しゃっくり／録音の声／酸素消失）、yokai-watch にも 1.0 が1件。重複台本が実際に投稿されている。

### 1-4. Git

- ブランチ: `main` のみ。**未マージブランチなし**。
- 最新5コミット:
  ```
  d5a39d9 fix(oauth): 新規チャンネルで連携ボタンが押せない問題を修正（クライアント流用）
  cb433e2 feat(auth): 管理画面セッションを7日→90日に延長し、環境変数で調整可能にする
  b680410 feat(rss): 競合未登録だった5chに監視対象を登録し、RSS監視の穴を塞ぐ
  beaa65a chore(channels): 全8chに新機能の設定と初期状態を投入
  ddff8f8 feat(growth): 再生リスト自動管理・シリーズ相互リンク・リクエスト募集・競合RSS監視・ショートエンドカード
  ```
- **未コミット変更: 274件**（変更47 / リネーム17 / 未追跡210）
  - `agent/` → `agent_deprecated/` へのリネーム17件が **staged のまま未コミット**
  - backend 側の実コード変更が17ファイル（pipeline, clip_factory, analytics, video_generator ほか）
  - 未追跡210件の大半は `data/channels/*.bak_pdca_*` 等の PDCA バックアップと生成物

### 1-5. 未解決の課題・ブロッカー

1. **ANTHROPIC_API_KEY 未設定** — PDCAのClaude分析（成功パターン・視聴維持率）が全ch常時スキップ。PDCAループの心臓部が空回りしている。
2. **YouTube カスタムサムネイル権限なし（403）** — アカウント確認が未完了。CTR改善策が全部打てない。
3. **JobQueue の永続化失敗** — `data/job_queue.json.tmp` が作れずキューが保存されない。
4. **競合RSS監視がほぼ全滅** — 登録した9チャンネル全てで fetch 失敗。
5. **台本の完全重複（類似度1.0）** — 重複チェックは検出しているが、生成をブロックできていない。
6. **未コミット274件** — 特に `agent_deprecated` リネームが宙ぶらりん。事故ると復旧困難。
7. **直近30日ショート集計が常に0本** — 全chが「サンプル不足」で判定が進まない原因。

### 1-6. 次にやるべきこと

1. `ANTHROPIC_API_KEY` を環境変数に設定（最優先。これが無いとPDCAが機能しない）
2. YouTube Studio で電話番号確認 → カスタムサムネイル権限を有効化
3. `data/job_queue.json.tmp` の書き込み失敗を調査（ディレクトリ権限 or 親ディレクトリ不在）
4. 未コミット274件を整理してコミット（`.bak_pdca_*` は `.gitignore` へ）
5. 30日窓のショート集計ロジックを修正（全chの判定が止まっている）
6. 重複チェックを「検出」から「生成ブロック」へ格上げ
7. 競合RSS の取得失敗原因を調査（URL形式 or レート制限）

---

## 2. aiseki

**パス**: `/Users/ayukiyamazaki/Developer/aiseki`
**本番**: https://aisekimatch.com（独自ドメイン・HTTP 200）／旧 https://aiseki-xi.vercel.app（まだ200を返す）
**ステータス**: 🟢 **正常** — 技術的に公開をブロックする問題はゼロ

### 2-1. 開発進捗

- アプリ実装は一通り完了（会作成・参加リクエスト・承認・グループチャット・プロフィール・ブロック・招待・通報・退会・PWA・OGP/SEO/セキュリティヘッダ）
- 2026-08-23 に3機能追加: **内部評価（user_reviews）／募集中の会へのアプローチ／飲みスタイルタグ**
- 2026-08-23 に**セキュリティレビュー実施、API直叩きで通っていた4件を修正**（最新コミット）
- 2026-08-22 に独自ドメイン `aisekimatch.com` へ統一、Resend SMTP 本番配信を実測確認（`delivered`）

### 2-2. マイグレーション適用状況 — **未適用はゼロ**

現行 Supabase プロジェクト `melfyxfvhyknqhruytms` に全て適用済み:

| ファイル | 状態 |
|---|---|
| `migration_launch.sql` | ✅ 適用済（08-19） |
| `migration_fixed_join_fee.sql` | ✅ 適用済（08-19） |
| `migration_launch2.sql` | ✅ 適用済（08-19） |
| `migration_reviews_approach_style.sql` | ✅ 適用済（08-23） |
| `migration_security_hardening.sql` | ✅ 適用済（08-23） |

`.e2e-tmp.mjs` の39項目が本番スキーマに対して全て成功。

### 2-3. Vercel デプロイ状態

- プロジェクト `aiseki`（projectId `prj_eXehBy01ZFf7TYhqGI3d2zyvWu8I`）
- 最新本番デプロイ `dpl_G7GC6af9ux669kvvTsSVeXicnYmb`（2026-08-22）／配信JS `assets/index-B1I0jCrz.js`
- ⚠️ **GitHub 連携は無いため、push しても本番には出ない。`vercel deploy --prod` が必須。**
- ⚠️ **最新コミット `efe9980`（セキュリティ修正4件）がデプロイ済みか要確認。** コード変更後のデプロイ記録が HANDOFF に無い。

### 2-4. Git

- ブランチ: `main`（`origin/main` と同期）。他に `feat/branding-refresh-age20` / `feat/codex-ui-refresh` / `feat/stripe-checkout-sky-blue-ui` の3本があるが、**いずれも main にマージ済み**（未マージブランチなし）。
- リモート: https://github.com/zaki21016/aiseki（private）
- 最新5コミット:
  ```
  efe9980 fix(security): API直叩きで通っていた4件を塞ぐ
  a9c769f docs: GitHub連携が無くpushでは本番に出ないことを記録
  66c30fb feat: 内部評価・会へのアプローチ・飲みスタイルタグを追加
  cb46a3b docs: --prebuilt デプロイで接続先が空になる落とし穴を記録
  c61e6d8 refactor: LPのコードを aiseki/lp/ に一式まとめる
  ```
- **未コミット変更: 2件（未追跡のみ）** — `.claude/settings.local.json` / `.e2e-tmp.mjs`。どちらもコード変更ではない。

### 2-5. 未解決の課題・ブロッカー

| 優先 | 内容 |
|---|---|
| 🔴 | **サインアップに CAPTCHA が無い** — 登録ボーナス10,000pt＋紹介3,800pt を自動登録で量産可能。**ポイントは現金化予定なので、決済有効化より先に対処** |
| 🟠 | **実機での動作確認が未実施**（チェックリストは `LAUNCH.md` §5） |
| 🟠 | 通報（`inquiries`）の対応担当者が未決定。管理画面は無く Supabase Table Editor 運用 |
| 🟠 | 利用規約 第23条「当社の本店所在地」が未確定 |
| 🟠 | 提携店舗の飲食店営業許可・深夜酒類提供飲食店営業の届出が未確認 |
| 🟡 | パスワード下限がサーバ側6文字（画面は8文字）／漏洩パスワード検査 無効 |
| 🟡 | パスワード変更に再認証を要求しない設定 |
| 🟡 | Stripe決済は placeholder のまま（意図的） |

⚠️ **Auth設定の変更には地雷あり**: 2026-08-21 に投入した SMTP 設定が翌日 全項目 null に戻った実績あり。Resend APIキーは Supabase 内にしか無く GET でも読めないため、巻き添えで消えると復旧不能。**触るなら Resend APIキーを手元に用意してから。**

### 2-6. 次にやるべきこと

1. `efe9980` が本番に出ているか確認 → 出ていなければ `vercel deploy --prod`
2. CAPTCHA 導入（Resend APIキーを手元に確保してから Auth 設定を触る）
3. 実機で `LAUNCH.md` §5 のチェックリストを消化
4. 運営体制の決定（通報対応者・本店所在地・店舗の営業許可確認）

---

## 3. ai-english-coach

**パス**: `/Users/ayukiyamazaki/Developer/ai-english-coach`
**本番URL**: **未発行**（Vercelプロジェクト未作成 / Gitリモート未設定）
**ステータス**: 🟡 **要対応** — コードは進んでいるが、外部アカウントが1つも無く前に進めない

### 3-1. 開発進捗

| Phase | 内容 | 状況 |
|---|---|---|
| Phase 1 | LINE Bot基本構成・AIテキスト対話MVP・Supabaseユーザー管理 | ✅ コード完了（**実機未検証**） |
| Phase 1.5 | LINE Pay サブスク + 超過チケット | ✅ コード完了（**mock でのみ動作確認**） |
| Phase 2 | 音声対話API統合・利用時間計測・本番デプロイ | ⬜ 着手前 |
| Phase 3 | マイページ・学習レベル設定・文法FB強化 | ⬜ 着手前 |
| Phase 4 | B2B法人展開・分析ダッシュボード | ⬜ 着手前 |

料金モデル: 月額¥7,000 / 10時間 / 超過チケット¥1,200・1h / 無料トライアル7日。

### 3-2. Git

- ブランチ: `main` のみ。未マージブランチなし。**Gitリモート未設定（バックアップが存在しない）**。
- 最新5コミット:
  ```
  a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
  d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
  99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
  eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
  6db3262 feat: phase 1 - AI text dialog MVP with Supabase
  ```
- **未コミット変更: 1件（未追跡）** — `HANDOFF.md`。コード変更はゼロ。

### 3-3. 未解決の課題・ブロッカー

1. **外部アカウントが一つも無い（クリティカルパス）** — LINE公式アカウント / Messaging APIチャンネル / LINE Pay加盟店 / OpenAI APIキー / Supabaseクラウド / Vercel / Gitリモート、**すべて未作成**。
2. **LINE Pay production は審査あり** — リードタイム最長。着手が遅れるほど後ろにずれる。
3. **実 API を一度も叩いていない** — LINE Webhook も LINE Pay も mock のみ。
4. **サブスク解約 API が未実装**（`expirePreapproved`）。課金サービスとして必須。
5. **自動テストがゼロ** — 決済フローの回帰検知が効かない。
6. **特商法表記・利用規約・プライバシーポリシーが未整備** — サブスク課金には必須。
7. **Vercel Cron が Authorization ヘッダを任意付与できない** — `CRON_SECRET` の受け渡し方式を見直す必要あり。
8. **音声（Phase 2）は API 選定 PoC すら未実施**。

### 3-4. 次にやるべきこと

1. LINE Pay 加盟店を申し込む（審査リードタイム最長。今日やるべきはこれ）
2. LINE 公式アカウント + Messaging API チャンネルを発行
3. Gitリモート作成・push（バックアップが無い状態を解消）
4. Supabase クラウド作成 + マイグレーション適用 → Vercel プロジェクト作成
5. ngrok で Webhook 疎通 → LINE Pay sandbox で Reserve→Confirm→regKey を実APIで確認
6. サブスク解約 API の実装

---

## 4. その他プロジェクト（読み取り確認のみ）

### 4-1. fanup — https://fanup-rouge.vercel.app 🟡 要対応

- **状態**: コードは完成、本番は「決済の環境変数待ち」で停止中。サイトは HTTP 200 で公開中。
- 実装済み: 認証〜ポイント購入（Stripe Checkout）〜Webhookでのポイント加算〜支援〜Stripe Connect出金〜メール通知〜Cron締切判定。DBマイグレーション 0000/0001/0002 適用済み。
- 最新コミット: `da58faf chore: Vercel 本番環境変数の設定ヘルパースクリプトを追加` / `e553870 feat: Stripe Connect出金機能実装`
- **未コミット: 24件（すべて未追跡のドキュメント／画像。コード変更ゼロ）** — 事業計画書 docx/pdf/pptx、page-01〜16.jpg、LibreOffice の `lu469vdwg.tmp`（削除可）
- **残タスク**: Stripe本番キー＋Webhook登録 → Resendドメイン検証 → `CRON_SECRET` 生成 → **再デプロイ**（`NEXT_PUBLIC_*`はビルド時埋め込み）→ 決済E2E。既存クリエイター3名の手数料 0.30→0.10 判断。未追跡24件の整理。**Gitリモート未設定（バックアップ無し）**。`README最新.md` が現状と矛盾。
- **集客は未着手。** ai-orchestrator の `fanup_growth` objective は設計のみ・未実装（FanUp側に運用APIルートが必要）。

### 4-2. oripa — https://oripa-omega.vercel.app 🟡 要対応

- **状態**: Phase 1 MVP 完成。サイトは公開中だが**パックが未投入＝実サービスとしては未開業**。
- 実装済み: Stripe決済、ガチャ演出8種、仮在庫（当選後調達）フロー、管理画面、法定表示ページ。
- **未コミット: なし**（作業ツリーはクリーン）
- ⚠️ **ブランチが分岐したまま**: `main` = `cd2119e`（Phase 1 MVP）に対し `feat/stripe-checkout` = `5c15784` が **9コミット先行**。実質の最新は feature ブランチ側。
- **最大のブロッカー: 古物商許可が未申請**（管轄警察署・審査約40日）。取得まで実運用に入れない。
- **残タスク**: 古物商許可申請（最優先） → ブランチ一本化 → Supabase本番作成・SQL適用（`NEXT_PUBLIC_SUPABASE_URL` は現在プレースホルダ）→ Stripeキー・Webhook → 事業者情報9変数 → 再デプロイ → パック投入。**Gitリモート未設定**。
- **決済は未着手**（環境変数がプレースホルダのまま）。

### 4-3. 切り抜きラボ（clip-lab） 🔵 凍結

- youtube-factory 内のチャンネル。`data/channels/clip-lab.json` の **autopilot: false**。スロット定義（平日17:45/19:45・土日12:45/14:45）は残っているが動いていない。
- 2026-08-23 の PDCA 対象チャンネル6件にも含まれず（`summary.json` 参照）。**凍結状態が設定上も確認できた。**
- 再開する場合は autopilot を true に戻すだけだが、`backend/pipeline/clip_factory/` 配下に**未コミットの変更が5ファイル**残っている点に注意。

### 4-4. rhythm-pop 🟡 要対応（完成済みだが未保存）

- 自然言語でリズムゲームを生成するツール。Vite 5 + TypeScript（フレームワーク無し）。
- 最新コミット: `1cfde97 docs: README for URL import + multi-action`
- ⚠️ **未コミット17件 — 大規模リファクタが未保存のまま。** `src/ai/generate.ts` `src/app/App.ts` `src/chart/Chart.ts` `src/game/templates.ts` `api/extract.ts` ほか。`src/chart/demo.ts` は削除済み(staged)。
- **次にやること: とりあえずコミットして保全する。** 現状はマシンが飛んだら消える。

### 4-5. claude-codex-bridge 🟢 完成

- Claude（設計）× Codex UI（実装）を GitHub ブランチ経由で非同期連携させる Claude Code スキル。
- 最新コミット `eb23d8a`（**リポジトリ唯一のコミット**）／**作業ツリーはクリーン**。
- 未コミット: `HANDOFF.md`（未追跡）のみ。
- 追加作業なし。

---

## 5. ユーザーの手動対応が必要なタスク（Claudeでは代行不可）

| # | プロジェクト | 内容 | 緊急度 |
|---|---|---|---|
| 1 | youtube-factory | **YouTube Studio で電話番号確認** → カスタムサムネイル権限を解放（403解消） | 🔴 高 |
| 2 | youtube-factory | **ANTHROPIC_API_KEY の発行・設定** | 🔴 高 |
| 3 | ai-english-coach | **LINE Pay 加盟店申込（production は審査あり）** — リードタイム最長 | 🔴 高 |
| 4 | oripa | **古物商許可の申請**（警察署・審査約40日） — リードタイム最長 | 🔴 高 |
| 5 | ai-english-coach | LINE 公式アカウント / Messaging API チャンネル発行 | 🟠 中 |
| 6 | ai-english-coach | OpenAI APIキー発行・支払い方法登録 | 🟠 中 |
| 7 | fanup | Stripe 本番キー取得・Webhook 登録・Resend ドメイン検証 | 🟠 中 |
| 8 | oripa | Supabase 本番プロジェクト作成・Stripe キー取得 | 🟠 中 |
| 9 | aiseki | **実機での動作確認**（`LAUNCH.md` §5） | 🟠 中 |
| 10 | aiseki | 運営体制の決定（通報対応者・本店所在地・提携店の営業許可確認） | 🟠 中 |
| 11 | fanup / oripa / ai-english-coach | **Gitリモート作成（3プロジェクトともバックアップ無し）** | 🟠 中 |
| 12 | fanup | 既存クリエイター3名の手数料 0.30→0.10 の判断 | 🟡 低 |

---

## 6. 横断的に見えたリスク

1. **バックアップ不在** — fanup / oripa / ai-english-coach の3つに Git リモートが無い。ローカルが飛べば消える。rhythm-pop はリモート以前に**未コミット17件が未保存**。
2. **未コミットの山** — youtube-factory 274件 / rhythm-pop 17件 / fanup 24件。特に youtube-factory の `agent`→`agent_deprecated` リネームが staged 止まりで危険。
3. **審査待ちが2本並走** — oripa の古物商許可（約40日）と ai-english-coach の LINE Pay 審査。どちらも**今日申請しても着地は10月**。申請を後ろに倒すほど全体が遅れる。
4. **収益化の直前で止まっているものが3つ** — fanup（決済env待ち）・oripa（許可待ち）・aiseki（人手の確認待ち）。技術的な難所は全部越えており、詰まっているのは全部「手続き」。

---

_このレポートは読み取り専用で作成されました。youtube-factory 以外のプロジェクトに対する変更は一切行っていません。_
