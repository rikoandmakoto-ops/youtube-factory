# 全プロジェクト 引き継ぎレポート — 2026-09-20

**実行日時**: 2026-09-20 23:10〜23:20 JST / **git 系の数値は 23:10 時点**
**前回**: 2026-09-19 23:20
**参照した過去文脈**: `last_handoff_log.md`(09-19 23:21)、`last_merge_log.md`(**09-19 22:08 のまま＝本日更新されていない**)、`.auto-memory/`（09-10〜09-19・`INDEX.md`・`projects/`）、`MEMORY_UPDATE_20260920.md`（本日朝の指揮者）

> ✅ **6夜連続で「最優先・期限あり」と書いてきた OAuth が解決した。** ザキ様が同意画面を本番公開し、稼働6ch＋pokemon-lab の計7ch が**無期限トークン**で再発行された。
> ✅ **指揮者の唯一の依頼だった pokemon-lab の再認可も完了。** ただし **autopilot は OFF のまま**なので、まだ1本も出ない。
> 🆕 **リーチ天井（前回 N3）の原因がエンドカードに特定され、本日 A/B が走り出した。** 判定 **09-27**。それまで5chの `short_endcard` を触ってはいけない。
> 🔴 **scp-lab のキューが 0 件。socio-rx は通過 0 件が3日連続。**

---

## 1. 各プロジェクトのステータス

| プロジェクト | ステータス | 一行サマリ |
|---|---|---|
| youtube-factory | 🟡 **要対応（期限なし）** | **公開14本**（枠15・**失効の瞬間に scp-lab 1枠を落とした**）。✅ **OAuth 解決・7ch 無期限化**。🆕 **エンドカードA/B 開始（判定09-27）**。🔴 **scp-lab キュー0件**。コミット2件・dirty 71・未マージ0 |
| aiseki | 🟡 **本日は停止** | 🆕 **09-20 のコミット 0 件**（前日まで2日連続で6件・1件）。dirty 0・neworigin と同期。aisekimatch.com 正常 |
| ai-english-coach | 🔵 凍結 | 最終コミット 09-08＝**12日**。dirty 0。**リモート未設定＝バックアップ無し** |
| fanup | 🟡 MVP完了・集客未着手 | 08-31 から**20日**。未追跡25件。サイト正常（サポーター1,248・進行中3件はシード値） |
| oripa | 🟡 Phase1 MVP・決済未着手 | 08-11 から**40日**。HEAD は `feat/stripe-checkout`（未マージ）。**サイト本文が空（8日連続）** |
| 切り抜きラボ(clip 4ch) | 🔴 全停止 | autopilot 全OFF・**OAuth も再認可されなかった**（本番公開の恩恵を受けていない）。最終公開 clip-lab/kaneko/fukada **09-09**・clip-animal **09-06**＝**11〜14日**。`theme_queue` 0件 |
| rhythm-pop | ✅ 完成済み | 06-22 以降 90日変化なし。未コミット19・リモート未設定 |
| claude-codex-bridge | ✅ 完成済み | 07-04 以降 78日変化なし。未追跡1・リモート未設定 |
| （参考）client-ops-platform | 🟢 稼働 | `a8974fd`(09-18)・未追跡2 |
| （参考）ai-orchestrator | ⚪ 休止 | 08-09 以降変化なし |

**本日の公開（JST・`video_id` 実在ベース）**: cf 4 / ds 3 / yokai 3 / scp 2 / socio 1 / 2ch 1 = **14本**
**日別**: 09-14 18 / 09-15 13 / 09-16 14 / 09-17 14 / 09-18 16 / 09-19 15 / **09-20 14**
**発火 15回 に対し公開 14本** — 差の1件は下記 N2。

---

## 2. youtube-factory

### 2-1. ✅ OAuth が解決した（09-14 以降6夜連続の最優先事項）

`logs/backend.log` に `♾️ [oauth] <ch>: リフレッシュトークンは無期限で発行されました（同意画面の本番公開が効いています）` が **7ch分**出ている。

