# 全プロジェクト引き継ぎレポート — 2026-09-05（土）

**実行**: 2026-09-05 23:15 JST / `daily-project-handoff`
**前回**: `last_handoff_log.md`（09-04 23:15）
**参照した文脈**: 前回ハンドオフログ、`last_merge_log.md`(09-02)、`MEMORY_UPDATE_20260905.md`（09-05 朝の指揮者実行）

> ⚠️ **`~/Documents/Claude/.auto-memory/` は今回も接続フォルダ外で読めなかった（9日連続）。**
> youtube-factory 内の `MEMORY_UPDATE_*.md` と `HANDOFF.md` をメモリ本体として代用した。
>
> ℹ️ **本レポート作成中（23:00〜）に別タスク（PDCA/指揮者）が並走していた。**
> `data/reports/2026-09-05/*.json` は 23:02〜23:12 に書き込み進行中で、
> アルファベット順で `daily-science` まで到達済み。`pokemon-lab` 以降は未生成。
> 後述の scp-lab の指摘（§1-4）はこの未完了が原因。

---

## 0. 前回（09-04）からの変化 — 3行サマリ

1. **前回の「未解決」11件のうち 4件が解決した。** 投稿枠の未反映、サムネA/Bのベースライン破損、clip-fukada の素材ゼロ、「正体」ルールの暴走。
2. **最大の課題は変わらずサムネイル403。** 09-05 も全公開本で失敗し続けている。本人確認が唯一の解。
3. **新たに 2件。** analytics 取得の破損が拡大（7→15行）、`success_patterns.json` の scp-lab だけクランプ未適用。

---

## 1. youtube-factory

**ステータス: 🟡 稼働中・要対応**（前回と同じ。ただし内訳は改善）

`/Users/ayukiyamazaki/Developer/youtube-factory` — https://youtube-factory-eight.vercel.app

### 1-1. 直近の変更

```
e4eef9f fix: 指揮者(09-05)の指摘7件を反映する          ← 09-05 13:17
a08c70d feat: 画像は 1ch=1スレッド固定にし、OpenAI Images API を削除する
9b03b40 feat: 画像生成を OpenAI API から ChatGPT のブラウザスレッドへ移す
284df19 data: 09-03 の実行結果と HANDOFF を記録する
3a0dba4 config: 投稿量を倍増し、機械ゲートと判断軸を全チャンネルへ反映する
```

- ブランチ: `main` のみ。**未マージブランチなし**（`origin/main` / `neworigin/main` とも先行差分ゼロ）
- **未プッシュコミット: 0**（前回 0 を維持）
- **未コミット変更: 147件**（変更48 / 未追跡99）。前回82件から増加。中身は `data/` 配下の自動生成物（analytics・channels・originality・reports）で、**運用上の問題ではない**

### 1-2. 09-05 の投稿状況 — 29本（前日25本から +4）

| チャンネル | 本数 | 状態 |
|---|---|---|
| scp-lab | 4 | 予約公開 |
| akashic-librarian / yokai-watch / fake-paper / clip-kaneko | 各3 | 予約 or 公開 |
| 2ch-matome / company-facts / daily-science / pokemon-lab / clip-fukada / clip-lab | 各2 | 予約 or 公開 |
| clip-animal | 1 | 公開 |

内訳は **公開8 / 予約21**。autopilot は全チャンネルで正常発火し、**制作起因の失敗は clip-lab の 20:45 枠 1件のみ**。

### 1-3. ✅ 前回から解決した項目（次回「要対応」として報告しないこと）

| 前回# | 内容 | 確認方法 |
|---|---|---|
| — | **投稿枠3件の未反映**（2ch 21:00 / scp 17:00 / yokai 17:45） | バックエンドが 09-05 11:15〜12:45 の間に再起動済み。`Started server process [6885]`。ログで `2ch-matome [slot 2] 21:00 JST` の登録と、20:15 の発火（21:00公開）を確認。**`apply_orchestrator_20260905.command` は実行済みと判断** |
| 5-1 | **サムネA/B の `channel_avg_ctr` 破損**（42.9 等の異常値） | 現在 19件すべて **0.0145〜0.0337** に収まっている。1以上の値はゼロ件 |
| 3 | **clip-fukada 素材ゼロ + `UCRUdyowhXEQhoNT7uNEvGJA` 無効** | 09-05 は 12:45 と 20:00 の両枠で公開成功。当該警告の**最終出現は 09-04 20:00** で本日は発生なし |
| 6-1 | **「正体」ルールの暴走** | 公開タイトルの「正体」出現率 **09-03 5/12 → 09-04 4/25 → 09-05 0/29**。cross-ch キーワードブロックが `「正体」は本日すでに2本` として実際に弾いている |
| 4 | clip-animal「全ての元動画が切り抜き済み」 | 09-05 に1本公開。**部分解決**（枠は2つあるので1枠は依然埋まっていない） |

