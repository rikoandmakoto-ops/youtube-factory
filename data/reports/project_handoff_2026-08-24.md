# 全プロジェクト引き継ぎレポート — 2026-08-24

生成: 2026-08-24（自動タスク `daily-project-handoff`）
調査方法: 各リポジトリの読み取りのみ（git・設定 JSON・HANDOFF/TODO・ログ）。**youtube-factory 以外は一切書き込みしていない。**

---

## 0. 一覧サマリ

| プロジェクト | URL | ステータス | 未コミット | 未マージブランチ |
|---|---|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 要対応 | **216 件** | なし（`main` のみ） |
| aiseki | https://aisekimatch.com （旧 https://aiseki-xi.vercel.app） | 🟢 正常 | 3 件（ゴミのみ） | なし |
| ai-english-coach | 未発行 | 🟡 要対応（インフラ未着手） | 1 件（HANDOFF.md） | なし |
| fanup | https://fanup-rouge.vercel.app | 🟡 要対応（決済未開通） | 25 件 | なし |
| oripa | https://oripa-omega.vercel.app | 🟡 要対応（許認可待ち） | 1 件 | **`feat/stripe-checkout` 作業中** |
| 切り抜きラボ（clip-lab） | youtube-factory 内 | 🟢 2026-08-24 に凍結解除 | — | — |
| rhythm-pop | ローカルのみ | 🟢 完成（未コミット注意） | 19 件 | なし |
| claude-codex-bridge | スキル本体 | 🟢 完成 | 1 件 | なし |

---

## 1. youtube-factory

**パス**: `/Users/ayukiyamazaki/Developer/youtube-factory`
**本番 URL**: https://youtube-factory-eight.vercel.app （認証ゲート付き）
**ステータス**: 🟡 **要対応** — 自動投稿は回っているが、**分析系が壊れて PDCA が判断保留になっている**

### 1-1. チャンネル別 autopilot 状態（`data/channels/*.json` 実測・全 11ch）

| チャンネル | 名前 | autopilot | 投稿スロット | 種別 | テーマ在庫 |
|---|---|---|---|---|---:|
| `scp-lab` | ゆっくり異常存在SCPラボ | ✅ ON | 平日 9:00 / 19:00・休日 13:00 / 19:00 | short | 17 |
| `daily-science` | リコとマコトのゆっくり日常科学 | ✅ ON | 平日 17:00・休日 13:00 | short | 11 |
| `company-facts` | 企業のホンネ | ✅ ON | 平日 17:00・休日 14:00 | short | 11 |
| `pokemon-lab` | ゆっくりポケラボ | ✅ ON | 平日 17:30・休日 12:00 | short | 8 |
| `2ch-matome` | ゆっくり2chスレまとめ劇場 | ✅ ON | 平日 18:00・休日 12:00 | short | 18 |
| `yokai-watch` | ゆっくり妖怪ラボ | ✅ ON | 平日 19:00・休日 12:00 | short | 12 |
| `clip-lab` | 切り抜きラボ | ✅ ON（**08-24 に凍結解除**） | 毎日 17:45 | clip | —（clip は未使用） |
| `clip-fukada` | 深田えいみ 切り抜き | ✅ ON（**08-24 稼働開始**） | 毎日 20:00 | clip | — |
| `clip-kaneko` | 金子みゆ 切り抜き | ✅ ON（**08-24 稼働開始**） | 毎日 20:30 | clip | — |
| `akashic-librarian` | ラグナロクの司書 | ❌ OFF | 18:45 | short | 2 |
| `fake-paper` | 虚構論文チャンネル | ❌ OFF | 19:30 | short | 13 |

→ **9ch 稼働 / 2ch 停止中。**

### 1-2. 直近の投稿状況（`data/reports/latest.md` 2026-08-24 23:00 生成）

| チャンネル | 登録者 | 直近30日ショート | ジャンル別トップ | 実績ベスト投稿時刻 |
|---|---|---|---|---|
| `2ch-matome` | **—（取得失敗）** | 0本と表示 | その他 850 | 月 18:00（937） |
| `daily-science` | **—** | 0本と表示 | 睡眠・夢 775 | 火 17:00（986） |
| `scp-lab` | **—** | — | — | — |
| `pokemon-lab` | **—** | — | — | — |
| `yokai-watch` | **—** | — | その他 1224 | 月 19:00（1873） |
| `fake-paper` | 0 | 総再生 1099 / 1本 | — | — |

