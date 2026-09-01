# 全プロジェクト引き継ぎレポート — 2026-08-25

生成: 2026-08-25（自動タスク `daily-project-handoff`）
調査方法: 各リポジトリの**読み取りのみ**（git・設定 JSON・HANDOFF・ログ・PDCA メモリ）。
**youtube-factory 以外は一切書き込みしていない。** 本レポートの保存先も youtube-factory 内のみ。

---

## 0. 一覧サマリ

| プロジェクト | URL | ステータス | 未コミット | 未マージブランチ |
|---|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 要対応 | **264 件** | なし（`main` のみ / **リモート未設定**） |
| aiseki | https://aisekimatch.com （旧 https://aiseki-xi.vercel.app） | 🟢 正常 | 2 件（ゴミのみ） | なし（origin と同期済み） |
| ai-english-coach | 未発行 | 🟡 要対応（インフラ未着手） | 1 件（HANDOFF.md） | なし（**リモート未設定**） |
| fanup | https://fanup-rouge.vercel.app | 🟡 要対応（決済未開通） | 25 件 | なし |
| oripa | https://oripa-omega.vercel.app | 🟡 要対応（許認可待ち） | 1 件 | **`feat/stripe-checkout` 作業中** |
| 切り抜きラボ（clip-lab） | youtube-factory 内 | 🔴 2日連続で自動生成失敗 | — | — |
| rhythm-pop | ローカルのみ | 🟢 完成（未コミット19件） | 19 件 | なし |
| claude-codex-bridge | スキル本体 | 🟢 完成 | 1 件 | なし |

**本日の最重要トピック**: YouTube の OAuth リフレッシュトークンが**再び失効**し、08-25 09:00 の scp-lab が未投稿になった。日中に再認可されて 17:00 以降は回復したが、**根本原因（GCP 同意画面がテスト中＝トークン寿命7日）は未解消**。放置すれば約7日周期で再発する。

---

## 1. youtube-factory

**パス**: `/Users/ayukiyamazaki/Developer/youtube-factory`
**本番 URL**: https://youtube-factory-eight.vercel.app （認証ゲート付き）
**ステータス**: 🟡 **要対応** — 分析は復旧、投稿も大半は回っているが、**OAuth 失効の再発と切り抜き2chの生成失敗が残っている**

### 1-1. チャンネル別 autopilot 状態（`data/channels/*.json` 実測・全 11ch）

| チャンネル | 名前 | autopilot | 投稿枠(JST) | 種別 | キュー残 |
|---|---|---|---|---:|---:|
| `scp-lab` | ゆっくり異常存在SCPラボ | ✅ ON | 平日 9:00 / 19:00・休日 13:00 / 19:00 | short | 14 |
| `daily-science` | リコとマコトのゆっくり日常科学 | ✅ ON | 平日 17:00・休日 13:00 | short | 10 |
| `company-facts` | 企業のホンネ | ✅ ON | 平日 17:00・休日 14:00 | short | 10 |
| `pokemon-lab` | ゆっくりポケラボ | ✅ ON | 17:30 / 休日 12:00 | short | 7 |
| `2ch-matome` | ゆっくり2chスレまとめ劇場 | ✅ ON | 平日 18:00・休日 12:00 | short | 16 |
| `yokai-watch` | ゆっくり妖怪ラボ | ✅ ON | 平日 19:00・休日 12:00 | short | 11 |
| `clip-lab` | ゆっくり解説 切り抜きラボ | ✅ ON | 毎日 17:45 | clip | 2 |
| `clip-fukada` | 深田えいみ 切り抜き | ✅ ON | 毎日 20:00 | clip | 2 |
| `clip-kaneko` | 金子みゆ 切り抜き | ✅ ON | 毎日 20:30 | clip | 3 |
| `akashic-librarian` | ラグナロクの司書 | ❌ OFF | 18:45 | short | 0 |
| `fake-paper` | 虚構論文チャンネル | ❌ OFF | 19:30 | short | 13 |

→ **9ch 稼働 / 2ch 停止中**（前日から変化なし）。

### 1-2. 直近の投稿状況（08-25）