| ch | 状態 |
|---|---|
| 2ch-matome / company-facts / daily-science / scp-lab / socio-rx / yokai-watch | **OK・無期限** |
| **pokemon-lab** | **OK・無期限**（指揮者が4日連続で出していた唯一の依頼。完了） |
| akashic-librarian / fake-paper / clip-lab / clip-fukada / clip-kaneko / clip-animal | ❌ **失効のまま**（6ch。本番公開は効くので、再認可すれば同じく無期限になるはず） |

**代償は1枠だけだった。** 失効時刻（12:05 前後）に scp-lab の生成ジョブ `c885d533`「なぜSCP-055の形だけ、記録から消えるのか？」が完成した直後に refresh が落ち、`⚠️ 自動公開スキップ` で1本が上がらなかった。再認可はその直後で、以降は正常。**09-13 の「5日連続公開ゼロ」は回避された。**

### 2-2. 🆕 リーチ天井の原因が特定され、A/B が走っている（本命）

前回 N3 で「per-video の PDCA では届かない最大の未解決問題」と申し送った件に、本日朝の指揮者が答えを出した（`MEMORY_UPDATE_20260920.md`）。

- 維持曲線を再生位置でコホート分解したところ、**0%・5%・10% は 08-19 前後でほぼ同値**（111.1 vs 107.7）。**冒頭フックは壊れていなかった。** 差は15%以降で開き、100%地点で **17.2% → 9.8%** とほぼ半減する。
- **3週間「離脱は13〜22%地点」として2行目の台本を直し続けてきた前提が間違っていた。** そこは差が開き始める場所であって、損失の本体は後ろにある。
- ループ率・完走率が**5ch同時に 08-19 で落ちて戻っていない**。ch個別の台本改訂では「5ch同時」を説明できない。
- 08-19 に入って**今も撤回されていない末尾変更はエンドカードだけ**（`ddff8f8` `short_endcard.py`・無音静止画1.6〜1.8秒を全6chの末尾に焼き込み・**32日間未検証**）。壊れている指標（完走・ループ）と変更が入った位置（末尾）が一致する。
- 登録/千再生は ①0.512 →②0.510 →③0.730 →④0.436 で、**導入による跳ねが無い＝登録を稼がずにリーチだけ削っている**疑い。

**本日の変更はこのA/B 1件だけ**（実測で確認済み）:

| 群 | ch | `defaults.short_endcard.enabled` |
|---|---|---|
| OFF | daily-science / yokai-watch / 2ch-matome | **false** |
| 対照ON | scp-lab / company-facts | true（**09-27 まで変更禁止**） |
| 除外 | pokemon-lab | true のまま（当時 OAuth 失効で条件が揃わなかったため） |

**判定 09-27。主指標は完走率(95-100%) が OFF群で 11.5%→16%以上へ回復するか。**
⚠️ socio-rx も true のままだが、指揮者のメモではA/Bの群に含まれていない（8本・登録0のため母数不足と思われる）。

### 2-3. 🔴 キュー在庫（実消費される `autopilot.theme_queue`）

`backend/pipeline/title_constraints.check(title, チャンネルJSON全体)` を全数適用。短文で `ok:False` になることを先に確認済み。

| ch | 総数 | 通過 | 枠/日 | 残り日数 | 主な違反 |
|---|---:|---:|---:|---:|---|
| 2ch-matome | 23 | 15 | 1 | 15.0 | `forbid_digits` 7 / `forbid_patterns` 2 |
| company-facts | 10 | 9 | 4 | 2.2 | `require_any_of` 1 |
| yokai-watch | 4 | 4 | 3 | 1.3 | — |
| daily-science | 2 | 2 | 3 | **0.7** | — |
| **scp-lab** | **0** | **0** | 3 | **0.0** | — |
| **socio-rx** | 5 | **0** | 2 | **0.0** | `require_any_of` 5 / `min_effective_chars` 3 |
| **稼働6ch 合計** | **44** | **30** | 16 | | |