⚠️ **6ch すべてが「登録者ソースが取得できないため判断保留」。**
2026-08-18 時点のレポートでは scp-lab 133 / daily-science 52 / pokemon-lab 11 / yokai-watch 10 / 2ch-matome 4 と数字が取れていた。**この 6 日で分析パイプラインの登録者取得が壊れている。**
一方で動画単位の再生数スナップショットは正常に取れており（yokai-watch 最高 2233、2ch-matome 1802 など）、**投稿そのものは止まっていない。**

### 1-3. 検出されているエラー

| エラー | 発生箇所 | 影響 |
|---|---|---|
| `登録者ソースが取得できない` | 全 short チャンネル | **PDCA の判定が全部保留。最大の問題** |
| `ANTHROPIC_API_KEY 未設定` → Claude 分析スキップ | 成功パターン分析・視聴維持率分析 | 台本生成へのフィードバックが効いていない |
| `HttpError 403 サムネイル設定失敗`（custom thumbnail 権限なし） | `logs/backend.log`・scp-lab 実行ログ | 生成サムネが反映されない動画がある |
| `DALL-E API error: HTTP Error 400` | 画像生成ログ | OpenAI billing hard limit（HANDOFF §6-10 と一致） |

### 1-4. 未マージブランチ・未コミット変更

- **ブランチ**: `main` のみ。未マージブランチ **なし**。リモート **未設定**（214+ コミットがローカルのみ＝**バックアップ皆無**）
- **未コミット: 216 件**（HANDOFF 記載の 114 件から倍増）
  - 変更: `backend/pipeline/clip_factory/*`（engines/local・noimos・segments・sources・pipeline）、`analytics/*`、`auto_scenario/*`、`data/channels/*.json` 全チャンネル、`data/pdca-memory/*`
  - **新規未追跡（無保護）**: `clip_factory/acquisition.py` `captions.py` `external.py` `visual_guard.py` `engines/noimos_client.py`、`narration_video.py`、`youtube_reporting.py`、`setup_reach_jobs.py`、テスト 2 本、`data/ab_tests/` ほか
  - → **切り抜き基盤まるごとが Git 管理外。ここが飛ぶと 08-24 の作業が全消滅する。**

### 1-5. PDCA で検出された課題と対応状況

| 課題 | 対応状況 |
|---|---|
| daily-science 重複テーマ（酸素・センサー・本と睡眠） | ✅ blacklist 追加済み |
| daily-science 宇宙・天体が平均 0 再生 | ✅ genre_blacklist 済み |
| scp-lab SCP-173 重複 | ✅ blacklist 済み（上位動画は適用前の投稿） |
| 2ch-matome 初動 0 再生 | ✅ 誤検知と判明（計測ラグ）。ただし**初動速度は全ch最下位のまま**＝未解決 |
| pokemon-lab 完全同一タイトル 2本 | ⚠️ 検出のみ。**削除・統合は未対応** |
| daily-science 登録者の減少・横ばい（再生→登録の転換率） | ⚠️ **未解決**。登録者が取れなくなったので追跡も止まっている |
| テーマ重複が依然多い（daily-science 15 件・閾値 0.62、類似度 1.0 が 8 ペア） | ⚠️ **未解決**。閾値の厳格化が残タスク |
| 再生 0 の動画の棚卸し（daily-science 21本 + scp-lab 29本） | ⚠️ 未着手 |
| clip-fukada の性的・共演回の取りこぼし | 🔶 区間ゲート（`exclude_text_patterns`）で暫定防御。**無人運用なら公開前の目視ゲートが必要** |

### 1-6. 次にやるべきこと（優先順）

1. **未コミット 216 件をコミットする**（特に未追跡の clip_factory 新規 6 ファイル）
2. **Git リモートを用意して push**（バックアップ皆無の状態を解消）
3. **登録者取得の復旧** — Analytics の views/subscriber 取得が壊れており、PDCA が機能停止している
4. `com.youtube-factory.pdca` の launchd を load（日次レポート生成の常駐が止まっている）
5. Anthropic API キー問題の解消（またはキー非依存の Claude タスク方式へ移行）
6. `daily-science` の OAuth `redirect_uri_mismatch` 解消＋ GCP consent screen を Published に（**ユーザー手動作業**）
7. カスタムサムネイル権限（YouTube 側のアカウント認証）を通す（**ユーザー手動作業**）
8. clip-fukada の公開前目視ゲートを運用に組み込む
9. `akashic-librarian` / `fake-paper` の autopilot 有効化を判断

---

## 2. aiseki