**登録者取得は復旧した。** 08-24 は全 6ch が `null` だったが、08-25 23:00 の PDCA では実数が入っている。

| チャンネル | 登録者 | 総再生 | 本数 | 前回(08-23)比 |
|---|---:|---:|---:|---|
| `scp-lab` | **135** | 138,125 | 157 | 横ばい（±0） |
| `daily-science` | **56** | 175,126 | 185 | **+1** |
| `pokemon-lab` | **13** | 40,778 | 30 | 横ばい |
| `yokai-watch` | **10** | 36,619 | 30 | 横ばい |
| `2ch-matome` | **6** | 24,859 | 26 | **+1** |
| `fake-paper` | 0 | 1,099 | 1 | 横ばい |
| 合計 | **220** | 416,606 | 429 | +2 |

**08-25 の投稿実績: 成功 7本 / 失敗 3本**

| 時刻 | チャンネル | 結果 |
|---|---|---|
| 09:00 | scp-lab | ❌ **未投稿**（OAuth トークン失効。動画は `~/Desktop/動画出力用/` に生成済みで残っている） |
| 17:00 | company-facts | ✅ https://youtube.com/watch?v=BuCRdC0KOnE |
| 17:00 | daily-science | ✅ https://youtube.com/watch?v=aIFiUiSxKqU |
| 17:30 | pokemon-lab | ✅ https://youtube.com/watch?v=l1RP8OJYEN8 |
| 17:45 | clip-lab | ❌ 失敗（未使用の切り抜き区間が残っていない） |
| 18:00 | 2ch-matome | ✅ https://youtube.com/watch?v=spL7feJGAi0 |
| 19:00 | scp-lab | ✅ https://youtube.com/watch?v=3HCnvM6A7sA |
| 19:00 | yokai-watch | ✅ https://youtube.com/watch?v=0P7LU1RGUX0 |
| 20:00 | clip-fukada | ❌ 失敗（区間ダウンロードで ffmpeg エラー） |
| 20:30 | clip-kaneko | ✅ https://youtube.com/watch?v=sIMwOdw1J4w |

### 1-3. 検出されているエラー

| # | エラー | 発生箇所 | 影響・状況 |
|---|---|---|---|
| 1 | `invalid_grant: Token has been expired or revoked` | 全チャンネルの OAuth | **08-25 朝に再発。** 09:00 の scp-lab が未投稿。日中に再認可されて 17:00 以降は復旧。**根本原因は GCP 同意画面が「テスト中」＝リフレッシュトークン寿命7日**（`backend/check_youtube_tokens.py` の説明どおり）。**約7日周期で必ず再発する** |
| 2 | `未使用の切り抜き区間が残っていません`（同一元動画） | clip-lab autopilot | **08-24・08-25 の2日連続で失敗。** 同じヒカキン回を掴み続けており、素材ローテーションが進んでいない |
| 3 | `区間ダウンロードに失敗（yjF8W6-BZd4）: ffmpeg exited with code 183` | clip-fukada autopilot | 08-25 の1本が生成できず。ffmpeg の `-22 Invalid argument` |
| 4 | `HttpError 403 サムネイル設定失敗` | clip-kaneko ほか | 生成サムネが反映されない。**YouTube アカウントの電話番号認証が必要（ユーザー手動）** |
| 5 | `ANTHROPIC_API_KEY 未設定` → Claude 分析スキップ | 成功パターン分析・視聴維持率分析 | **前日から未解消。** 台本生成へのフィードバックが効いていない |
| 6 | `ScenarioValidator` スコア低下（5〜55点） | company-facts 0 / yokai-watch 5 / daily-science 45 / pokemon-lab 45 / scp-lab 55 | 「中盤フックの転換ワードなし」「最終行に登録誘導なし」が全ch共通。**08-24 に CTA を高評価優先へ書き換えた変更とバリデータのルールが噛み合っていない可能性** |
| 7 | `rss fetch HTTP 404/500` が競合チャンネルで多発 | 競合RSSスキャン | 死んだ競合IDが登録に残っている。実害は小さいがログを汚す |
| 8 | `Image API error: HTTP Error 400` | 画像生成 | OpenAI billing hard limit（既知） |