推移: 09-17 87/32 → 09-18 61/37 → 09-19 51/29 → **09-20 44/30**。
18:32 のコミット `85f8288` で company-facts に8件が補充され、company-facts は 2→9 に回復した。**その補充で scp-lab と socio-rx は救われていない。**
（参考: pokemon-lab は 21件中12件通過＝4.0日分あるが、autopilot が OFF なので消費されない）

### 2-4. サムネ

**09-20 公開14本のうち 11本が失敗、全て 403**（成功は daily-science 3本のみ・3日連続で同じ分かれ方）。
🔄 前回 N1 で初めて見つかった **2MB超（`Media larger than: 2097152`）は本日は再発していない**。ただし1日のデータなので直ったとは言えない。
優先度は 09-19 に指揮者が引き下げたまま（imp×CTR 由来の再生は総再生の 0.48%）。**「最優先」として扱わない。**

### 2-5. git（取得 23:10）

- HEAD `85f8288`。**本日のコミットは2件のみ**: `e89f8aa`(10:35) `fix(scripts): 相席マッチのメール基盤を流用するのをやめる` / `85f8288`(18:32) `feat(company-facts): 題材8件をキューへ再投入`（エンドカードA/Bの設定もここに同梱されている）。
- **dirty 71件**（自動生成物・`.auto-memory/`・レポート類）。うち **`MEMORY_UPDATE_20260920.md` / `reports/youtube_analysis_20260920.xlsx` / `scripts/orch_apply_20260920.py` の3件が未追跡**＝本日の指揮者の成果物がまだ git に載っていない。
- `neworigin/main...HEAD` = **0 0**（同期）。`origin` は**4遅れ**（二重リモートの整理が未判断）。
- **未マージブランチ 0**（`orch-20260911-followup` は 09-19 に削除済み）。
- `.git` のゴミ: `tmp_obj_*` **623** / `stale_locks` **88** / `_stale` **34**（前回と同数＝増えていない）。

### 2-6. スケジュール

`daily-merge-all-projects` は本日 **22:05 に走った**（`lastRunAt` 09-20 13:05 UTC）が、**`last_merge_log.md` は 09-19 22:08 のまま**。→ **N1（前回解決と報告した件）の再発。**
23時台の3本並走は**8日連続**（`nightly-full-progress` 23:09 / `daily-project-handoff` 23:09 / `vercel-migration-reminder` は本日 `lastRunAt` が 09-19 のまま＝今日は走っていない可能性）。

---

## 3. aiseki

- **HEAD `c92949a`（09-19 23:12）。本日のコミットは0件。** 前日まで2日連続で動いていたので、🆕 **本日は開発が止まっている。**
- dirty 0・`neworigin` と同期・`origin` は1遅れ・未マージブランチなし。
- `https://aisekimatch.com` 正常（HTML 応答・OGP 完備）。
- ✅ **前回 #26「未適用マイグレーションの有無は判定不能」→ 所在が判明。** マイグレーションは `supabase/migrations/` ではなく **`supabase/migration_*.sql` のフラットな29ファイル**。`apply_migrations.command` が当てているのは **`migration_launch.sql` / `migration_fixed_join_fee.sql` / `migration_launch2.sql` の3本だけ**で、残り26本（`migration_dm_autosend.sql` など 09-01 までの分）は**このスクリプトの対象外**。適用済みかどうかは DB 側を見ないと分からないので、**手で管理されている前提**。
- ⚠️ `apply_migrations.command` に Supabase の DB パスワードが平文で2箇所（`.gitignore` 済み・継続）。
- 未着手のまま: Twilio 本番アップグレード / SNS 投稿0件 / ロゴ未作成。

---

## 4. ai-english-coach