### 1-4. ❌ 未解決の課題

| # | 内容 | 種別 | 実測 |
|---|---|---|---|
| 1 | **サムネイル `thumbnails/set` が HTTP 403**。`The authenticated user doesn't have permissions to upload and set custom video thumbnails` | 継続（**最優先**） | ログ内 349件。09-05 も 2ch-matome / scp-lab / pokemon-lab / yokai-watch / fake-paper の全公開本で失敗 |
| 2 | **`ANTHROPIC_API_KEY` 未設定** — `backend/.env` 18行目がコメントアウトのまま | 継続 | clip-lab 20:45 の viral 枠が3回試行して失敗。**5夜連続** |
| 3 | **analytics 取得の破損が拡大**（`views=0` かつ `impressions>0`） | 継続・**悪化** | 09-01: 1 → 09-03: 5 → 09-04: 7 → **09-05: 15行** |
| 4 | **`success_patterns.json` の scp-lab だけ `avg_view_percentage` が未クランプ**（337.05） | **NEW** | 他11chは全て 0-100 に収まっている。`success_analyzer.py` の `_ret()` は正しく動作しており、**scp-lab のブロックが並走中の PDCA でまだ再生成されていないだけ**（§冒頭の注記）。次回実行時に自然解消しているはず。していなければコード側を疑う |
| 5 | **`channel_metrics` が 2026-09-02 止まり**（3日欠測） | 継続 | 前回の 09-01 から1日だけ前進。`video_metrics` は 09-05 分 243行を取得できているので、**`channel_metrics` の取得経路だけが詰まっている** |
| 6 | **ChatGPT画像ブリッジのスレッドURL未登録** — `data/image_requests/threads.json` が `{}` | 継続 | 13ch すべて未登録 |
| 7 | **Reddit RSS 429**（r/HolUp, r/funny, r/WatchPeopleDieInside, r/therewasanattempt, r/instant_regret）。`REDDIT_CLIENT_ID` が `.env` に存在しない | 継続 | — |
| 8 | **GCP OAuth 同意画面が「テスト中」** | 継続・**期限接近** | リフレッシュトークンの次の失効が **09-09 前後**。あと4日 |
| 9 | **サムネA/B が19件すべて `monitoring` のまま、切替ゼロ** | 継続 | ベースラインは直ったが、まだ1件も切替判定に至っていない。09-08 頃に再確認 |
| 10 | **clip-lab の転換ゼロ** | 継続・**悪化** | 直近30日で **34,743再生・登録者0人**（前回 31,946再生・0人）。再生は伸びているのに登録が1人も付かない |

### 1-5. 次にやるべきこと

1. **サムネ403の解消**（ユーザー手動 / 最優先）— 解消するまで毎日30本前後がサムネ無しで出続ける
2. **09-09 までに OAuth 同意画面を本番公開**（ユーザー手動 / 期限あり）
3. `channel_metrics` の取得経路を調査 — `video_metrics` は動いているので原因は限定できるはず
4. **09-12**: 尺の対照実験の評価日（実験群 scp-lab / 2ch-matome を対照群3chと比較）。**それまで daily-science / pokemon-lab / yokai-watch の尺に触れないこと**
5. **09-19**: yokai-watch を 19時→17:45 に移した影響で再生数が落ちていないかの確認（19時は ch内で平均再生が最高の枠だった）
6. clip-lab の転換ゼロ — 34,743再生を1人も登録に変えられていないので、CTA か切り抜き元の選定を見直す

---

## 2. aiseki

**ステータス: 🟢 正常・公開待ち**（前回と同じ）

`/Users/ayukiyamazaki/Developer/aiseki` — https://aisekimatch.com

### 2-1. 直近の変更

```
af5f442 広告用LPに料金比較・FAQ・構造化データを足す        ← 09-03 11:08
e37c670 招待・DM・電話番号まわりの e2e 検証スクリプトを追加する
0ea61b3 一時デバッグスクリプトと xlsx 資料を .gitignore に足す
cd61e3e DMの自動送信を足す（管理画面からジョブを積み、手元のワーカーが送る）
f02b80c Serverless Function を15個から5個に減らす（Hobbyの上限12個対策）
```