### 1-4. 未マージブランチ・未コミット変更

- **ブランチ**: `main` のみ。未マージブランチ **なし**。**リモート未設定**（`git remote -v` が空）
- **未コミット: 264 件**（08-24 の 216 件からさらに +48）
  - 内訳: `data/ab_tests` 155 / `assets/characters` 33 / `data/scenarios` 20 / `data/channels` 8 / `data/channels_orchestrator` 6 / `data/originality` 6 / `data/series_links` 6 / その他
  - コード変更: `backend/api_phase4.py`・`backend/pipeline/auto_scenario/generator.py`・`backend/pipeline/youtube_oauth.py`・`backend/tests/test_short_format.py`
  - **新規未追跡（無保護）**: `backend/check_youtube_tokens.py`・`backend/republish_short.py`・`assets/characters/_backup_20260824/`
- 🔴 **リモート未設定 = バックアップ皆無**が 08-24 から改善していない。切り抜き基盤・OAuth 診断スクリプト・立ち絵の修正がすべてローカル1箇所にしか無い。

### 1-5. PDCA で検出された課題と対応状況

| 課題 | 対応状況 |
|---|---|
| 登録者ソースの取得失敗（08-24 の最大問題） | ✅ **解消。** 08-25 は全6chで実数を取得できている |
| OAuth 失効で 08-24 に2本未投稿 | 🔶 **部分対応。** 診断スクリプト `check_youtube_tokens.py` と後追い投稿スクリプト `republish_short.py` を新設。**ただし未投稿3本は依然未公開、同意画面の本番公開も未実施** |
| OAuth 失敗理由がログに出ない | ✅ 解消（`youtube_oauth.py` の握り潰しを修正済み。今回の再発時に理由が即座に判明した） |
| 立ち絵のアルファハロー（サムネ実害） | ✅ 解消（32ファイル修正済み・バックアップあり） |
| CTA を高評価優先へ | ✅ 全5ch適用済み。ただし §1-3 #6 でバリデータが落ちている点は要確認 |
| サムネにその動画固有のビジュアルが無い | ⚠️ **未解決。** 08-24 に「最大の残課題」と記録。同一ch内で全サムネが同一構成 |
| テーマ重複（daily-science 15件・類似度1.00が複数） | 🔶 blacklist 9語追加済み。08-25 の重複ペアは 2ch-matome 4件まで減少 |
| 2ch-matome の「ワイ、〇〇歴N年やけど質問ある？」テンプレ飽和 | ⚠️ **要判断・未対応。** 08-25 も類似ペア3件が同テンプレ。当たり枠でもあるため機械的な blacklist は不可 |
| pokemon-lab の完全同一タイトル2本 | ⚠️ 検出のみ。削除・統合は未対応 |
| 再生0の動画の棚卸し | ⚠️ 未着手 |
| clip-lab の素材枯渇 | 🔴 **新規・未対応。** 2日連続で同じ元動画にぶつかって失敗。許諾済み在庫が構造的に薄い（ひろゆき本人chは100本中4本のみ許諾文言あり） |
| clip-fukada の公開前目視ゲート | ⚠️ 未対応（無人運用のリスクとして残置） |

### 1-6. 次にやるべきこと（優先順）

1. 🔴 **GCP OAuth 同意画面を「本番」に公開する**（**ユーザー手動**）— これをやらないと約7日ごとに全ch投稿が止まる。今回で2回目の発生
2. 🔴 **未投稿3本を `republish_short.py` で後追い公開する** — scp-lab『SCP-179 太陽系の番人』(08-24)・yokai-watch『#12 両面宿儺』(08-24)・scp-lab『#99 SCP-956 子供割り人形』(08-25)。いずれも `~/Desktop/動画出力用/` に生成済み
3. 🔴 **Git リモートを用意して push** — 264件の未コミットとローカル限定の歴史。事故ったら全消滅
4. 🟠 **clip-lab の素材ローテーション修正** — 同じ元動画で2日連続失敗。許諾済みチャンネルの追加か、消費済み判定の見直し
5. 🟠 **ScenarioValidator のスコア低下を調査** — 5ch すべてで低スコア。08-24 の CTA 変更との整合を確認
6. 🟡 カスタムサムネイル権限（YouTube アカウントの電話番号認証）を通す（**ユーザー手動**）
7. 🟡 Anthropic API キー問題の解消（またはキー非依存の Claude タスク方式へ移行）
8. 🟡 clip-fukada の ffmpeg エラー（code 183）の調査
9. 🟢 サムネへの動画固有ビジュアル導入（本編用に生成済みの `short_illustrations` を流用可能）
10. 🟢 `akashic-librarian` / `fake-paper` の autopilot 有効化を判断
11. 🟢 死んだ競合RSS ID の掃除