- **HEAD `cd2c8c5`（09-08 22:08）＝12日間変化なし。** dirty 0・`_locktest` は main にマージ済み。
- **リモート未設定＝ローカルのみ。バックアップが無い状態が12日続いている。**
- Phase 1 テキスト版は完了（LINE Pay v3 のサブスク・チケット決済基盤 `eec4752`、`lib/coach.ts` への抽出、LINE不要のローカル検証用 debug/mock 画面まで入っている）。`supabase/migrations/0001_initial.sql` `0002_billing.sql` の2本が用意済み。
- 音声課金は未着手。**LINE Pay 加盟店申込（審査あり）が先行ブロッカー。**

---

## 5. 全進捗サマリ

| プロジェクト | URL | ステータス |
|---|---|---|
| youtube-factory | https://youtube-factory-eight.vercel.app | 🟡 稼働。14本/日。**OAuth解決・7ch無期限**。エンドカードA/B中（判定09-27）。scp-lab キュー0 |
| aiseki | https://aisekimatch.com | 🟡 サイト稼働。本日コミット0。**残: Twilio本番 / 営業本番の開始判断 / ロゴ / SNS初投稿 / 実機確認 / 運営体制** |
| fanup | https://fanup-rouge.vercel.app | 🟡 MVP完了・**集客未着手20日**。表示中のサポーター1,248・達成8件はシード値 |
| oripa | https://oripa-omega.vercel.app | 🟡 Phase1 MVP・決済未着手。**サイト本文が空・8日連続**。古物商許可（審査約40日）未取得 |
| ai-english-coach | （未デプロイ） | 🔵 Phase1テキスト版完了・音声課金未着手。**リモート未設定** |
| 切り抜きラボ（clip-lab / clip-kaneko / clip-fukada / clip-animal） | — | 🔴 **全停止11〜14日**。autopilot 全OFF・OAuth 失効・キュー0件。本日の本番公開の恩恵も受けていない |
| rhythm-pop | — | ✅ 完成済み（90日変化なし・リモート未設定） |
| claude-codex-bridge | — | ✅ 完成済み（78日変化なし・リモート未設定） |

**登録者（`data/reports/latest.md` 09-20 22:30 生成）**

| ch | 登録者 | 前日比 | 総再生 | 本数 |
|---|---:|---:|---:|---:|
| scp-lab | **169** | **-1** | 178,325 | 208 |
| daily-science | **74** | **-2** | 216,065 | 233 |
| company-facts | 44 | ±0 | 75,449 | 72 |
| yokai-watch | **28** | **-3** | 62,575 | 75 |
| **pokemon-lab** | **15** | 🆕 **測定再開** | 62,017 | 56 |
| 2ch-matome | 11 | ±0 | 49,563 | 55 |
| socio-rx | 0 | ±0 | 5,495 | 8 |
| **稼働6ch 計** | **326** | **-6** | | |

⚠️ **3ch で登録者が減った。** ただし pokemon-lab が測定に復帰したこと、latest.md の生成時刻が前日と異なることもあり、**1日の増減に構造的説明を与えない**（09-18 の教訓）。残5ch（akashic-librarian・fake-paper・clip系4）は OAuth 失効で測定不能のまま。

---

## 6. 検出した課題

### ✅ 解決済み（次回「要対応」として報告しないこと）

- **🚨 #1「GCP OAuth 同意画面がテスト中」→ 解決。** 本番公開され、7ch が無期限トークンで再発行された。**09-14 から6夜連続で書いてきた期限付きブロッカーが消えた。**
- **🔴 #2「pokemon-lab 未再認可」→ 解決。** 指揮者が4日連続で出していた唯一の依頼。**ただし autopilot が OFF のままなので、公開はまだ始まらない（下記 N3）。**
- **🟠 aiseki #26「未適用マイグレーションの有無が判定不能」→ 所在が判明。** `supabase/migration_*.sql` の29ファイル。`apply_migrations.command` が当てているのは3本のみ。適用状況の判定には DB 側の確認が要る。
- **前回 N3「リーチ天井の原因不明」→ 仮説が1本に絞られ検証が走った。** エンドカード。09-27 判定。**「原因不明」としては報告しない。**
- **前回 N1「サムネ 2MB超」→ 本日は再発なし。** ただし n=1日。
- **#9「未マージブランチ `orch-20260911-followup`」→ 前回削除済み。** 3リポジトリとも未マージ 0。