- ブランチ: `main` のみ。**未マージブランチなし**
- **未プッシュコミット: 1**（`af5f442`）
- **未コミット変更: 5件** — すべて未追跡。09-05 12:34〜12:38 に作られた**集客用ドキュメント**（`dm_templates.md` / `influencer_outreach.md` / `sns_profile_guide.md`）と LibreOffice のロックファイル2件

### 2-2. 前回からの差分

- **NEW（進捗）**: 09-05 昼に SNS集客の準備物が一式追加された（DMテンプレ・インフルエンサー開拓リスト・プロフィール設計・`sns_content_calendar.xlsx` / `revenue_simulation.xlsx`）。**開発から集客フェーズに移りつつある**
- **確認済み**: 本番 https://aisekimatch.com は**稼働中**。メタタグ（OGP・構造化データ・料金比較まわりの description）が揃っており、`af5f442` の内容が**本番に反映されている**
- マイグレーション: `supabase/migration_*.sql` は 09-03 以降の新規追加なし。**未適用マイグレーションの懸念は無い**
- ロックファイル2件（`.~lock.*.xlsx#`）は LibreOffice が開いたままか異常終了の残骸。**`.gitignore` に追加推奨**

### 2-3. 次にやるべきこと

1. **Twilio を本番アップグレード**（ユーザー手動 / 公開前の必須条件）
2. `af5f442` を push
3. サインアップの CAPTCHA 未導入 / DM自動送信の規約リスク — 公開前に判断が要る（前回から変化なし）
4. `.~lock.*.xlsx#` を `.gitignore` へ

---

## 3. ai-english-coach

**ステータス: 🔵 凍結**（前回と同じ）

`/Users/ayukiyamazaki/Developer/ai-english-coach`

### 3-1. 直近の変更

```
a90c4ad docs: 決済・ローカル開発手順を反映し typecheck スクリプトを追加   ← 08-18 22:14
d1af467 feat(debug): LINE 不要でローカル検証できる debug / mock 画面を追加
99dc4cf refactor(coach): 対話処理を lib/coach.ts に抽出し課金チェックを統合
eec4752 feat(billing): LINE Pay v3 サブスク・チケット決済基盤を追加
6db3262 feat: phase 1 - AI text dialog MVP with Supabase
```

- **最終コミットは 08-18。18日間動きなし**
- ブランチ: `main` と `_locktest`。`_locktest` は作業用と思われる
- **未コミット変更: 2件**（`HANDOFF.md`、`.__perm_test`）
- **Git リモート未設定**（`git remote -v` が空）。ローカルにしか存在しない

### 3-2. 前回からの差分

変化なし。**リモート未設定によるコード消失リスクだけが継続している。**

### 3-3. 次にやるべきこと

1. **GitHub にリモートを作って push**（消失リスクの解消。凍結中でもこれだけはやる価値がある）
2. Phase 2（音声課金）は着手判断待ち

---

## 4. 全進捗サマリ

| プロジェクト | URL | ステータス | 内容 |
|---|---|---|---|
| **youtube-factory** | https://youtube-factory-eight.vercel.app | 🟡 稼働中・要対応 | 13ch（12ch稼働 / socio-rx は `enabled=false`）。09-05 は29本投稿。サムネ403が最大の障害 |
| **aiseki** | https://aisekimatch.com | 🟢 正常・公開待ち | 本番稼働中。技術タスクは完了。残るは Twilio 本番化と実機確認（人手）。集客準備物が09-05に追加 |
| **fanup** | https://fanup-rouge.vercel.app | 🟡 MVP完了・集客未着手 | `2681dfd`（08-31）から動きなし。未コミット25件・未プッシュ0 |
| **oripa** | https://oripa-omega.vercel.app | 🟡 Phase 1 MVP・決済未着手 | `feat/stripe-checkout` が **main へ未マージ**。**未プッシュ9コミット**。最終コミット 08-11。未コミット1件 |
| **ai-english-coach** | （未デプロイ） | 🔵 凍結 | Phase 1 テキスト版完了。Git リモート未設定 |
| **切り抜きラボ（clip-lab）** | YouTube `UCbWZ5quEFE2VpHPh5TGyPCw` | 🟡 稼働・**転換ゼロ** | 30日で 34,743再生・**登録者0**。20:45枠は API キー未設定で失敗継続 |
| **rhythm-pop** | （ローカル） | ✅ 完成済み | 最終コミット 06-22。未コミット19件・未プッシュ3。リモート未設定 |
| **claude-codex-bridge** | （ローカル） | ✅ 完成済み | 最終コミット 07-04。未コミット1件・未プッシュ3。リモート未設定 |