---

## 2. aiseki

**パス**: `/Users/ayukiyamazaki/Developer/aiseki`
**本番 URL**: **https://aisekimatch.com**（旧: https://aiseki-xi.vercel.app — まだ 200）
**ステータス**: 🟢 **正常** — 本日も活発に開発が進んでいる。P0（公開ブロッカー）は全消化済み

### 2-1. 開発進捗

グループ相席マッチング（React 18 + Vite 6 / Supabase / Vercel）。ビジネスロジックは PL/pgSQL + RLS 側。

**08-25 は3コミットが入った活発な日**:

| コミット | 時刻 | 内容 |
|---|---|---|
| `b4e08da` | 18:48 | **店舗カタログを撤廃**。ユーザーが店名・エリアを自由入力する方式に変更（`ShopsScreen.jsx` 削除・296行削減） |
| `6cf1f9a` | 20:26 | **Stripe 決済を有効化**。登録ボーナス 5,000pt を「カード登録後に付与」へ変更。`card_registered` 列＋トリガーで二重取得を防止、`grant_card_bonus()` は service_role 専用で冪等 |
| `338b979` | 21:07 | **運営用管理画面 `/admin` を新設**。通報・お問い合わせ（`inquiries`）の確認と対応状況の更新。`ADMIN_EMAILS` はサーバ側のみが出典 |

これで HANDOFF §5 の P1-7（通報の確認導線）と P2-11（Stripe 有効化）が実質的に消化された。

### 2-2. マイグレーション適用状態

`supabase/` 配下に 16 本の SQL。最新の `migration_card_bonus.sql` はコミットメッセージ上「**適用済み**」と明記されている。**未適用のマイグレーションは検出されず。**

### 2-3. Vercel デプロイ状態

- Vercel プロジェクト `aiseki` / projectId `prj_eXehBy01ZFf7TYhqGI3d2zyvWu8I`
- 08-22 に独自ドメインへ移行後、コード変更のたびに `vercel deploy --prod` が必要な運用
- ⚠️ **08-25 の3コミット（特に `/admin` と Stripe 有効化）が本番へデプロイ済みかはリポジトリからは確認できない。要確認**
- ⚠️ 環境変数を変えた場合は**再デプロイするまで実行時に反映されない**（HANDOFF に明記された過去の罠）

### 2-4. 未マージブランチ・未コミット変更

- **ブランチ**: `main` のみ。`origin/main` と **完全同期（ahead 0 / behind 0）**。未マージブランチなし
- **未コミット: 2 件のみ** — `.claude/settings.local.json`・`.introspect.mjs`（どちらも作業用のゴミ。コミット不要）
- Git リモート: https://github.com/zaki21016/aiseki（private）

### 2-5. 未解決の課題・ブロッカー

| 項目 | 状況 |
|---|---|
| **`theoffzaki@gmail.com` のアカウントが未作成** | `/admin` を開けない。**ユーザー手動** |
| 実機での動作確認 | 未実施（`LAUNCH.md` §5 のチェックリスト）。**ユーザー手動** |
| サインアップの CAPTCHA | **未対応。** 5,000pt の登録ボーナスをカード登録に紐づけたことでリスクは下がったが、紹介ボーナス 3,800pt の自動量産余地は残る |
| 利用規約 第23条「当社の本店所在地」 | 実在の所在地へ差し替えが必要。**ユーザー手動** |
| 提携店舗の飲食店営業許可・深夜酒類提供の届出確認 | 未確認。**ユーザー手動** |
| `STRIPE_WEBHOOK_SECRET` | 未設定のあいだ webhook は 503。`confirm-card` 経路で代替中 |
| プッシュ通知・参加者の途中離脱・本人確認バッジ | いずれも未実装（P3） |
| HANDOFF.md の記述が一部古い | §5 P1-7 に「管理画面は無い」と書かれているが 08-25 に実装済み。次回更新時に反映を |

