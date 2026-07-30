# Dispatch引き継ぎ書（2026-07-02）

## ユーザー情報
- 名前: ザキ
- Email: theoffzaki@gmail.com
- 一人称: 「私」（「俺」は使わない）
- 口調: 普通に簡潔に。オラオラ系・強め口調は避ける
- 確認: アクセス・定型確認はスキップ、重要判断だけ質問
- 危険コマンド: 目的・用途・概要を先に提示してから確認

## プロジェクト一覧

### 1. YouTube Factory（メイン）
- パス: `/Users/ayukiyamazaki/Developer/youtube-factory`
- 本番URL: https://youtube-factory-eight.vercel.app
- 内容: ゆっくり解説ショート動画の自動生成・投稿パイプライン（Python FastAPI + Next.js）
- チャンネル:
  - `daily-science`: 「リコとマコトのゆっくり日常科学」（日常の疑問を科学視点で解説）
  - `scp-lab`: 「ゆっくり異常存在SCPラボ」（SCP解説、ショート「一口SCP」）
- 運用: 両チャンネルともショートのみ、1日1本、19:00投稿
- キャラ位置デフォルト: +130pxオフセット

### 2. AI Orchestrator
- パス: `/Users/ayukiyamazaki/Developer/ai-orchestrator`
- ダッシュボード: https://dashboard-woad-chi-18.vercel.app
- ダッシュボードsecret: `e7cf2fd8c75b1e76d020f1c02d109ddd80bf2415ab593c9d`
- 内容: 自律AIエージェント（observe→think→act→check）、YouTube Factory操作用
- 注意: **オーケストラを使う時は明示的に指示があった時のみ**
- GitHubリモート: 未設定

### 3. FanUp
- パス: `/Users/ayukiyamazaki/Developer/fanup`
- 本番URL: https://fanup-rouge.vercel.app
- Vercel projectName: fanup
- 内容: ファンクラブ型クラウドファンディング（All-or-Nothing）、Next.js 16 + Supabase + Stripe
- 成長戦略: クリエイター軸（クリエイターが自分のアカウントでも宣伝してくれる前提）
- Phase 0（決済E2E）: 修正済み、Stripe環境変数のVercel設定が必要

### 4. AI English Coach
- パス: `/Users/ayukiyamazaki/Developer/ai-english-coach`
- LINE Bot英会話コーチ、Next.js+Supabase、Phase 1実装中

## 今回のセッションでやったこと

### 完了
1. **TikTok自動投稿機能** — 正規API（Content Posting API + Login Kit OAuth v2）でYouTube Factoryに統合。コミット済み(`2f5ce1b`)。TikTokアカウント未作成、開発者登録から必要。
2. **B案フォーマット修正** — VideoFormatにshort_illustrationsフィールド追加。本番パイプラインでB案が有効化されるよう修正。コミット済み(`0f262b6`, `d055b90`)。
3. **背景画像復元** — Pexels失敗時のフォールバック背景生成を追加。コミット済み(`d055b90`)。
4. **画像品質全面改善** — DALL-E切替、Pillowフォールバック改善、縦長背景追加、エンコードCRF18。コミット済み(`ee2690e`)。
5. **投稿時間最適化** — 実データ分析で昼12:00が死んでることを確認。7:00/17:00 → 12:00/19:00 → 19:00のみ（1日1本）に変更。コミット済み(`068db0e`)。
6. **YouTube動画削除API** — delete_video()関数とDELETEエンドポイント追加。コミット済み。

### 未完了・ペンディング
1. **再生0の動画50本を非公開にする** — Chrome接続待ち。daily-science 21本 + scp-lab 29本。
2. **OpenAI billing hard limit** — gpt-image-1が使えない。キャラ高解像度化、AI背景生成が保留。billing復旧後にgen_images.pyを実行すれば完了。
3. **TikTokセットアップ** — アカウント作成→開発者登録→アプリ作成→審査申請。手順はdocs/TIKTOK_SETUP.md。
4. **Analytics APIのviews取得が壊れている** — 自動PDCAの時間帯分析が機能していない（全て0を返す）。
5. **daily-science OAuth redirect_uri_mismatch** — UI再認可がブロック中。
6. **GCP consent screen → Published** — 永続OAuth用。ユーザーアクション必要。
7. **過去のSCP非公開動画5本** — dItYJed2Qog等。手動公開 or スコープ拡張が必要。
8. **FanUp Phase 0 env vars** — Stripe keys, Webhook Secret, CRON_SECRETをVercelに設定して再デプロイ。
9. **FanUp orchestrator plugin** — fanup_growth.py設計済み未実装。FanUp側APIルート先に必要。

## 運用ルール（厳守）
- 両チャンネル: ショートのみ、1日1本、19:00
- 動画に大きな修正・画像配置時はサンプルを送って許可してから変更
- オーケストラは明示的指示があった時のみ使用
- 1リポジトリに複数タスク並行禁止、必ずマージしてから終了
- 投稿設定変更は必ず実データ分析に基づく（PDCA厳守）
- 成長戦略は自分で考えて提案、聞くな
- 演出実装前に同ジャンル競合を横断分析して学習してから設計
- 不要プロジェクトは Developer/archive/ に格納

## 最新のgitログ（youtube-factory）
```
ee2690e feat: 画像品質全面改善 - DALL-E切替・キャラ高解像度化・縦長背景・エンコード品質
d055b90 fix: 背景画像の描画を復元 + VideoFormat short_illustrations修正
0f262b6 fix: VideoFormatにshort_illustrations追加、B案が本番で有効化されるよう修正
fe39000 fix: B案フォーマット反映 + 投稿時間を最適化（12:00/19:00）
068db0e fix: 投稿を1日1本に変更（パフォーマンス分析に基づく最適化）
2f5ce1b feat: TikTok自動投稿機能を追加 + 設定バリデーション改善
```