### ❌ 未解決（継続）

| # | 内容 | 継続 | 09-20 実測 |
|---|---:|---|---|
| 1 | 🔴 **scp-lab のキューが 0 件** | 🆕 | 枠3/日に対し在庫ゼロ。18:32 の補充は company-facts のみ |
| 2 | 🔴 socio-rx のキュー通過 0 件 | **3日** | 6→5件・`require_any_of` 5 / `min_effective_chars` 3。09-18 から1件も直っていない |
| 3 | 🔴 OAuth 未再認可の残6ch | 継続 | akashic-librarian / fake-paper / clip系4。**本番公開済みなので再認可すれば無期限になる** |
| 4 | 🔴 `ANTHROPIC_API_KEY` 401 | **9日** | `latest.md` の全chで「認証エラー」。キーは `backend/.env` 18行目に存在するが通らない |
| 5 | 🟠 サムネ403 | 9日 | 14本中11本。優先度は引き下げ済み |
| 6 | 🟠 `channel_metrics` が3日遅れ | 継続 | 最終 **09-17**（`video_metrics` は 09-20）。前回から1日進んだ |
| 7 | 🟠 `threads.json` が空 | **16日** | `{}` / `data/image_requests/threads.json`（09-04 から変化なし） |
| 8 | 🟠 画像ブリッジ pending 増加 | 継続 | **724**（前回684・**+40/日**）。failed 235 は新規なし |
| 9 | 🟠 `viral_translation_pending` 17件 | 継続 | 変化なし |
| 10 | 🟠 `.git` のゴミ | 横ばい | `tmp_obj_*` **623** / `stale_locks` **88** / `_stale` **34**（前回と同数） |
| 11 | 🟠 回帰テストが測れない | **10日** | サンドボックスに pytest 無し |
| 12 | 🟠 oripa `feat/stripe-checkout` 未マージ | **40日** | HEAD がこのブランチのまま |
| 13 | 🟠 oripa サイト本文が空 | **8日** | 到達するが body が空 |
| 14 | 🟠 ai-english-coach リモート未設定 | 継続 | 凍結12日 |
| 15 | 🟠 aiseki: Twilio / SNS未投稿 / ロゴ未作成 | 継続 | 変化なし |
| 16 | ⚠️ 23時台の cron 並走 | **8日** | `nightly-full-progress` と本タスクが 23:09 で同時 |
| 17 | ⚠️ `auto_optimize_schedule=true` が2ch | 🔽改善 | **company-facts / socio-rx のみ**（前回4ch → akashic-librarian・fake-paper が外れた） |
| 18 | 🟠 `data/job_queue.json` 20MB | 継続 | 上限・ローテーション無し |
| 19 | ⚪ `data/analytics.db`(0B) / `data/video_status.db`(0B) | 継続 | Mac 側でないと削除不可 |
| 20 | ⚪ 未コミット: fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 / oripa 1 / client-ops 2 | 継続 | 変化なし |
| 21 | ⚪ 二重リモート（origin 4遅れ / neworigin 同期） | 継続 | yf・aiseki とも |

### 🆕 NEW

