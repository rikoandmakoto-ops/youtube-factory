# 全プロジェクト引き継ぎレポート — 2026-09-04（夜）

実行: 2026-09-04 23:15 JST / タスク: `daily-project-handoff`
参照した過去文脈: `last_merge_log.md`(09-02) / `MEMORY_UPDATE_20260904.md`(朝) / `MEMORY_UPDATE_20260903_night.md` / 各 `HANDOFF.md`

> ⚠️ `last_handoff_log.md` は**存在しなかった**（本レポートが初回）。差分の基準は
> 09-02 のマージログと 09-04 朝のメモリ更新に置いた。
> ⛔ `~/Documents/Claude/.auto-memory/` は**接続フォルダ外で今夜も読めなかった**（7夜連続）。
> 恒久対応: Cowork の接続フォルダに `~/Documents/Claude/.auto-memory` を追加すること。

---

## エグゼクティブサマリ

| | |
|---|---|
| 🎉 **最大の変化** | 朝の P0「OpenAI 429 で制作が全面停止・本日0本」は**解消**。11:32 以降に復旧し、**09-04 は 21 本に video_id が付与された**（即時公開4 / 予約17）。09-03 の 12 本を上回り、投稿量倍増（15→34枠）の効果が実測で出た初日 |
| 🚨 **今夜の最重要** | **サムネイルが全公開本で設定されていない**。`thumbnails/set` が HTTP 403（*The authenticated user doesn't have permissions to upload and set custom video thumbnails*）で **109 回失敗**。動画は公開されているがサムネはYouTube自動生成のまま。→ **チャンネルの電話番号確認が必要（ユーザー手動）** |
| 📉 未解決の継続 | `ANTHROPIC_API_KEY` 未設定 / clip-fukada・clip-animal の素材枯渇 / GCP 同意画面の本番公開（**09-09 前後に OAuth 再失効の見込み**）/ Reddit RSS 429 |
| ✅ 解消済み | youtube-factory の未コミット 647→82 件・未プッシュ 9→0 コミット / aiseki の未コミット 24→0 件 |

---

## 1. youtube-factory

**ステータス: 🟡 稼働中（動画は出ているが、サムネが全滅）**
URL: https://youtube-factory-eight.vercel.app

### 直近の変更（git log --oneline -5）

```
a08c70d feat: 画像は 1ch=1スレッド固定にし、OpenAI Images API を削除する   (09-04 19:59)
9b03b40 feat: 画像生成を OpenAI API から ChatGPT のブラウザスレッドへ移す   (09-04 17:00)
284df19 data: 09-03 の実行結果と HANDOFF を記録する                        (09-04 10:23)
3a0dba4 config: 投稿量を倍増し、機械ゲートと判断軸を全チャンネルへ反映する
009d695 feat: タイトル・テーマ・演出の施策を自然文から機械ゲートへ移す
```

- ブランチ: `main` のみ。**未マージブランチなし**、コンフリクトなし
- **未コミット 82 件**（朝は 647 件）。内訳は `data/` 配下の当日生成物・シナリオ 41 件と分析 JSON。実害なし
- **未プッシュ 0 コミット**（朝は origin/main より 9 先行）。`origin/main` と同期済み

### 本日の制作実績（`video_publish.db`）

| 時刻 | ch | 状態 | video_id |
|---|---|---|---|
| 11:32 | yokai-watch | 予約 | jBrtIbNN5NM |
| 11:37 | 2ch-matome | 予約 | CPhxUakX8mw |
| 11:48 | clip-lab | **公開** | -UiTA3tALd8 |
| 11:51 | daily-science | 予約 | 6lcWup40vok |
| 12:26 | scp-lab | 予約 | 1_OFbz4Xqzk |
| 12:49 | company-facts | 予約 | iTLPgjOJAYE |
| 13:47 | akashic-librarian | 予約 | PuHKm7UzClk |
| 14:00 | clip-kaneko | **公開** | zFzveWT2A8c |
| 14:22 | pokemon-lab | 予約 | saslFdGKLOg |
| 14:52 | fake-paper | 予約 | k8LdSuv7Drk |
| 15:24 | yokai-watch | 予約 | 0F8nNs8IFFQ |
| 16:26 | daily-science | 予約 | SzMbnxjh0hM |
| 16:27 | company-facts | 予約 | kv1KNLaPkWA |
| 17:11 | pokemon-lab | 予約 | FlhD3y4SXSU |
| 17:46 | clip-lab | **公開** | U0W0HjIPXsg |
| 17:50 | 2ch-matome | 予約 | DARoakZbgGk |
| 18:03 | akashic-librarian | 予約 | XgKZ5b4XDww |
| 18:23 | scp-lab | 予約 | rMCy64I45Zs |
| 18:24 | yokai-watch | 予約 | _0xgJRshAgQ |
| 18:52 | fake-paper | 予約 | HYZOis-0Ry0 |
| 20:30 | clip-kaneko | **公開** | dxph90B2w4o |

