# daily-merge-all-projects 実行ログ

**実行日時:** 2026-09-19 22:08 JST
**対象:** youtube-factory / aiseki / ai-english-coach

---

## サマリ

| リポジトリ | マージ | 新規コミット | push |
|---|---|---|---|
| youtube-factory | ⚠️ コンフリクトのため見送り（1ブランチ） | 6件 | ❌ 認証不可（12コミット未push） |
| aiseki | 対象ブランチなし | 1件 | ❌ 認証不可（5コミット未push） |
| ai-english-coach | ✅ 未マージなし（`_locktest` はマージ済み） | 0件（作業ツリー clean） | — remote 未設定 |

**ユーザー作業が必要なのは push だけです**（下の「手動で必要な作業」）。

---

## Phase 1: マージ

### youtube-factory — `orch-20260911-followup`（⚠️ 手動対応が必要）

`/tmp` に `git clone -s` した作業用クローンで試験マージした結果、**コンフリクト2件**。
指示どおり強制マージはせず、実リポジトリは一切触っていません（試験後 `merge --abort`）。

| ファイル | 状態 |
|---|---|
| `data/channels/2ch-matome.json` | CONFLICT（content） |
| `.auto-memory/INDEX.md` | CONFLICT（content） |
| 他13ファイル | 自動マージ可 |

**内容を読んだ所見（参考・判断はご本人で）**

このブランチは 09-11 のもので、3コミット分の修正のうち **実質的なコードはすでに main に取り込まれ済み**です。
マージ後に main と差が出るのは3ファイルだけでした。

- `2ch-matome.json` のコンフリクトは **テーマキューの中身と、その後 main 側で積み上げた知見の衝突**です。
  main 側には 09-14 のタイトル型実測、09-17 のマーカー変更、`min_effective_chars` の
  `hard_constraints` 移行など **09-11 より新しい設定**が入っています。ブランチ側を採ると
  それらを踏み戻す可能性があります。
- `.auto-memory/INDEX.md` も同様で、main 側の記述のほうが新しく詳細です
  （例: 「09-12 に config 上書き事故は止まった」がブランチ側には無い）。

→ **ブランチを捨てて問題ない可能性が高い**と見ています。残したい差分は
`akashic-librarian.json` の1行と、`INDEX.md` / `2ch-matome.json` の追記くらいです。
判断がついたら Mac 側で次のどちらか:

```bash
cd ~/Developer/youtube-factory
git branch -D orch-20260911-followup            # 捨てる場合
# もしくは差分を見てから:
git diff main...orch-20260911-followup -- data/channels/2ch-matome.json .auto-memory/INDEX.md
```

### aiseki

未マージブランチなし（`main` のみ）。

### ai-english-coach

`_locktest` は `main` にマージ済み（`git branch --merged main` で確認）。作業なし。

---

## Phase 2: 整理・コミット

### youtube-factory（6コミット / 61ファイル）

| コミット | メッセージ | 規模 |
|---|---|---|
| `e9cb092` | chore(config): 09-19 指揮者のチャンネル設定更新（冒頭重複対策の禁止語・2ch-matome エンハンサー停止） | 5 files, +58 −61 |
| `f68b3f7` | chore(data): 09-19 の分析・独自性・ファクト台帳・シリーズリンクを同期 | 14 files, +641 −556 |
| `bb76558` | chore(scenarios): 09-19 生成分のシナリオとアーカイブ索引を追加 | 36 files, +7972 |
| `2982c19` | chore(trends): 09-19 の Google/YouTube トレンド取得結果を追加 | 2 files, +230 |
| `fa9cdd7` | docs: 09-19 指揮者メモ・Mac実行スクリプト・分析xlsx を追加 | 3 files, +382 |
| `422c3b6` | chore(gitignore): サンドボックスの書き込み検証用ファイル `.__deltest` を無視 | 1 file, +2 |

コミット後の作業ツリーは clean。

### aiseki（1コミット）

| コミット | メッセージ | 規模 |
|---|---|---|
| `7053d29` | docs(marketing): アフィリエイト座組を課金トリガー版で追加 | 1 file（135行） |

`marketing_*.md` は既に4本追跡されているため、先例どおり追跡対象としました。

### ai-english-coach

未コミット・未追跡ファイルなし。

---

## .gitignore に追加したパターン