**パス**: `/Users/ayukiyamazaki/Developer/aiseki`
**本番 URL**: **https://aisekimatch.com**（旧: https://aiseki-xi.vercel.app — まだ 200）
**ステータス**: 🟢 **正常** — P0（公開ブロッカー）は全消化。残るのは人手の作業のみ

### 2-1. 開発進捗

- グループ相席マッチング（React 18 + Vite 6 / Supabase / Vercel）。ビジネスロジックは PL/pgSQL + RLS 側
- Supabase プロジェクトを `tvydtsqirogdxglkoicz` → **`melfyxfvhyknqhruytms`** に移管完了（08-20）
- 独自ドメイン `aisekimatch.com` 移行済み（08-22）
- Resend SMTP フル投入 → 実アドレスへの配信 `delivered` を実測（08-22）
- 確認メールの日本語化完了（08-22）
- 広告用 LP `/lp/women` `/lp/men` を本番デプロイ済み（08-22）
- 08-23〜24 で内部評価・アプローチ・飲みスタイルタグ・**評価平均によるランク**・店舗予算帯を追加

### 2-2. 直近の変更（`git log --oneline -5`）

```
d885701 feat: 評価の平均で決まるランクと、店舗の予算帯を追加する
10b73a6 feat: ファビコンとロゴを差し替える（黒地に角丸・ゴールドのA）
985efd4 design(lp): ファーストビューを強くする（光らせずに段差で）
fd3d099 design(lp): LPから「生成物っぽさ」を落として組み直す
efe9980 fix(security): API直叩きで通っていた4件を塞ぐ
```

### 2-3. 未適用マイグレーション・デプロイ状態

- **未適用マイグレーション: なし。** `supabase/migrations/` ディレクトリは無く、`supabase/migration_launch.sql` を手動適用する方式。本番（新 ref）へ **2026-08-20 に適用済み**、重複外部キー2本の削除まで完了
- **Vercel: デプロイ済み・稼働中**（`prj_eXehBy01ZFf7TYhqGI3d2zyvWu8I` / deployment `dpl_G7GC6af9ux669kvvTsSVeXicnYmb`）
  - ⚠️ **GitHub 連携が無いため `git push` では本番に出ない。** 手動 `vercel deploy --prod` が必要
  - ⚠️ リモートビルドが 15分以上詰まる事象あり。`vercel pull → build --prod → deploy --prebuilt --prod` に切り替えると 13 秒で完了

### 2-4. 未マージブランチ・未コミット変更

- ブランチ: `main` のみ（`origin/main` と同期）。未マージ **なし**
- 未コミット **3 件**、いずれも一時ファイル: `.claude/settings.local.json` / `.e2e-rank.mjs` / `.e2e-tmp.mjs` → **削除か .gitignore で片付ければクリーン**

### 2-5. 未解決の課題・ブロッカー

- 🟠 **実機での動作確認が未実施**（チェックリスト `LAUNCH.md` §5）
- 🟠 **サインアップに CAPTCHA が無い** — 登録ボーナス 10,000pt ＋ 紹介 3,800pt を自動登録で量産できる。**決済有効化より先に必須**
- 🟠 通報（`inquiries`）を誰が見るか未決定。管理画面なし＝ Supabase の Table Editor 運用
- 🟠 利用規約第23条の「本店所在地」が未確定
- 🟠 提携店舗の飲食店営業許可・深夜酒類提供の届出確認が未実施
- 🟡 Stripe は placeholder のまま（意図的）
- ⚠️ **Supabase の SMTP 設定が翌日 null に戻った実績あり**（原因未特定）。触ったら必ず GET で実値確認

### 2-6. 次にやるべきこと

1. 一時ファイル 3 件を整理してツリーをクリーンに
2. **実機で動作確認**（LAUNCH.md §5）← **ユーザー手動**
3. **CAPTCHA 導入**（ポイント量産の穴を塞ぐ）
4. 運営体制の確定：通報対応者・本店所在地・提携店舗の許認可確認 ← **ユーザー手動**
5. 決済を開けるときに Stripe 本番キー + Webhook + `PUBLIC_BASE_URL` 差し替え

---

## 3. ai-english-coach

**パス**: `/Users/ayukiyamazaki/Developer/ai-english-coach`
**URL**: **未発行**（Vercel プロジェクト未作成・Git リモート未設定）
**ステータス**: 🟡 **要対応** — コードは Phase 1 完成、**インフラが丸ごと未着手**

### 3-1. 開発進捗