**合計 21 本**（台本系8ch 16本 / 切り抜き 5本）。失敗は 3 枠のみ（下記）。

### チャンネル別 登録者効率（30日 / 判断軸 = 登録者/1000再生）

| ch | 登録/千再生 | 獲得登録 | 再生 | autopilot |
|---|---|---|---|---|
| akashic-librarian | **0.83** | 3 | 5,402 | ✅ |
| company-facts | **0.70** | 27 | 41,767 | ✅ |
| scp-lab | 0.53 | 17 | 35,142 | ✅ |
| daily-science | 0.49 | 15 | 33,151 | ✅ |
| pokemon-lab | 0.26 | 8 | 33,868 | ✅ |
| 2ch-matome | 0.17 | 6 | 37,579 | ✅ |
| fake-paper | **0.00** | 0 | 7,584 | ✅ |
| clip-lab（切り抜きラボ） | **0.00** | 0 | **31,946** | ✅ |
| clip-kaneko | 0.00 | 0 | 2,058 | ✅ |
| clip-animal | 0.00 | 0 | 17 | ✅ |
| clip-fukada | — | 0 | 0 | ✅ |
| yokai-watch | （PDCA 実行中で未出力） | | | ✅ |
| socio-rx | — | — | — | ❌ 無効（凍結） |

> **clip-lab は 31,946 再生で登録 0**。再生量では全13ch中2位なのに転換ゼロという構造は 09-03 から変わっていない。
> 一方 **company-facts は 27 登録で最多**。個社名×年収実額×「正体／裏側」の勝ち筋が効いている。

### 検出した課題

| # | 内容 | 状態 |
|---|---|---|
| 1 | 🚨 **サムネイル設定が全公開本で HTTP 403**（*doesn't have permissions to upload and set custom video thumbnails*）。今日だけで **109 回**失敗。8月の引き継ぎ書にも記載があり**新規ではないが、投稿量を34枠に増やしたため全公開本に波及**した。原因はチャンネルの**電話番号未確認**（YouTube はカスタムサムネに本人確認を要求する） | ❌ 未解決・**要ユーザー手動** |
| 2 | ❌ **`ANTHROPIC_API_KEY` 未設定**（`backend/.env` 18行目でコメントアウトのまま）。今夜も **clip-lab 20:45 枠が「viral エンジンが失敗: ANTHROPIC_API_KEY 未設定」で中止**。`success_patterns.gpt_insights` も全ch null のまま | ❌ 未解決（継続） |
| 3 | ❌ **clip-fukada は素材が実質ゼロ**。12:45 / 20:00 枠とも「切り抜ける元動画が見つかりません」。加えて `⚠️ チャンネルが見つかりません: UCRUdyowhXEQhoNT7uNEvGJA` — **参照先チャンネルIDが無効**の可能性 | ❌ 未解決（継続）／ ID無効は **NEW** |
| 4 | ❌ **clip-animal は 18:00 枠が「全ての元動画が切り抜き済み」**。`clips_per_video: 1` なので素材1本で即枯渇（09-03 に指摘済みの構造がそのまま） | ❌ 未解決（継続） |
| 5 | 🆕 **ChatGPT 画像ブリッジのスレッドURLが 13ch すべて未登録**（`data/image_requests/threads.json` が `{}`、pending/cache も空）。夕方の大改修で画像生成はブリッジ経由になったが、登録がゼロなので**実質 Pillow フォールバックだけで動いている** | **NEW**・要ユーザー手動 |
| 6 | ⚠️ `channel_metrics` が **2026-09-01 止まり**（3日欠測）。朝は 08-31 止まりだったので1日分は進んだが、日次の登録増減はまだ追えない。`video_metrics` は 09-04 まで取得済み | 部分改善・未解決 |
| 7 | ⚠️ **Reddit RSS が 429**（`r/HolUp` `r/funny` `r/WatchPeopleDieInside` `r/therewasanattempt` `r/instant_regret`）。`REDDIT_CLIENT_ID` 未設定のため匿名RSSに依存 | ❌ 未解決（継続） |
| 8 | ⚠️ **GCP OAuth 同意画面が「テスト中」のまま**。リフレッシュトークンは7日で失効し 08-24 / 08-31 / 09-02 と3回再発。**次は 09-09 前後** | ❌ 未着手・**要ユーザー手動** |
| 9 | ✅ **OpenAI 429（朝の P0）は解消**。`api_usage.jsonl` は 23:11 まで正常記録。手動トリガーは不要だった（朝の判断どおり） | **解決済み** |
| 10 | ✅ **OpenAI Images API の呼び出しは実際に止まった**。ログ上の最終呼び出しは 17:00 頃で、19:59 の削除コミット以降の枠（18:00〜20:45）では発生していない | **解決済み** |

