# 全プロジェクト マージ・整理ログ — 2026-09-13

実行: 2026-09-13 00:12 JST（daily-merge-all-projects 自動実行）
対象: youtube-factory / aiseki / ai-english-coach

---

## 0. 結論（3行）

1. **コミットは3リポジトリとも完了**。youtube-factory に2コミット追加し、作業ツリーは3リポジトリ全て clean。
2. **push は全リポジトリで不可**。サンドボックスに GitHub の認証情報が無い（`could not read Username for 'https://github.com'`）。**未 push は youtube-factory 24件 / aiseki 4件**。Mac 側で `git push` が必要。
3. **youtube-factory の `orch-20260911-followup` はコンフリクト2件でマージせず**（規定どおり報告のみ）。手動対応が必要。

---

## 1. マージ結果

| リポジトリ | 未マージブランチ | 結果 |
|---|---|---|
| youtube-factory | `orch-20260911-followup`（main より3コミット先行） | ⛔ **コンフリクト2件 — マージ中止** |
| aiseki | なし | — |
| ai-english-coach | なし（`_locktest` は main の祖先で既にマージ済み） | — |

### youtube-factory のコンフリクト詳細

`/tmp` に `git clone -s` した検証用クローンで判定（理由は §4）。`main`(8d1249f) × `orch-20260911-followup`(8badac5)、共通祖先 14eb733。

自動マージできたファイル（9件）: `.auto-memory/2026-09-11.md`, `data/analytics/clip_state.json`,
`data/channels/{akashic-librarian,company-facts,daily-science,fake-paper,pokemon-lab,scp-lab,yokai-watch}.json`

**衝突したファイル（各1ハンク）:**

1. **`.auto-memory/INDEX.md`**
   - 衝突の中身: 「config 変更が稼働中プロセスに上書きされる」教訓の記述。
     main 側は 09-12 に追記された**新しい版**（`patch_channel_file` 集約で事故が止まった旨・数値突合の教訓・unlink 制約）で、
     ブランチ側は 09-11 時点の**古い版**。
   - 所見: **main 側（HEAD）を採用すれば足りる**内容。ブランチ側に main に無い情報は見当たらない。

2. **`data/channels/2ch-matome.json`**（`theme_queue` 付近、777行目あたり）
   - 衝突の中身: テーマキューの項目。main 側は該当区間が空（消化済み）、ブランチ側に
     `81377fd7`「ちいかわ寿司コラボが中止になった本当の理由」など**09-11 に改題した未消化テーマ**が残る。
   - 所見: キューは日々消化・補充される生きたデータなので、**片方を機械的に採るのは危険**。
     現行キューの残量を見てから、必要なテーマだけ拾うのが安全。

**ブランチ側にしか無い実質的な変更（マージ未達のため main に未反映）:**

```
backend/pipeline/title_constraints.py     |  10 +-   ← effective_len がハッシュタグ判定で本文を落とす不具合の修正
backend/tests/test_fixes_20260911.py      |  27 +    ← 上記の回帰テスト
reports/make_youtube_analysis_20260911.py |  55 +-   ← 実効文字数集計の修正
reports/youtube-analysis-2026-09-11.xlsx  | Bin      ← 再生成
```

> ⚠️ ただし `title_constraints.py` の同等の修正は main 側にも `af84e4a` /
> `8badac5` 相当の内容で入っている可能性がある（コミットメッセージが酷似）。
> 手動マージ前に `git diff main...orch-20260911-followup -- backend/pipeline/title_constraints.py`
> で**実差分が残っているかを先に確認すること。** 残っていなければブランチは削除してよい。

### 手動マージ手順（Mac 側で実行）

```bash
cd ~/Developer/youtube-factory
git diff main...orch-20260911-followup -- backend/pipeline/title_constraints.py   # まず実差分の有無を確認
git merge --no-ff orch-20260911-followup
# .auto-memory/INDEX.md      → HEAD 側を採用   : git checkout --ours .auto-memory/INDEX.md
# data/channels/2ch-matome.json → キュー残量を見て手で調整
git add -A && git commit
```

---

## 2. コミット内容

### youtube-factory — 2コミット / 計86ファイル

| コミット | 内容 | ファイル数 |
|---|---|---|
| `7b226a3` | 台本: 各チャンネルの新規シナリオとアーカイブを追加（9ch分） | 49 |
| `88d1a18` | 09-12 データ更新: チャンネル設定・分析/PDCAメモリ・トレンド・レポート・制作トリガ | 37 |

`88d1a18` の内訳: `data/channels/` 8件、`data/originality/` 7件、`data/pdca-memory/` 3件、
`data/analytics/` 7件、`data/cta_history/` 1件、`data/fact_ledger/` 1件、
`data/trends/{google_japan,youtube_JP_27_28}_2026-09-12.json`、
`data/reports/{last_handoff_log.md,latest.md,pdca_history.xlsx,project_handoff_2026-09-11.md}`、
`reports/youtube_analysis_20260912.xlsx`、`scripts/orch_trigger_20260912.command`、
`MEMORY_UPDATE_20260912.md`

> ℹ️ 当初は6コミットに分ける予定だったが、1回目の commit 実行中に `.git/refs/heads/main.lock` が
> 消せず後続5グループが同一 index に積み上がったため、2コミット目にまとめて `--amend` で
> メッセージを実態に合わせた。分割粒度が粗い点は次回の改善対象。

さらに、本タスク実行中に**別プロセス（夜間の引き継ぎタスク）が並行して 2件コミット・書き込み**していた。
その分も取り込んでコミット済み:

| コミット | 内容 | 備考 |
|---|---|---|
| `9c3161e` | 夜間全進捗 09-12: schedule 変更が稼働中プロセスに反映されない事実を確定 | 別プロセスが作成 |
| `8d1249f` | 09-13 データ同期: 分析・PDCAメモリ・チャンネル設定・引き継ぎレポートを反映 | 本タスクが13ファイルをコミット |

**最終 HEAD: `8d1249f` / 作業ツリー clean**

### aiseki — コミットなし
作業ツリー clean。未マージブランチなし。既存の未 push 4コミットのみ。

### ai-english-coach — コミットなし
作業ツリー clean。未マージブランチなし。リモート未設定。

---

## 3. .gitignore に追加したパターン

**追加なし（3リポジトリとも）。**

youtube-factory の未追跡ファイルは全て、**既に追跡対象として運用されている種類**だった:

| 未追跡だったもの | 判断 |
|---|---|
| `data/trends/*_2026-09-12.json` | `data/trends/` は 05-11 以降ずっと追跡済み → コミット |
| `data/analytics/viral_translation_pending/viral_1we9dwn.json` | 同ディレクトリの他ファイルが追跡済み → コミット |
| `scripts/orch_trigger_20260912.command` | `trigger_autopilot_20260830/20260911.command` が追跡済み → コミット |
| `reports/youtube_analysis_20260912.xlsx` | 過去分の xlsx が追跡済み → コミット |
| `MEMORY_UPDATE_20260912.md` / `data/reports/project_handoff_*.md` | 記録資産 → コミット |
| `data/scenarios/**` | 台本キュー・アーカイブ、従来どおり追跡 → コミット |

既存 .gitignore に `data/ab_tests/`・`*.audit.mjs`・`data/**/*.bak_*`・`*.xlsx.tmp` 等は
既に入っており、今回それらの取りこぼしは発生していない。

### 機密情報チェック

コミット対象の全ファイル（xlsx を除くテキスト）を
`AIza…` / `sk-…` / `ghp_…` / PRIVATE KEY / `client_secret|refresh_token|access_token|api_key|password` の
パターンで走査 → **検出ゼロ**。
`scripts/orch_trigger_20260912.command` は管理パスワードを `read -r -s` で対話入力する作りで、
ハードコードは無し（使用後 `unset` もしている）。

---

## 4. push 結果

| リポジトリ | remote | 未 push | 結果 |
|---|---|---|---|
| youtube-factory | `origin` = zaki21016/youtube-factory<br>`neworigin` = rikoandmakoto-ops/youtube-factory | **24** (neworigin 比では 56) | ⛔ **失敗（認証情報なし）** |
| aiseki | `origin` = zaki21016/aiseki<br>`neworigin` = rikoandmakoto-ops/aiseki | **4** | ⛔ **失敗（認証情報なし）** |
| ai-english-coach | なし | — | — （remote 未設定） |

```
fatal: could not read Username for 'https://github.com': No such device or address
```

ネットワーク自体は通っている（`https://github.com` → 200）。
サンドボックスに credential.helper / `~/.netrc` / `~/.git-credentials` / `GH_TOKEN` のいずれも無いのが原因。
**push は Mac 側で実行が必要:**

```bash
cd ~/Developer/youtube-factory && git push origin main && git push neworigin main
cd ~/Developer/aiseki            && git push origin main && git push neworigin main
```

---

## 5. 環境側の制約（今回ブロッカーになった点 / 承認すれば解消するもの）

### 5.1 マウントで unlink（削除）ができない — **これが最大の制約**

`/Users/ayukiyamazaki/Developer/*` のマウントは**ファイル削除が一切 EPERM**。
書き込み・作成・上書き・`mv`（rename）は可能。帰結:

- `git add` / `commit` / `log` は動く（lock は rename で消費されるため）
- `git status` は**毎回 `.git/index.lock` を残す**
- **`git merge` / `git checkout` は `error: unable to unlink old '<file>'` で必ず失敗する**
  → 今回はマージ可否の判定を `/tmp` の作業用クローン（`git clone -s`）で行った

残った lock は削除できないので `.git/stale_locks/` へ `mv` して退避した。
**`.git/stale_locks/` にゴミが溜まり続けているので、ホスト側で削除してよい:**

```bash
rm -rf ~/Developer/{youtube-factory,aiseki,ai-english-coach}/.git/stale_locks
rm -f  ~/Developer/youtube-factory/.git/*.stale* ~/Developer/youtube-factory/.git/stale_index.lock.bak
rm -rf ~/Developer/youtube-factory/.git/_stale
```

削除権限の付与を自動実行中に要求したが、**承認者不在のため自動で却下された**。
この権限を事前に許可しておけば、次回から**サンドボックス内でマージまで完了できる**。

### 5.2 push 用の認証情報が無い
→ §4 のとおり。`GH_TOKEN` をサンドボックスに渡すか、push は Mac 側で行う運用にする。

### 5.3 並行実行
本タスクの実行中に別の夜間タスクが同じ repo にコミット・書き込みしていた（`9c3161e`）。
衝突は起きなかったが、**スケジュール時刻をずらすか、排他を入れたほうが安全**。

---

## 6. 次のタスク（daily-project-handoff）への申し送り

- [ ] youtube-factory: `git push origin main` / `git push neworigin main`（24コミット未反映）
- [ ] aiseki: `git push origin main` / `git push neworigin main`（4コミット未反映）
- [ ] youtube-factory: `orch-20260911-followup` の手動マージ（コンフリクト2件、§1 に手順）
      — 先に `title_constraints.py` の実差分が残っているか確認。無ければブランチ削除で可。
- [ ] `.git/stale_locks/` の掃除（§5.1）
- [ ] 検討: サンドボックスへの削除権限付与 / GH_TOKEN 供給 / 夜間タスクの時刻分散