### 2-6. 次にやるべきこと

1. 08-25 の3コミットが本番にデプロイされているか確認（未なら `vercel deploy --prod`）
2. `theoffzaki@gmail.com` でアカウント登録 →`/admin` の動作確認（**ユーザー手動**）
3. 実機チェックリストの消化（**ユーザー手動**）
4. CAPTCHA 導入
5. 利用規約の所在地を実在のものへ

---

## 3. ai-english-coach

**パス**: `/Users/ayukiyamazaki/Developer/ai-english-coach`
**本番 URL**: **未発行**
**ステータス**: 🟡 **要対応** — コードは Phase 1 + 1.5 まで完成しているが、**08-18 を最後に開発が止まっており、インフラは一切着手されていない**

### 3-1. 開発進捗

LINE Bot 型の AI 英会話コーチ（月額 ¥7,000 / 10時間、超過チケット ¥1,200/h、無料トライアル7日）。

| フェーズ | 内容 | 状況 |
|---|---|---|
| Phase 1 | LINE Bot 基本構成・AIテキスト対話MVP・Supabase ユーザー管理 | ✅ コード完了（**実機未検証**） |
| Phase 1.5 | LINE Pay サブスク + 超過チケット | ✅ コード完了（**mock でのみ動作確認**） |
| Phase 2 | 音声対話API統合・利用時間計測（実機）・本番デプロイ | ⛔ 着手前 |
| Phase 3 | マイページ・学習レベル設定・文法フィードバック強化 | ⛔ 着手前 |
| Phase 4 | B2B法人向け展開・分析ダッシュボード | ⛔ 着手前 |

実装済み: DB スキーマ（`users`/`conversations`/`messages`/`usage_logs`/`subscriptions`/`payments`/`tickets`）、LINE Webhook（署名検証付き）、OpenAI コーチ応答（4ステップ学習ルール）、月間利用時間管理、LINE Pay v3 クライアント（Reserve/Confirm/Preapproved/Refund + モック）、月次自動更新 cron、ローカル検証用の debug / mock 画面。

### 3-2. 未コミット変更・ブランチ

- **ブランチ**: `main` のみ。未マージブランチなし。**Git リモート未設定**
- **未コミット: 1 件** — `HANDOFF.md`（未追跡）。**引き継ぎ書そのものが Git に入っていない**
- 最終コミット: **2026-08-18 22:14**（1週間停滞）

### 3-3. 未解決の課題・ブロッカー

全部が「外部サービスの登録が済んでいない」ことに起因する。

| ブロッカー | 影響 | 種別 |
|---|---|---|
| **LINE Pay 加盟店 未申込**（sandbox・production とも） | 課金が一切できない。**審査リードタイムが最長** | **ユーザー手動** |
| LINE 公式アカウント / Messaging API チャンネル 未作成 | Bot が動かせない | **ユーザー手動** |
| OpenAI API キー 未発行 | AI 応答が動かない | **ユーザー手動** |
| Supabase クラウドプロジェクト 未作成 | 本番DBが無い | **ユーザー手動** |
| Vercel プロジェクト 未作成（`vercel.json`・`.vercel/` も無し） | デプロイ先が無い | **ユーザー手動** |
| Git リモート 未設定 | バックアップ皆無 | |
| Vercel Cron 未登録 | 月次課金が回らない | |
| 実機での動作確認 ゼロ | Phase 1・1.5 とも一度も本番相当で動いていない | |

### 3-4. 次にやるべきこと