LINE Bot × AI 英会話コーチ（月額 ¥7,000 / 10時間、超過チケット ¥1,200・7日無料トライアル）。

**✅ 実装完了（コード）**
- Phase 1: DB スキーマ、LINE Messaging ユーティリティ、OpenAI コーチ応答（gpt-4o-mini・4ステップ学習ルール）、Webhook（署名検証）、月間利用時間管理、対話コア `lib/coach.ts`
- Phase 1.5（決済・先行実装）: LINE Pay v3 クライアント（Reserve/Confirm/Preapproved/Refund）、モックモード、サブスク加入、Confirm callback、追加チケット購入、月次自動更新 cron、webhook 統合
- ローカル開発支援: `/debug` チャット UI、`/api/debug/chat`、`/mock/line-pay`、`npm run typecheck`

**⛔ 未着手（すべて環境・運用）**
- Vercel プロジェクト未作成（`vercel.json` / `.vercel/` すら無い）
- **Git リモート未設定** — 7 コミットがローカルのみ
- Supabase クラウド未作成、LINE 公式アカウント・Messaging API チャンネル未発行、LINE Pay 加盟店未申込、OpenAI API Key 未発行、Vercel Cron 未登録

### 3-2. 直近の変更（`git log --oneline -5`）

```
a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
6db3262 feat: phase 1 - AI text dialog MVP with Supabase
```

### 3-3. 未コミット変更

**1 件のみ**: `HANDOFF.md`（未追跡）。実質クリーン。未マージブランチなし（`main` のみ、リモート無し）。

### 3-4. 未解決の課題・ブロッカー

- 🔴 **音声機能（Phase 2）が未着手** — 現状はテキスト対話のみ。課金 10時間/月の「時間」課金は音声前提の設計
- 🔴 **LINE Pay 加盟店審査**がリードタイム最長（production は審査あり）← **ユーザー手動**
- 🟠 Git リモートが無くバックアップ皆無

### 3-5. 次にやるべきこと

1. Git リモートを用意して push
2. LINE 公式アカウント作成 → Messaging API チャンネル発行 ← **ユーザー手動**
3. LINE Pay 加盟店申込（sandbox は即時 / production は審査） ← **ユーザー手動**
4. Supabase / Vercel / OpenAI Key を用意して環境変数を投入
5. ngrok で Webhook 疎通確認 → Phase 1 の実地テスト
6. その後に音声課金（Phase 2）へ

---

# 全プロジェクト進捗サマリ

## youtube-factory
- **URL**: https://youtube-factory-eight.vercel.app
- **ステータス**: 🟡 要対応（自動投稿は稼働中 / 分析パイプラインが停止）
- **チャンネル別 登録者・autopilot**（登録者は 2026-08-18 レポートの最終取得値。**08-24 現在は取得失敗中**）

| チャンネル | 登録者 | 総再生 | 本数 | autopilot |
|---|---:|---:|---:|---|
| scp-lab | 133 | 133,388 | 146 | ✅ |
| daily-science | 52 | 168,282 | 177 | ✅ |
| pokemon-lab | 11 | 33,937 | 23 | ✅ |
| yokai-watch | 10 | 31,792 | 22 | ✅ |
| 2ch-matome | 4 | 14,349 | 15 | ✅ |
| company-facts | — | — | — | ✅ |
| clip-lab（切り抜きラボ） | — | — | — | ✅ **08-24 凍結解除** |
| clip-fukada | — | — | 1 | ✅ 08-24 稼働 |
| clip-kaneko | — | — | 0 | ✅ 08-24 稼働 |
| fake-paper | 0 | 1,099 | 1 | ❌ |
| akashic-librarian | — | — | — | ❌ |

- **残タスク**: 未コミット 216 件のコミット / Git リモート用意 / 登録者取得の復旧 / PDCA launchd の load / Anthropic キー問題 / 再生0動画の棚卸し（50本） / テーマ重複閾値の厳格化 / TikTok セットアップ
- **ユーザー手動待ち**: GCP consent screen の Published 化、daily-science の OAuth 再認可、**カスタムサムネイル権限（YouTube アカウント認証）**、OpenAI billing hard limit の解除、SCP 非公開動画 5本の公開判断、clip-fukada の公開前目視チェック

