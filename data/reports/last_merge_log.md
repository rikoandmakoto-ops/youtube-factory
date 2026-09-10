# 全プロジェクト マージ・整理ログ

実行日時: 2026-09-09 22:00 〜 2026-09-10 00:10 (JST)
対象: youtube-factory / aiseki / ai-english-coach

---

## サマリ

| リポジトリ | マージ | コミット | push |
|---|---|---|---|
| youtube-factory | 対象なし（mainのみ） | 4件（67ファイル） | **失敗（認証情報なし）** |
| aiseki | 対象なし（mainのみ） | なし（作業ツリーはクリーン） | 未実施（既に origin より 4 コミット先行） |
| ai-english-coach | 対象なし（`_locktest` は main にマージ済み） | なし（作業ツリーはクリーン） | 該当なし（remote 未設定） |

---

## Phase 1: マージ

### youtube-factory
- ローカルブランチは `main` のみ。未マージブランチなし。
- コンフリクト: なし。

### aiseki
- ローカルブランチは `main` のみ。未マージブランチなし。
- コンフリクト: なし。

### ai-english-coach
- ブランチ: `main`, `_locktest`
- `git merge-base --is-ancestor _locktest main` → **`_locktest` は main にマージ済み**。マージ操作は不要。
- コンフリクト: なし。

---

## Phase 2: 整理・コミット

### youtube-factory（4コミット / 計67ファイル）

1. `302e28c` **データ更新: 分析・チャンネル設定・オリジナリティ・トレンドを09-09時点に同期**
   - 25ファイル (+1205 / -676)
   - `data/analytics/` 3件、`data/channels/` 8件、`data/cta_history/`、`data/fact_ledger/`、`data/originality/` 8件、`data/series_links/`、`data/trends/` 2件、`data/analytics/viral_translation_pending/viral_1wapy6u.json`（新規）

2. `8b2e996` **テーマキュー追加: 全7チャンネルの新規シナリオ25件とアーカイブ索引を更新**
   - 28ファイル (+10837)
   - 2ch-matome / akashic-librarian / company-facts / daily-science / fake-paper / pokemon-lab / scp-lab / yokai-watch のテーマキュー json、アーカイブ `_index.json` 3件、アーカイブ済みシナリオ md 3件

3. `f476dcc` **指揮者スクリプト追加: 09-09の適用・検証・xlsx生成スクリプトと分析レポート**
   - 12ファイル (+1355)
   - `scripts/orch_*_20260909.py` 10件 + `scripts/orch_cache_values.py`、`reports/youtube_analysis_20260909.xlsx`、`trigger_20260909.command`

4. `d2fa066` **docs: HANDOFF更新と09-09のメモリ更新メモを追加**
   - 2ファイル (+344): `HANDOFF.md`、`MEMORY_UPDATE_20260909.md`

作業ツリーは上記コミット後クリーン（.gitignore 対象を除く）。

### aiseki
- `git status` クリーン。未コミット・未追跡ファイルなし。コミットなし。

### ai-english-coach
- `git status` クリーン。未コミット・未追跡ファイルなし。コミットなし。

---

## .gitignore への追加

**追加なし（3リポジトリとも）。**

理由:
- youtube-factory の `.gitignore` には既に `data/ab_tests/`、`*.audit.mjs`、`data/reports/YYYY-MM-DD/`、`output/`、`*.mp4` 等の生成物パターンが揃っており、今回の未追跡ファイルに新たな生成物・一時ファイルは含まれていなかった。
- `scripts/orch_*_20260909.py` / `trigger_20260909.command` / `reports/youtube_analysis_*.xlsx` は一見「日付付きの使い捨て」だが、リポジトリの既存慣習（`scripts/apply_pdca_20260901.py`、`restart_and_trigger_20260908.command`、`reports/youtube_analysis_20260908.xlsx` 等が全て追跡済み）に合わせて **ignore ではなくコミット** した。
- aiseki / ai-english-coach は未追跡ファイルなし。

## 機密情報チェック

- 新規追加した `scripts/orch_*.py`（11件）と `trigger_20260909.command` を `api_key` / `secret` / `token` / `password` / `AIza` / `sk-` / `ghp_` / `Bearer` / `client_secret` でスキャン → **ヒット0件**。
- その他の追加分はデータ JSON と Markdown のみ（既存の追跡対象と同種）。
- 全差分に対する一括スキャンは、最後にサンドボックスのシェルが停止したため未完了。次回実行時に再確認すること。

---

## Phase 3: push 結果

### youtube-factory — **push 失敗**
```
$ git push origin main
fatal: could not read Username for 'https://github.com': No such device or address
```
- 原因: 指揮者が動いている Linux サンドボックスに GitHub の認証情報がない（credential.helper 未設定、`~/.git-credentials` なし）。Mac の Keychain にある認証情報はサンドボックスから参照できない。
- 状態: `main` は `origin/main` より **4 コミット先行**（ローカルにのみ存在）。データ消失はない。
- **要対応（人手）**: Mac 上で以下を実行すること。
  ```
  cd ~/Developer/youtube-factory && git push origin main
  ```

### aiseki — **push 未実施**
- 作業ツリーはクリーンだが、`main` は `origin/main` より **4 コミット先行**（今回より前からの未 push 分。最新は `1538169 docs: マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加`）。
- 同じ認証情報の問題で push できないため未実施。
- **要対応（人手）**: `cd ~/Developer/aiseki && git push origin main`

### ai-english-coach — **該当なし**
- remote が 1 つも設定されていない（`git remote -v` が空）。push 先なし。

---

## 環境上の注意（次回実行者向け）

1. **マウント上で `unlink` が禁止されている。**
   サンドボックスから `/Users/.../Developer` へは書き込み・rename はできるが削除ができない。
   このため git が `*.lock` や `.git/objects/*/tmp_obj_*` を消せず、`warning: unable to unlink ...` が多発し、
   ロックが残って以降の git 操作が全て失敗する。
   → 対処として `.git` 配下の `*.lock` を `.git/stale_locks/` へ **mv して退避** する方式を取った。

2. **`git commit` / `git status`（全体）は 178 秒のツールタイムアウトに間に合わない。**
   マウントの stat が遅く、追跡ファイル 3075 件のスキャンだけで 50〜120 秒かかる。
   → `git status --porcelain -- <ディレクトリ>` で分割し、コミットは
   `git add` → `git write-tree` → `git commit-tree` → `git update-ref` の配管コマンドで実行した
   （`git commit` はインデックス全体を refresh するため必ずタイムアウトする）。

3. **退避したロックファイル / ゴミ**（Mac 側で手動削除してよい）
   - `youtube-factory/.git/stale_locks/`（旧 `refs/heads/main.lock.stale.*` 6件 + 今回分の index.lock / HEAD.lock / main.lock）
   - `ai-english-coach/.git/stale_locks/`（旧 `refs/heads/_locktest.lock.stale.*` 1件）
   - `youtube-factory/.git/objects/*/tmp_obj_*` 約 340 件（`git gc` では消えないので手動 or Mac 上で削除）
   ※ 退避により `warning: ignoring broken ref refs/heads/main.lock.stale.*` は解消済み。

4. **force push / reset --hard は一切実行していない。** 他プロジェクトにも触れていない。