| # | 内容 |
|---|---|
| **N1** | 🔴 **`daily-merge-all-projects` がまた空振りした。** 22:05 に実行されている（`lastRunAt` 09-20 13:05 UTC）のに **`last_merge_log.md` は 09-19 22:08 のまま**。前回「解決」と報告した件の**再発**。09-17・09-18 に続き3度目。本日のコミット2件はいずれも 10:35 と 18:32 で、マージ run の時刻ではない |
| **N2** | 🟠 **OAuth 失効の瞬間に scp-lab の1枠を落とした。** ジョブ `c885d533` は動画のレンダリングまで完走した直後に refresh が落ち、`自動公開スキップ`。**生成コストは払って公開だけ失った。** `publish_blocked` ではなくこの経路なので、`publish_blocked` 0件を見ても気付けない |
| **N3** | 🔴 **pokemon-lab は再認可されたのに `autopilot.enabled=false` のまま。** キューは21件中12件通過（4.0日分）あり、指揮者の評価では**成熟動画の40%が1,200再生超＝6ch中いちばん天井が高い**。**ONにするだけで明日から3本/日が増える。** 今いちばん費用対効果の高い1操作 |
| **N4** | 🆕 **`scripts/token_expiry_alert.py` が作られた**（09-19 23:36 `ad46ca1`、09-20 10:35 `e89f8aa` で修正）。OAuth 残寿命が危ういときだけ短く出す。作者コメントに「245KBのログと長いレポートに埋もれて 09-19 の一斉失効を誰も拾えなかった」とある。**通知は送らない設計（終了コード2を返すだけ）なので、呼び出し側の routine に繋がないと鳴らない** |
| **N5** | 🟠 **aiseki が本日ゼロコミット。** 09-18・09-19 と動いていたので変化。止めたのか一時的かは判断材料なし |
| **N6** | 🟠 **登録者が3ch で減少**（scp -1 / ds -2 / yokai -3・6ch計 332→326）。**ただし n=1日。構造的説明を与えない**（09-18 の教訓）。エンドカードA/Bの主指標は完走率・ループ率であって登録者ではない |
| **N7** | 🔽 **`auto_optimize_schedule=true` が4ch→2ch に減った**（akashic-librarian・fake-paper が false 化）。前回の懸念#17 は半分解消 |
| **N8** | ⚠️ **指揮者の本日の成果物3点が未追跡**（`MEMORY_UPDATE_20260920.md` / `youtube_analysis_20260920.xlsx` / `scripts/orch_apply_20260920.py`）。N1 の空振りと同じ原因。**A/B の根拠文書が git に載っていない状態で 09-27 の判定を迎えることになる** |

---

## 7. ユーザー手動待ちタスク一覧

**⭐ 今いちばん効くもの**

1. ⭐ **pokemon-lab の autopilot を ON にする**（N3）— OAuth は通った。**キュー4日分あり、6ch中いちばん天井が高い。ONにするだけで明日から3本/日**
2. 🔴 **scp-lab のテーマキュー補充**（在庫0・枠3/日）
3. 🔴 **socio-rx のキュー修正**（5件中0件通過・`require_any_of` 5件。3日連続で同じ5件）
4. **残6ch の OAuth 再認可**（akashic-librarian / fake-paper / clip系4）— **同意画面はもう本番なので、今やれば全部無期限になる**。akashic-librarian は実力3位
5. 🔴 **`ANTHROPIC_API_KEY` を貼り直す**（`backend/.env` 18行目・9日連続で401）

**判断が要るもの**

6. 🆕 **`daily-merge-all-projects` が3度目の空振り（N1）** — 22:05 の実行が何もしていない。タスク定義を見直すか、23時台の並走（#16）とまとめてスケジュールをずらすか
7. 🆕 **`token_expiry_alert.py` を実際に鳴らす配線**（N4）— 今は終了コードを返すだけで誰も呼んでいない
8. 2ch-matome の `forbid_digits` を緩めるか（7件が該当。ただし「数字あり」は 09-17 実測 0.72倍で負）
9. 23時台の cron をずらす（8日連続で並走）
10. `auto_optimize_schedule=true` の残2ch（company-facts / socio-rx）を自動最適化に任せるか
11. 切り抜き4chを畳むか（全停止11〜14日・キュー0件・再認可もされていない）
12. fake-paper を止めるか作り直すか
13. `origin`(zaki21016) と `neworigin`(rikoandmakoto-ops) の二重リモートを片方に寄せるか（origin が4遅れ）
14. oripa `feat/stripe-checkout` を main へマージするか（40日）
15. サムネ403（電話確認）をいつやるか — 急ぎではない扱いのまま

**⛔ 09-27 まで触ってはいけないもの**