### YouTube 13ch の autopilot 状態と直近30日の登録効率

| ch | autopilot | 投稿枠 | 30日 再生 | 30日 登録 | sub/1k |
|---|---|---|---|---|---|
| company-facts | ✅ | 08:15 / 13:30 / 17:00 | 44,273 | 27 | **0.703** |
| clip-lab | ✅ | 11:45 / 17:45 / 20:45(viral) | 34,743 | **0** | **0.000** |
| pokemon-lab | ✅ | 08:30 / 15:00 / 17:30 | 34,552 | 8 | 0.270 |
| daily-science | ✅ | 07:30 / 12:30 / 17:00 | 31,937 | 14 | 0.508 |
| 2ch-matome | ✅ | 07:00 / 12:15 / **21:00** | 39,658 | 6 | 0.173 |
| fake-paper | ✅ | 11:00 / 15:30 / 19:30 | 10,831 | 0 | 0.000 |
| akashic-librarian | ✅ | 10:00 / 14:30 / 18:45 | 6,235 | 3 | 0.630 |
| clip-kaneko | ✅ | 08:00 / 14:00 / 20:30 | 5,201 | 1 | 1.016 |
| clip-fukada | ✅ | 12:45 / 20:00 | 544 | 0 | 0.000 |
| clip-animal | ✅ | 09:30 / 18:00 | 22 | 0 | 0.000 |
| scp-lab | ✅ | **17:00** / 13:00 / 19:00 | （集計未完） | — | — |
| yokai-watch | ✅ | 12:00 / 16:00 / **17:45** | （集計未完） | — | — |
| socio-rx | ⛔ 無効 | 20:00(平日) / 15:00(週末) | — | — | — |

> **太字は 09-05 に変更した枠。** scp-lab / yokai-watch の30日集計は並走中の PDCA が未到達のため空欄。
> ⚠️ 数字は `pdca-report` の30日集計。`MEMORY_UPDATE_20260905.md` §0 の通り、
> **量的指標は累積カウンタなので、この表を過去レポートの数値と直接比較しないこと。**

---

## 5. ユーザー手動待ちタスク（優先度順）

| # | 内容 | 期限 | 前回から |
|---|---|---|---|
| 1 | **YouTube 13ch の電話番号確認**（youtube.com/verify）→ サムネ403の唯一の解 | なし（毎日30本が影響） | 継続 |
| 2 | **GCP OAuth 同意画面を本番公開**（project 844705815004） | **09-09 前後** | 継続・期限接近 |
| 3 | **`ANTHROPIC_API_KEY` を `backend/.env` に設定**（18行目のコメント解除） | — | 継続（5夜連続） |
| 4 | **Twilio を本番アップグレード**（aiseki 公開前の必須条件） | aiseki 公開時 | 継続 |
| 5 | ChatGPT スレッドURL を 13ch 分登録（`scripts/image_bridge.py thread set`） | — | 継続 |
| 6 | `~/Documents/Claude/.auto-memory` を Cowork の接続フォルダに追加 | — | 継続（**9日連続**） |
| 7 | `REDDIT_CLIENT_ID` を設定 | — | 継続 |
| 8 | ai-english-coach の GitHub リモート作成と push | — | 継続 |
| 9 | oripa の `feat/stripe-checkout` を main へマージするか判断（9コミット未プッシュ） | — | 継続 |
| ~~10~~ | ~~clip-fukada の素材投入 / チャンネルID確認~~ | — | ✅ **解決** |

---

## 6. 次回（09-06）の実行時に確認すること

1. **サムネ403が解消したか** — 解消していれば「解決済み」へ移す
2. `success_patterns.json` の scp-lab が 0-100 にクランプされているか（PDCA完走後）
3. `channel_metrics` が 09-02 から前進したか
4. analytics 取得の破損（`views=0` かつ `impressions>0`）が 15行から増えていないか
5. **09-09 前後**: OAuth リフレッシュトークンの失効
6. **09-11**: `cta_position` A/B の判定日
7. **09-12**: 尺の対照実験の評価日
8. サムネA/B が `monitoring` から動いたか（19件）

---

## 7. 本タスクで行った書き込み

- `data/reports/project_handoff_2026-09-05.md`（本ファイル・新規）
- `data/reports/last_handoff_log.md`（上書き）

**他プロジェクト（aiseki / ai-english-coach / fanup / oripa / rhythm-pop / claude-codex-bridge）は読み取りのみ。**
git 操作（commit / push / merge）、設定変更、MCP の書き込み系操作は一切実行していない。