1. 🔴 **LINE Pay 本番加盟店を申し込む**（審査が最長。今すぐ出すべき）— **ユーザー手動**
2. 🔴 `HANDOFF.md` をコミット + **GitHub リポジトリを作成して push**
3. 🟠 LINE 公式アカウント + Messaging API チャンネル作成 — **ユーザー手動**
4. 🟠 OpenAI API キー発行 → ローカルで `npx supabase start` + debug 画面で対話を実地確認
5. 🟡 Supabase クラウド → Vercel プロジェクト → 環境変数 → `crons` 定義 → デプロイ
6. 🟡 Phase 2（音声）着手の可否を判断

---

## 4. 全プロジェクト進捗サマリ

### 4-1. ステータス一覧

| # | プロジェクト | URL | ステータス | ひとことで言うと |
|---|---|---|---|---|
| 1 | **youtube-factory** | https://youtube-factory-eight.vercel.app | 🟡 要対応 | 9ch 自動投稿中・登録者計 220人。OAuth が7日周期で失効する問題が未解決 |
| 2 | **aiseki** | https://aiseki-xi.vercel.app（現行 https://aisekimatch.com） | 🟢 正常 | 本日 Stripe 有効化＋管理画面追加。技術的ブロッカーは無し |
| 3 | **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | コード完成。Stripe/Resend の環境変数が「後で入力」のまま |
| 4 | **oripa** | https://oripa-omega.vercel.app | 🟡 Phase 1 MVP・決済未着手 | 古物商許可待ち（審査40日）。`feat/stripe-checkout` が未マージ |
| 5 | **ai-english-coach** | 未発行 | 🟡 Phase 1 テキスト版完了・音声/課金未着手 | 外部サービス登録が全部未着手。08-18 から停滞 |
| 6 | **切り抜きラボ（clip-lab）** | youtube-factory 内 | 🔴 凍結解除済みだが2日連続で生成失敗 | 素材枯渇。許諾済み在庫が構造的に薄い |
| 7 | **rhythm-pop** | ローカルのみ | 🟢 完成済み | 06-22 で停止。アーカイブ予定。未コミット19件だけ注意 |
| 8 | **claude-codex-bridge** | スキル本体 | 🟢 完成済み | 07-04 で完成。Dispatch 連携を直接実装するなら不要になる可能性 |

### 4-2. YouTube チャンネル別 登録者数・autopilot 状態

| チャンネル | 登録者 | 総再生 | 本数 | autopilot | 本日の投稿 |
|---|---:|---:|---:|---|---|
| ゆっくり異常存在SCPラボ | **135** | 138,125 | 157 | ✅ ON | 1本成功 / 1本 OAuth 失効で未投稿 |
| リコとマコトのゆっくり日常科学 | **56** | 175,126 | 185 | ✅ ON | ✅ 1本 |
| ゆっくりポケラボ | **13** | 40,778 | 30 | ✅ ON | ✅ 1本 |
| ゆっくり妖怪ラボ | **10** | 36,619 | 30 | ✅ ON | ✅ 1本 |
| ゆっくり2chスレまとめ劇場 | **6** | 24,859 | 26 | ✅ ON | ✅ 1本 |
| 企業のホンネ | 5（08-15 時点） | 4,630 | — | ✅ ON | ✅ 1本 |
| 虚構論文チャンネル | 0 | 1,099 | 1 | ❌ OFF | — |
| ゆっくり解説 切り抜きラボ | — | — | — | ✅ ON | ❌ 失敗（素材枯渇） |
| 深田えいみ 切り抜き | — | — | — | ✅ ON | ❌ 失敗（ffmpeg） |
| 金子みゆ 切り抜き | — | — | — | ✅ ON | ✅ 1本 |
| ラグナロクの司書 | — | — | — | ❌ OFF | — |
| **合計** | **約220** | **416,606+** | **429+** | 9ON/2OFF | **7本成功 / 3本失敗** |

### 4-3. 残タスク一覧（プロジェクト横断・優先度順）

**🔴 最優先（放置すると実害が出続ける）**

1. GCP OAuth 同意画面を「本番」公開 → YouTube 全ch投稿停止の再発防止【ユーザー手動】
2. 未投稿3本の後追い公開（SCP-179・両面宿儺・SCP-956）
3. youtube-factory の Git リモート作成 + push（264件がローカル限定）
4. ai-english-coach の LINE Pay 加盟店申込（審査最長）【ユーザー手動】