16. **`defaults.short_endcard.enabled`（daily-science / yokai-watch / 2ch-matome / scp-lab / company-facts）** — 対照群を動かすとA/Bが丸ごと無駄になる
17. 評価待ちの設定変更: **09-24** 投稿時刻（09-17変更）/ **09-25** 文字数帯3ch（09-18変更）/ **09-26** 冒頭重複修正（09-19変更）/ **09-27 ★本命** エンドカードA/B / **10-02** 2ch-matome エンハンサー停止

**環境の掃除（Mac 側でないと消せない）**

18. `rm -rf .git/stale_locks .git/_stale && find .git/objects -name 'tmp_obj_*' -delete && git gc --prune=now`（**623/88/34**）
19. ホストで `pytest backend/tests`（**10日間**未測定）
20. `data/analytics.db`(0B) / `data/video_status.db`(0B) の削除
21. `data/job_queue.json` 20MB の上限・ローテーション要否
22. `git push origin main`（4コミット）— または `git remote remove neworigin`。#13 次第

**aiseki**

23. Twilio 本番アップグレード / `dm_targets` CSV 取り込み / 営業本番の開始判断（先頭 `1000bero_net`・**1日30件・間隔30〜120秒は変えない**）
24. ロゴ生成 → Instagram プロフ写真差し替え / SNS 初投稿（**投稿0件**）
25. ⚠️ `apply_migrations.command` に Supabase DB パスワードが平文で2箇所（`.gitignore` 済み）
26. 🆕 **`supabase/migration_*.sql` 29本のうち `apply_migrations.command` が当てているのは3本だけ。** 残り26本の適用状況を DB 側で確認するか、スクリプトを実態に合わせる
27. 実機動作確認 / 運営体制（通報対応者・営業許可・本店所在地）

**ai-english-coach**

28. **GitHub リモートの作成と push**（09-08 以降ローカルのみ＝バックアップ無し・**12日**）
29. **LINE Pay 加盟店申込**（審査があるので最優先）/ LINE公式アカウント / Supabase / Vercel / OpenAIキー / Webhook疎通

**その他**

30. ChatGPT スレッドURLを13ch分登録（`threads.json` が `{}` のまま**16日**）/ 画像ブリッジ pending **724**（+40/日）
31. oripa サイト本文が空（**8日連続**）/ 古物商許可（審査約40日）
32. fanup 25 / rhythm-pop 19 / bridge 1 / ai-orchestrator 1 の整理（任意）
33. rhythm-pop / claude-codex-bridge / ai-orchestrator / ai-english-coach は**リモート未設定**（バックアップ無し）

---

## 8. 次回（09-21）に確認すること

- ⭐ **pokemon-lab の autopilot が ON になったか**（なっていれば公開が 14 → 17本/日になるはず）
- **scp-lab / socio-rx のキューが補充されたか**（在庫0＋通過0）
- **OAuth 7ch が無期限のままか**（本番公開が効いていれば失効しないはず。**ここが崩れたら本番公開が効いていない**）
- **残6ch が再認可されたか**
- 🆕 **`last_merge_log.md` が更新されたか**（N1・3度目の空振り）
- 🆕 **指揮者の成果物3点がコミットされたか**（N8）
- **`ANTHROPIC_API_KEY` の401が消えたか**（9日連続）
- **公開本数**（今日14本・`自動公開スキップ` 1件）／**サムネ 2MB超の再発**
- **登録者の減少（N6）が続くか**（n=1日では判断しない。**2日続いたら初めて見る**）
- **aiseki が再開したか**（N5）
- **09-24** 投稿時刻 / **09-25** 文字数帯 / **09-26** 冒頭重複 / **09-27 ★** エンドカードA/B

---

## 9. 計測方法の注意（次回実行者向け）