### 次にやるべきこと

1. **13ch の電話番号確認**（https://www.youtube.com/verify）。これが通るまで、毎日 20 本以上がサムネ無しで出続ける。**費用対効果が最も高い**
2. **GCP 同意画面の本番公開**（project 844705815004）。09-09 前後の再失効を待たずに
3. `ANTHROPIC_API_KEY` を `backend/.env` に投入 → clip-lab 海外枠と gpt_insights が同時に復旧
4. `scripts/image_bridge.py thread set <ch> <URL>` を 13ch 分実行
5. clip-fukada の素材投入 と `UCRUdyowhXEQhoNT7uNEvGJA` の有効性確認 / clip-animal の `clips_per_video` 引き上げ
6. **📅 09-11: `cta_position` A/B の判定日**。yokai 0.23 / pokemon 0.23 / 2ch 0.17 を上回らなければ `after_hook` へ戻す

---

## 2. aiseki

**ステータス: 🟢 正常（技術的ブロッカーなし・公開待ち）**
URL: https://aisekimatch.com

### 直近の変更

```
af5f442 広告用LPに料金比較・FAQ・構造化データを足す
e37c670 招待・DM・電話番号まわりの e2e 検証スクリプトを追加する
0ea61b3 一時デバッグスクリプトと xlsx 資料を .gitignore に足す
cd61e3e DMの自動送信を足す（管理画面からジョブを積み、手元のワーカーが送る）
f02b80c Serverless Function を15個から5個に減らす（Hobby の上限12個対策）
```

- ブランチ: `main` のみ。**未マージブランチなし**
- **未コミット 0 件**（前回マージログの 24 件は `0ea61b3` の .gitignore 追加で解消済み）
- ⚠️ **origin/main より 1 コミット先行（未プッシュ）** — `af5f442`

### 前回からの差分

| 項目 | 09-02 | 今回 |
|---|---|---|
| 未コミット | 24 件 | **0 件**（解決） |
| 未プッシュ | 3 コミット | 1 コミット（減） |

### 検出した課題

- ⚠️ **最新コミット `af5f442`（広告用LP）が本番へ反映済みか未確認**。コードを変えたら `vercel deploy --prod` が必要とHANDOFFに明記。未プッシュ1件と合わせて要確認
- ⛔ **Twilio がトライアルアカウントのまま**。SMS 認証は実装済みだが、**公開前にアップグレードが必須**（ユーザー手動）
- ⛔ **DM 自動送信（`worker/dm_worker.mjs`）は Meta Platform Terms に反する**。運営判断で導入済みだが、アカウント停止リスクは残る。ペースの歯止めと停止条件を緩めないこと
- ⚠️ **サインアップ自体の CAPTCHA が未導入**。紹介ボーナス 3,800pt はサインアップだけで付くため、**アカウント量産は止まっていない**（カード登録側は Turnstile 導入済み）
- ℹ️ マイグレーションは `supabase/migration_*.sql` の平置きで順序管理がなく、**未適用かどうかはローカルからは判定できない**（Supabase 側の確認が必要）
- P1 の残タスク（人手）: 実機動作確認 / 通報の受け先の運用決め / 利用規約 第23条の本店所在地 / 提携店舗の許認可確認

### 次にやるべきこと

1. `git push` して `vercel deploy --prod` の状態を確認（広告LPが本番に出ているか）
2. Twilio を本番アップグレード
3. 実機チェックリスト（`LAUNCH.md` §5）を通す

---

## 3. ai-english-coach

**ステータス: 🔵 凍結（コードは進んでいるが、公開導線が未着手）**
URL: なし（未デプロイ）

### 直近の変更

```
a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加
d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
6db3262 feat: phase 1 - AI text dialog MVP with Supabase
```

- ブランチ: `main` のみ。**リモート未設定**（`git remote -v` が空 = バックアップが存在しない）
- **未コミット 2 件**: `HANDOFF.md`（未追跡）/ `.__perm_test`

### 前回からの差分

前回 1 件 → 今回 2 件。`.__perm_test` が増えただけで実質変化なし。**HANDOFF.md が 09-02 から未コミットのまま放置**されている。

### 検出した課題