**🟠 次に効くもの**

5. clip-lab の素材ローテーション修正（2日連続失敗）
6. ScenarioValidator の低スコアを調査（全5ch）
7. aiseki の 08-25 分デプロイ確認
8. oripa の古物商許可申請（審査約40日）【ユーザー手動】
9. fanup の Stripe / Resend 環境変数投入【ユーザー手動】
10. ai-english-coach を GitHub へ push

**🟡 準備が整い次第**

11. YouTube カスタムサムネイル権限（電話番号認証）【ユーザー手動】
12. Anthropic API キー問題の解消
13. aiseki の CAPTCHA 導入・利用規約の所在地差し替え【一部ユーザー手動】
14. oripa の `feat/stripe-checkout` → `main` マージ + 再デプロイ
15. サムネへの動画固有ビジュアル導入

**🟢 判断待ち**

16. `akashic-librarian` / `fake-paper` の autopilot 有効化
17. rhythm-pop・claude-codex-bridge・ai-orchestrator のアーカイブ判断
18. fanup 既存クリエイター3名の `platform_fee_rate` 0.30→0.10 の判断【ユーザー手動】

### 4-4. ユーザーの手を待っているタスク（Claude 側では進められないもの）

| # | タスク | プロジェクト | リードタイム |
|---|---|---|---|
| 1 | **GCP OAuth 同意画面を「本番」に公開** | youtube-factory | 即〜数日（審査あり） |
| 2 | YouTube アカウントの電話番号認証（カスタムサムネ権限） | youtube-factory | 即日 |
| 3 | OpenAI の課金上限を上げる（画像生成 400 エラー） | youtube-factory | 即日 |
| 4 | Anthropic API キーの再発行・設定 | youtube-factory | 即日 |
| 5 | `theoffzaki@gmail.com` でアカウント登録（`/admin` を開くため） | aiseki | 即日 |
| 6 | 実機での動作確認（`LAUNCH.md` §5） | aiseki | 半日 |
| 7 | 利用規約 第23条の本店所在地を実在のものへ | aiseki | 即日 |
| 8 | 提携店舗の飲食店営業許可・深夜酒類提供届出の確認 | aiseki | 数日 |
| 9 | **LINE Pay 本番加盟店 申込** | ai-english-coach | **審査が最長** |
| 10 | LINE 公式アカウント + Messaging API チャンネル作成 | ai-english-coach | 即日 |
| 11 | OpenAI API キー発行 | ai-english-coach | 即日 |
| 12 | Supabase / Vercel プロジェクト作成 | ai-english-coach | 即日 |
| 13 | Stripe キー取得 → Vercel 投入 + Webhook 登録 | fanup | 即日 |
| 14 | Resend ドメイン設定 → `RESEND_API_KEY` 投入 | fanup | 即日 |
| 15 | **古物商許可の申請**（管轄警察署） | oripa | **審査約40日** |
| 16 | 事業者情報9件を Vercel 環境変数へ | oripa | 即日 |
| 17 | Supabase / Stripe の実キー設定 | oripa | 即日 |

---

## 5. 調査の限界（明記しておくこと）

- **本番の稼働確認はしていない。** URL への疎通確認はサンドボックスから行っていないため、各 URL のステータスは HANDOFF・過去レポート・リポジトリの記述に基づく。
- **Vercel の最新デプロイ状態は API 経由で確認していない。** aiseki の 08-25 分がデプロイ済みかは未確認。
- **YouTube の登録者数は 08-25 23:00 の PDCA レポート（`data/reports/2026-08-25/report.md`）の値**。company-facts は当該レポートの対象外のため 08-15 時点の値を併記している。
- **fanup / oripa / rhythm-pop / claude-codex-bridge は git 情報のみを読み取った**（コード・設定の中身は読んでいない）。ステータスは `全プロジェクト進捗.md`（08-11）と前回レポート（08-24）に基づく。
- **youtube-factory 以外への書き込みは一切していない。**
