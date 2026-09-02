# Daily Merge Log

**実行日時**: 2026-09-02 22:06 JST
**タスク**: daily-merge-all-projects
**結果サマリ**: マージ対象ブランチなし（全リポジトリ）。コンフリクトなし。

---

## 1. youtube-factory (`/Users/ayukiyamazaki/Developer/youtube-factory`)

- 現在のブランチ: `main`
- ローカルブランチ: `main` のみ
- リモートブランチ: `origin/main`, `neworigin/main`（いずれも main にマージ済み相当、未マージコミットなし）
- **マージしたブランチ**: なし（未マージブランチが存在しない）
- **コンフリクト**: なし
- **未コミット変更**: あり — 合計 **647 件**
  - 変更(modified): 523
  - 未追跡(untracked): 124
  - ステージ済み: 0
- 未プッシュコミット: origin/main より **9 コミット先行**

## 2. aiseki (`/Users/ayukiyamazaki/Developer/aiseki`)

- 現在のブランチ: `main`
- ローカルブランチ: `main` のみ
- リモートブランチ: `origin/main`, `neworigin/main`（未マージコミットなし）
- **マージしたブランチ**: なし
- **コンフリクト**: なし
- **未コミット変更**: あり — 合計 **24 件**（すべて未追跡ファイル）
  - デバッグ/E2E用スクリプト `.＊.mjs` 22件、xlsx 2件
- 未プッシュコミット: origin/main より **3 コミット先行**

## 3. ai-english-coach (`/Users/ayukiyamazaki/Developer/ai-english-coach`)

- 現在のブランチ: `main`
- ローカルブランチ: `main` のみ
- リモート: 設定なし（remote ブランチ無し）
- **マージしたブランチ**: なし
- **コンフリクト**: なし
- **未コミット変更**: あり — 合計 **1 件**（未追跡: `HANDOFF.md`）

---

## 注記 / 手動対応が必要な項目

- マージ操作は一切実行していない（対象が無かったため）。force push / reset --hard は未使用。
- youtube-factory の未コミット変更 647 件は規模が大きい。ブランチ作業を始める前に整理（コミット or .gitignore 追加）を推奨。data/ab_tests 配下の生成物が大半。
- youtube-factory と aiseki に未プッシュコミット（9 / 3）あり。push は本タスクの範囲外のため未実行。
- 対象3リポジトリ以外には一切アクセスしていない。
