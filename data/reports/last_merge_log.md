# 全プロジェクト マージ・整理ログ

**実行日時**: 2026-09-11 22:20 JST（scheduled task: daily-merge-all-projects）

---

## サマリ

| リポジトリ | マージ | コミット | push |
|---|---|---|---|
| youtube-factory | ❌ コンフリクト（手動対応が必要） | ✅ 6件 | ❌ 認証不可（origin/main に対し **15コミット先行**） |
| aiseki | 対象ブランチなし | 変更なし | ❌ 認証不可（origin/main に対し **4コミット先行**） |
| ai-english-coach | 対象なし（`_locktest` は main に取り込み済み） | 変更なし | リモート未設定のため push 不要 |

> **要対応が2つあります。** 下の「手動対応が必要な項目」を参照。

---

## Phase 1: マージ

### youtube-factory

- 未マージブランチ: `orch-20260911-followup`（main にない3コミット）
  - `8badac5` fix: effective_len が本文をハッシュタグとして落としていたのを直し、数値を再計算
  - `3ebbd2a` docs: 追補コミットの取り込み手順を .auto-memory に記録
  - `1460539` fix: 2ch-matome の min_effective_chars を再適用し、上書きの罠を記録
- **結果: コンフリクト発生。指示どおり強制マージせず中止（作業ツリーは無傷）。**
- コンフリクト箇所: `data/channels/2ch-matome.json` の `theme_queue`
  - followup 側: テーマ `81377fd7` を「ちいかわ寿司コラボ中止の裏事情とは？」→「ちいかわ寿司コラボが中止になった本当の理由」に改題（答え提示語が無くテストが赤になったため）
  - main 側: 同テーマは本日の自動run中にキューから消費済みで、エントリ自体が存在しない
  - つまり followup の改題は**すでに用済みの可能性が高い**が、判断は人間に委ねる
- 補足: followup のコード変更（`title_constraints.py` の effective_len 修正、テスト、`.auto-memory`、レポート）は**すでに作業ツリーに同一内容で存在**しており、今回のコミット af84e4a 等で main に入っている。未取り込みなのは `data/channels/*.json` の rationale 文面差分と上記キュー改題のみ。

### aiseki

- ブランチは `main` のみ。マージ対象なし。

### ai-english-coach

- ブランチ: `main`, `_locktest`
- `_locktest`（a90c4ad）は **main にすべて含まれている**（`git log main.._locktest` が空）。マージ不要。

---

## Phase 2: 整理・コミット

### youtube-factory（6コミット、計 103ファイル）

前回の中断により index が Sep 10 のまま固まっていたため、`git reset`（mixed。**--hard は未使用**）で staging をほどいてから内容ごとに分割してコミットした。

| コミット | メッセージ | 主な内容 |
|---|---|---|
| `af84e4a` | fix: effective_len がハッシュタグ判定で本文を落としていたのを修正し、タグ除去後の空白を畳む | `backend/pipeline/title_constraints.py`, `backend/tests/test_fixes_20260911.py` |
| `e1b23e5` | docs: .auto-memory に 09-11 の effective_len 修正と再計算の経緯を追記 | `.auto-memory/2026-09-11.md`, `INDEX.md` |
| `97a86d6` | レポート更新: 09-11 分析スクリプトの実効文字数集計を修正しxlsxを再生成 | `reports/make_youtube_analysis_20260911.py`, `.xlsx` |
| `b3ef95f` | 設定更新: 全チャンネルのタイトル制約・オリジナリティ・CTA履歴を09-11時点に同期 | `data/channels/` 8件, `data/originality/` 8件, `data/cta_history/` |
| `c71f770` | データ更新: クリップ取得・横断キーワード・バイラル取得の09-11分析結果を反映 | `data/analytics/` 4件 + `viral_translation_pending/` |
| `28e28fc` | テーマキュー追加: 全7チャンネルの新規シナリオと本日分アーカイブ・索引を更新 | `data/scenarios/` 全7ch（新規24 + 索引8） |

- **機密情報スキャン実施**: 対象全ファイルを APIキー / トークン / 秘密鍵パターンで走査。検出ゼロ。
- 作業ツリーは現在クリーン。

### aiseki / ai-english-coach

- どちらも未コミット・未追跡ファイルなし。コミット不要。

---

## .gitignore への追加

**今回の追加はなし。** 指示にあった `data/ab_tests/`・`*.audit.mjs` は youtube-factory の `.gitignore` に既に記載済み。他の未追跡ファイルはすべて追跡対象の成果物（シナリオ・分析JSON・レポート）で、除外すべき一時ファイルは見つからなかった。

---

## Phase 3: push

**3リポジトリとも push できていない。**

- youtube-factory / aiseki: `fatal: could not read Username for 'https://github.com'`
  - 実行環境（サンドボックス）に GitHub 認証情報がなく、credential.helper も未設定。ホスト側のキーチェーンに届かない。
  - コミット自体はローカルに正しく積まれているので、ホストのターミナルで `git push origin main` を叩けば同期される。
- ai-english-coach: リモート未設定（`git remote -v` が空）。push 対象外。

---

## 手動対応が必要な項目

1. **push（2件）** — ホストのターミナルで実行:
   ```
   cd ~/Developer/youtube-factory && git push origin main   # 15コミット
   cd ~/Developer/aiseki          && git push origin main   # 4コミット
   ```
2. **youtube-factory のマージコンフリクト** — `data/channels/2ch-matome.json` の theme_queue。
   followup 側の改題対象テーマは main 側で消費済みのため、`git merge orch-20260911-followup` 後に
   main 側（エントリ削除済みの状態）を採用するのが妥当に見える。rationale 文面の差分は followup 側が新しい。

---

## 環境上の注意（次回実行者向け）

- サンドボックスから見た `/Users/ayukiyamazaki/Developer/*` のマウントは **unlink（ファイル削除）が一切できない**。
  そのため git は以下の挙動になる:
  - `git add` / `git commit` / `git log` は動く（lock は rename で消費されるため）
  - `git status` は毎回 `.git/index.lock` を消せずに残す → 次の git 書き込みが「Another git process...」で失敗する
  - `git merge` / `git checkout` は**作業ツリーのファイルを差し替えられず必ず失敗する**（`error: unable to unlink old '...'`）
- 回避策として今回使ったもの:
  - 残った lock は `.git/stale_locks/` へ `mv` して退避（`rm` は EPERM）
  - マージ可否の判定は `/tmp` に `git clone -s` した作業用クローンで実施（ext4 なので正常に動く）
- `.git/stale_locks/`・`.git/_stale/` に退避済み lock が溜まっている。ホスト側で削除して構わない。
- force push / `reset --hard` は一切実行していない。他プロジェクトには触れていない。