| リポジトリ | 追加 | 理由 |
|---|---|---|
| youtube-factory | `.__deltest` | サンドボックスの削除可否を調べる使い捨てファイル。このマウントでは削除できず残るため（既存の `.__perm_test` と同枠） |
| aiseki | なし | — |
| ai-english-coach | なし | — |

`data/ab_tests/` と `*.audit.mjs` は **既に3リポジトリとも設定済み**だったため追加不要でした。
今日の未追跡ファイルはいずれも生成物ではなく、`data/scenarios/` `data/trends/` `reports/*.xlsx`
`MEMORY_UPDATE_*.md` `*.command` すべて **既存の追跡実績（同パターンが数百件）がある**ので追跡しています。

---

## 機密情報チェック

コミット対象の全ファイルを `AIza…` / `sk-…` / `ghp_…` / `xoxb-` / PRIVATE KEY / `client_secret`
/ `refresh_token` / `api_key` のパターンで走査。**検出ゼロ**。

`restart_and_trigger_20260919.command` は localhost:8000 への curl のみで、認証情報は含みません。

---

## push 結果 ❌

| リポジトリ | 結果 |
|---|---|
| youtube-factory → origin | `could not read Username for 'https://github.com'` |
| aiseki → origin | 同上 |
| ai-english-coach | remote 未設定のため対象外 |

このタスクは Linux サンドボックス上で動作しており、GitHub 認証情報は macOS キーチェーン側に
あるため参照できません。**昨日と同じ状況で、構造的にサンドボックスからは push できません。**

---

## 手動で必要な作業

```bash
# 1. push（Mac のターミナルで）
cd ~/Developer/youtube-factory && git push origin main   # 12コミット
cd ~/Developer/aiseki          && git push origin main   #  5コミット
```

> ⚠️ 昨日のログには「origin(zaki21016) が 404 相当で、実体は neworigin(rikoandmakoto-ops)」
> という記録がありました。`git push origin main` が Repository not found になる場合は
> `git push neworigin main`、恒久的に切り替えるなら `git branch -u neworigin/main main` を。

```bash
# 2. .git 内のゴミ掃除（サンドボックスからは削除できません）
cd ~/Developer/youtube-factory  && rm -rf .git/_stale .git/stale_locks && git prune && git gc --prune=now
cd ~/Developer/aiseki           && rm -rf .git/_stale && git gc --prune=now
cd ~/Developer/ai-english-coach && rm -rf .git/_stale
```

現在の残量: youtube-factory `tmp_obj_*` 618件 / `_stale` 33件 / `stale_locks` 88件、
aiseki `tmp_obj_*` 26件 / `_stale` 2件、ai-english-coach `_stale` 1件。
**リポジトリの整合性には影響しません**（git は rename でオブジェクトを確定させており、
消せないのは確定後の一時ファイルだけです）。

```bash
# 3. 判断が必要（上記 Phase 1 参照）
cd ~/Developer/youtube-factory && git diff main...orch-20260911-followup
```

---

## 環境上の制約（既知・変化なし）

1. **`/Users/ayukiyamazaki/Developer/*` のマウントは unlink が一切できません**（EPERM）。
   帰結として `git status` は毎回 `.git/index.lock` を、`git commit` は `.git/HEAD.lock` を残します。
   - 今回は **`GIT_INDEX_FILE=/tmp/…` で別インデックスを使い、各 git コマンドの前に
     残留ロックを `.git/_stale/` へ rename して退避**する手順でコミットを通しました。
     退避前に git プロセスが動いていないことを確認済みです。
   - `git merge` / `git checkout` はこの環境では原理的に失敗するため、**マージ可否の判定は
     `/tmp` への `git clone -s`（ext4）で行いました**。今回マージを見送った理由は
     コンフリクトであって、この制約ではありません。
2. **push はサンドボックスから不可**（認証情報がキーチェーン側）。
3. **youtube-factory は稼働中**です。作業中も別プロセスが `data/` を書き換えるため、
   `git add -A` は毎回パスを明示して限定しています。

---

## 遵守事項の確認

- ✅ 対象3リポジトリ以外には一切触れていません。
- ✅ `git push --force` / `git reset --hard` は使用していません。
- ✅ コンフリクトのあるマージは強制せず、報告に留めました。
- ✅ 機密情報を含むファイルはコミットしていません。
- ✅ `.git/index.lock` の退避は、git プロセス不在を確認したうえで削除ではなく rename で行いました。