- 🆕 🔴 **`publish_blocked` が0でも枠は落ちる。** 本日の scp-lab は `⚠️ 自動公開スキップ (<job_id>): チャンネル '<ch>' — トークン失効のため要再認可` という別経路で1枠失った。**`Autopilot fired` の回数と公開本数を突き合わせ、ズレたら `自動公開スキップ` も grep する。**
- 🆕 **OAuth の再認可は `logs/backend.log` の `♾️ [oauth] <ch>: リフレッシュトークンは無期限で発行されました` で確認できる。** `latest.md` の OAuth 表より早く・確実に分かる。
- 🆕 **`data/channels/*.json.bak_*` は `.gitignore` の `data/**/*.bak_*` で除外される。** バックアップの有無は `git status` では見えないので `ls` すること。
- 🆕 **指揮者の設定変更は別コミットとは限らない。** 本日のエンドカードA/Bは `85f8288`「company-facts の題材8件をキューへ再投入」に同梱されていた。**コミットメッセージで設定変更の有無を判断しない。`git show --stat` でファイルを見る。**
- 🔴 **`.git/index` を cp して `GIT_INDEX_FILE` に使ってはいけない。** 必ず `export GIT_INDEX_FILE=/tmp/<ユニーク名> && git read-tree HEAD` で作り直す。使うと dirty が二重に見える。
- 🔴 **`Autopilot fired` を `grep -c` で数えない。** 1行に2〜4回まとめて出る。`grep -o ... | sort | uniq -c` を使う。
- **サムネ失敗は403だけではない**（09-19 に `Media larger than: 2097152` を初確認）。**成功本数＝公開本数 −（全失敗の distinct video_id）** で出す。1本につき2行出るので行数で数えない。
- **キュー在庫の実消費は `data/channels/<ch>.json` の `autopilot.theme_queue`。** `data/channels/<ch>/theme_queue.json` は seeds で別物。**どちらか必ず明記する。**
- **枠数は `autopilot.schedule.times` の要素数。** `slots` や `videos_per_day` というキーは無い。
- 🔴 **`title_constraints.check()` の第2引数は「チャンネル JSON 全体」**（`hard_constraints` を渡すと全件 `ok:True`）。`cd backend` してから `from pipeline import title_constraints`。**必ず短い文字列で `ok:False` を確認してから集計する。**
- **カウンタは mtime の分布まで見る。** `failed` 235件は「詰まっている」ではなく「09-08 以降 新規が来ていない」。
- **23時台は他タスクが並走する。** git 系の数値は取得時刻を併記する。
- **公開実績は `data/video_publish.db` の `video_status`**（`data/video_status.db` は0バイト）。ch列は `channel_id`。`published_at` は UTC → `date(datetime(published_at,'+9 hours'))`。
- **analytics は `data/analytics/analytics.db`**（`data/analytics.db` は0バイト）。`sqlite3.connect('file:...?mode=ro', uri=True)` で開く。
- **登録者数と OAuth の生死は `data/reports/latest.md`**（`oauth_tokens.expires_at` で判定しない）。
- **aiseki のマイグレーションは `supabase/migrations/` ではなく `supabase/migration_*.sql` のフラット配置。** 「ディレクトリが無い＝判定不能」と書かない。
- **スケジュールの生死は `list_scheduled_tasks` の `lastRunAt`。** ただし**「走った」と「成果物を出した」は別**（本日のマージ run が実例）。**出力ファイルの mtime も見る。**
- **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink 不可（EPERM）だが rename は通る。** `git merge`/`checkout` は原理的に失敗する。マージ可否は `/tmp` の `git clone -s` で判定。
- **`curl` は egress 不可。** サイト疎通は `web_fetch`、URL はタスク定義に載っているものだけ。
- **サンドボックスに pytest が無い。** 回帰テストはホストでしか測れない。
- **`video_metrics.views` は直近30日窓。** 同一動画でも日をまたいで減る。「再生が減った」と読まない。
- **比較は必ず公開3日以上の動画で。** d0〜d2 は構造的にほぼ0（指揮者 09-20 実測）。
- **`title_constraints.repair()` をキューのタイトルに当ててはいけない**（日本語が壊れる）。`min_effective_chars` は `UNREPAIRABLE_RULES`。

---

*主要12項目は別エージェントで独立再計測 → **不一致 0件**。*