## aiseki
- **URL**: **https://aisekimatch.com**（旧 https://aiseki-xi.vercel.app も 200）
- **ステータス**: 🟢 正常・稼働中。**P0 公開ブロッカーはゼロ**
- **残タスク**: 一時ファイル 3 件の整理 / CAPTCHA 導入 / Stripe 本番キー + Webhook（決済を開けるとき） / プッシュ通知・管理画面・途中離脱（未実装）
- **ユーザー手動待ち**: **実機での動作確認**、通報対応者の決定、利用規約の本店所在地確定、提携店舗の飲食店営業許可・深夜酒類提供届出の確認

## fanup
- **URL**: https://fanup-rouge.vercel.app
- **ステータス**: 🟡 **MVP 完了・集客未着手**。加えて**本番決済が未開通**
- **残タスク**: Stripe 本番 Secret key + Webhook 登録 + Connect Webhook / Resend ドメイン検証 / `CRON_SECRET` 生成 / Vercel 再デプロイ / 決済 E2E テスト / 既存クリエイター3名の手数料 30%→10% 判断 / 未追跡 24 件の整理 / Git リモート用意 / `README最新.md` の削除 / ai-orchestrator の `fanup_growth`（設計のみ・未実装）
- **ユーザー手動待ち**: **Stripe 本番モードの開通**、Resend ドメイン検証、**集客施策そのものが未着手**

## oripa
- **URL**: https://oripa-omega.vercel.app
- **ステータス**: 🟡 **Phase 1 MVP 完了・決済未着手**。**古物商許可待ちで実運用に入れない**
- **残タスク**: `feat/stripe-checkout` → `main` マージ（**唯一の未マージブランチ**） / Supabase 本番プロジェクト作成 + SQL 適用（schema → functions → 0001 → 0002） / Stripe キー + Webhook / 事業者情報 9 変数 / 再デプロイ → パック投入 / Git リモート用意 / 仕入れ自動巡回 Phase 2（設計のみ）
- **ユーザー手動待ち**: **古物商許可の申請（管轄警察署・審査およそ 40 日＝リードタイム最長・最優先）**、古物商番号取得後の事業者情報設定

## ai-english-coach
- **URL**: 未発行
- **ステータス**: 🟡 **Phase 1 テキスト版完了・音声課金未着手**。インフラ全般が未セットアップ
- **残タスク**: 音声対話（Phase 2） / Vercel プロジェクト作成 / Git リモート / Supabase クラウド / Cron 登録 / Webhook 疎通確認
- **ユーザー手動待ち**: **LINE 公式アカウント作成・Messaging API チャンネル発行**、**LINE Pay 加盟店申込（production は審査）**、OpenAI API Key 発行

## 切り抜きラボ（clip-lab）
- **URL**: youtube-factory 内のチャンネル（管理は https://youtube-factory-eight.vercel.app ）
- **ステータス**: 🟢 **凍結解除済み**。2026-08-24 に再開（毎日 17:45 / gen_type=clip）
  - 凍結理由だった「theme_queue 未作成・実績0件」は gen_type=short 向けの判定で、clip 系には当てはまらなかった。凍結前の 08-21〜23 にひろゆき切り抜き 4本を投稿済み
- **残タスク**: 許諾済み在庫の枯渇管理（1日1枠に絞って対応済み） / 実績データの蓄積待ち
- **ユーザー手動待ち**: なし

## rhythm-pop
- **URL**: ローカルのみ（デプロイ先なし）
- **ステータス**: 🟢 **完成済み**
- **残タスク**: **未コミット 19 件（大規模リファクタが未保存）** — 保存しないと消える
- **ユーザー手動待ち**: なし

## claude-codex-bridge
- **URL**: なし（Claude Code スキル本体）
- **ステータス**: 🟢 **完成済み**。作業ツリーほぼクリーン（未追跡 1 件）
- **残タスク**: なし
- **ユーザー手動待ち**: なし

---

## 横断して効いているリスク

1. **Git リモートが無いリポジトリが 4 つ**（youtube-factory / fanup / oripa / ai-english-coach）。ローカルのディスク障害で全部消える
2. **未コミット変更の放置**（youtube-factory 216 / fanup 25 / rhythm-pop 19）。特に youtube-factory の切り抜き基盤 6 ファイルは**未追跡＝ Git 管理外**
3. **審査・許認可のリードタイム**が 2 件（oripa の古物商およそ40日、ai-english-coach の LINE Pay production）。**着手が遅れるほど後ろが全部ずれる**

---

### 注記
- 本レポートは読み取りのみで作成。youtube-factory 以外のリポジトリには一切書き込んでいない
- youtube-factory の登録者数は `data/reports/latest.md`（08-24）で取得失敗のため、`HANDOFF.md` に記録された 2026-08-18 時点の値を併記した