- ❌ **Git リモート未設定** — ローカルにしか存在しない。最優先で GitHub へ push すべき
- ❌ Vercel プロジェクト未作成 / 本番URL未発行 / Supabase クラウド未作成
- ❌ LINE 公式アカウント・Messaging API チャンネル未作成 / LINE Pay 加盟店 未申込
- ❌ 月次課金 Cron のスケジューラ登録が未実施（ルートは実装済み）
- ℹ️ HANDOFF.md の日付が 2026-08-20 のままで、その後の 4 コミット分が反映されていない

### 次にやるべきこと

1. `HANDOFF.md` をコミット + **GitHub リモートを作成して push**（消失リスクの解消）
2. Phase 1（テキスト版）を Vercel へデプロイして実機で触れる状態にする
3. 音声課金は Phase 2。LINE Pay 加盟店申込がクリティカルパス

---

## 4. 全進捗サマリ

| プロジェクト | URL | ステータス | 直近の動き / 次の一手 |
|---|---|---|---|
| **youtube-factory** | https://youtube-factory-eight.vercel.app | 🟡 稼働中・要対応 | 09-04 に 21 本投稿（過去最多）。**全本サムネ未設定（403）**。→ 電話番号確認 |
| **aiseki** | https://aisekimatch.com | 🟢 正常・公開待ち | 広告LP追加（未プッシュ1）。P0 完了済み。→ Twilio 本番化 + 実機確認 |
| **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | 最新 `2681dfd`（Stripe クライアント遅延生成でビルド修復）。未コミット 25 件（ドキュメント・画像）。→ 集客導線とクリエイター手数料 0.30→0.10 の可否決定 |
| **oripa** | https://oripa-omega.vercel.app | 🟡 Phase 1 MVP・決済未着手 | ブランチ `feat/stripe-checkout`（**main へ未マージ**）。最新は経営計画書の追加。→ Stripe Checkout の完了とマージ |
| **ai-english-coach** | なし（未デプロイ） | 🔵 凍結 | Phase 1 テキスト版＋LINE Pay 基盤は実装済み。**リモート未設定**。→ push とデプロイ |
| **切り抜きラボ (clip-lab)** | youtube-factory 内のch | 🟡 稼働・転換ゼロ | 09-04 に 2 本公開。30日で **31,946 再生・登録 0**。海外枠は ANTHROPIC_API_KEY 待ち |
| **rhythm-pop** | — | ✅ 完成済み | 最新 `1cfde97`。未コミット 19 件。動きなし |
| **claude-codex-bridge** | — | ✅ 完成済み | 単一コミット `eb23d8a`。未コミット 1 件。動きなし |
| *(参考)* ai-orchestrator | — | ✅ 稼働 | `052a617` プロンプトキャッシング追加。未コミット 1 件 |

---

## 5. ユーザーの手動対応が必要なタスク（優先度順）

| # | 内容 | プロジェクト | 影響 |
|---|---|---|---|
| 1 | **YouTube 13ch の電話番号確認**（youtube.com/verify） | youtube-factory | 毎日20本以上がサムネ無しで公開され続ける |
| 2 | **GCP OAuth 同意画面を本番公開**（project 844705815004） | youtube-factory | **09-09 前後に4回目の全ch失効**の見込み |
| 3 | `ANTHROPIC_API_KEY` を `backend/.env` に設定 | youtube-factory | clip-lab 海外枠が毎日失敗 / 分析の質が落ちている |
| 4 | ChatGPT スレッドURL を 13ch 分登録 | youtube-factory | 画像ブリッジが動かず Pillow のみ |
| 5 | clip-fukada の素材投入・`UCRUdyowhXEQhoNT7uNEvGJA` の確認 | youtube-factory | 切り抜き4chで最も深刻（累計0本） |
| 6 | **Twilio を本番アップグレード** | aiseki | SMS認証が本番で機能しない＝公開不可 |
| 7 | `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加 | 共通 | **7夜連続でメモリに書けていない** |
| 8 | `REDDIT_CLIENT_ID` の設定 | youtube-factory | 切り抜きの素材探索が 429 で失敗 |
| 9 | ai-english-coach の GitHub リモート作成 | ai-english-coach | ローカルのみ＝消失リスク |

---

## 6. 判断の記録（本レポートで意図的にやらなかったこと）

- **他プロジェクトへの書き込みは一切していない**（読み取りのみ）。書き出しは youtube-factory 内の2ファイルのみ
- **git push / merge / commit は実行していない**（本タスクの範囲外）
- サムネ 403 は 8月の引き継ぎ書にも記載があるため「NEW」ではなく「継続・影響拡大」として扱った
- 朝のメモリで「解決済み」とされた OAuth 誤診・`#shorts` タイトル不具合・テーマキューの負けパターンは、**要対応として再掲していない**
