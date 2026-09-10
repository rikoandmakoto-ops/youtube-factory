# 全プロジェクト マージ・整理ログ

**実行日時**: 2026-09-10 22:09 JST
**対象**: youtube-factory / aiseki / ai-english-coach

---

## Phase 1: マージ結果

| リポジトリ | ローカルブランチ | 未マージ | 実施したマージ | コンフリクト |
|---|---|---|---|---|
| youtube-factory | `main` のみ | なし | なし | なし |
| aiseki | `main` のみ | なし | なし | なし |
| ai-english-coach | `main`, `_locktest` | なし（`_locktest` は `main` に取り込み済み） | なし | なし |

`git branch --no-merged main` は3リポジトリとも空。**マージ作業は発生せず、コンフリクトもゼロ。**

`ai-english-coach` の `_locktest` は `main` と差分ゼロ（`git log main.._locktest` が空）。過去のロック検証で作られた残骸ブランチと思われるが、削除は指示外なので放置した。

---

## Phase 2: 整理・コミット

### youtube-factory — **6コミット**

作業前の未コミット/未追跡は 104 件（変更30 / 未追跡74）。内容ごとに6本へ分割した。

| コミット | ファイル数 | メッセージ |
|---|---|---|
| `041288b` | 23 | データ更新: 分析・チャンネル設定・オリジナリティ・シリーズリンクを09-10時点に同期 |
| `d4c3ae3` | 73 | テーマキュー追加: 全7チャンネルの新規シナリオと本日分アーカイブ・索引を更新 |
| `d8be8d2` | 2 | data: 09-10 の Google/YouTube トレンド取得結果を追加 |
| `9dfb5bf` | 2 | data: 指揮者タスクの09-10チャンネル分析結果を追加 |
| `1b55b91` | 4 | レポート追加: 09-10 指揮者レポート2件とxlsx生成スクリプト、.gitignoreに\*.xlsx.tmpを追加 |
| `9a9f4c1` | 2 | docs: .auto-memory を repo 内に配置し09-10の学びを記録 |

コミット後 `git status` はクリーン。

### aiseki / ai-english-coach

未コミット・未追跡ファイルなし。**コミットなし。**

---

## .gitignore に追加したパターン

**youtube-factory のみ 1件。**

```
# xlsx 書き出し途中の一時ファイル（生成し直せる）
*.xlsx.tmp
```

追加理由と、追加**しなかった**ものの判断:

- `reports/youtube_analysis_20260904.xlsx.tmp` が過去に誤って追跡されていたため、再発防止としてパターンを追加。既存の追跡分は `git rm --cached` すると次回 pull で消えるため、指示範囲外として**そのまま残した**（Mac 上で手動で外すとよい）。
- `data/scenarios/**`, `data/trends/**`, `data/channels_orchestrator/**`, `reports/**` は「自動生成物」に見えるが、リポジトリの既存慣習で全て追跡済み（例: 追跡中のシナリオ 783件・アーカイブ md 773件・trends 244件）。**慣習に合わせて ignore ではなくコミット**した。
- `.auto-memory/`（新規・2ファイル 10KB）は **ignore せずコミット**した。判断根拠: 追跡済みの `MEMORY_UPDATE_2026*.md` 群に「`~/.auto-memory/` が接続フォルダ外で書き込めない。恒久対応は接続フォルダに追加すること」と8日連続で書かれており、repo 内に置かれた `.auto-memory/` は代替ではなくメモリ本体そのもの。捨てると学びが失われる。
- aiseki / ai-english-coach は対象ファイルなしのため追加なし。

---

## 機密情報チェック

コミット対象 105 ファイル全件を以下のパターンでスキャン → **ヒット0件**。

`AIza…` / `sk-…` / `ya29.…` / `ghp_…` / `xox[baprs]-…` / `-----BEGIN … PRIVATE KEY` / `api_key|secret|password|token|client_secret` への16文字以上の代入

---

## Phase 3: push 結果

### youtube-factory — **push 失敗（認証情報なし）**

```
$ git push origin main
fatal: could not read Username for 'https://github.com': No such device or address
```

- 原因: Linux サンドボックスに GitHub 認証情報が存在しない。`credential.helper` 未設定、`~/.git-credentials` / `~/.netrc` / `~/.ssh` / `gh` CLI いずれもなし。Mac の Keychain はサンドボックスから参照できない。**09-10 03:44 の前回実行と同じ原因**（2回連続）。
- 状態: `main` は `origin/main` より **7コミット先行**（上表の6本＋本ログのコミット `59bc1df`）。ローカルにデータは全て保存済みで消失なし。
- **要対応（人手）**: `cd ~/Developer/youtube-factory && git push origin main`

### aiseki — **push 未実施（同じ認証情報の問題）**

- 作業ツリーはクリーン。`main` は `origin/main` より **4コミット先行**（今回より前からの未 push 分。最新 `1538169 docs: マーケ資料（DMテンプレ・SNSコンテンツ・競合分析）とインフルエンサーリスト生成スクリプトを追加`）。**2日連続で push できていない。**
- **要対応（人手）**: `cd ~/Developer/aiseki && git push origin main`

### ai-english-coach — **該当なし**

- remote が1つも設定されていない（`git remote -v` が空）。push 先なし。

---

## 環境上の注意（次回実行者向け）

1. **マウント上で `unlink` が禁止されている（前回と同じ）。**
   サンドボックスから `/Users/.../Developer` へは書き込み・rename はできるが**削除ができない**。git が `*.lock` や `.git/objects/*/tmp_obj_*` を消せず、残ったロックで以降の git 操作が全部失敗する。
   → 対処: 各 git コマンドの前後で `.git` 配下の `*.lock` を `*.lock.stale.<ns>` へ **mv して退避**するラッパ関数を使った。これで `git commit` も含め全操作が通った（前回のような配管コマンドへの退避は不要だった）。

2. **退避ファイルを `.git/refs/` 配下に残すと git が壊れる。**
   前回の退避で `refs/remotes/{origin,neworigin}/main.lock.stale.*` が10件残り、`fatal: bad object refs/remotes/neworigin/main.lock.stale.…` で `git gc` が毎回失敗していた。
   → 今回 `.git/_stale_junk/` へ移動して解消。**退避先は必ず `refs/` の外にすること。**

3. **手動で消してよいゴミ**（Mac 側で削除推奨。サンドボックスからは消せない）
   - `youtube-factory/.git/objects/*/tmp_obj_*` … 約 **540件**
   - `youtube-factory/.git/_stale_junk/` … 11件（旧 `gc.log` 含む）
   - `youtube-factory/.git/*.lock.stale.*` および `.git/**/*.lock.stale.*` … 57件
   - `youtube-factory/.git/{_writetest,_wtest,.git_write_test,.__perm_test}` などの疎通テスト残骸
   - `aiseki/.git/index.lock`, `ai-english-coach/.git/index.lock`（0バイト。git プロセスは動いていない）

4. **force push / `reset --hard` は一切実行していない。指示された3リポジトリ以外には触れていない。**
