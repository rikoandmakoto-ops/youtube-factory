# 画像フィードバックUI 実装レポート

## 実装した機能
サンプル画像とサムネイルの生成結果に対して、ユーザーがテキストで修正点を指示し、その内容を反映して再生成できるUIをフロントエンド／バックエンド両方に追加しました。

### バックエンド変更
- `backend/api_phase5.py`
  - `SampleRequest` / `ThumbnailGenerateRequest` に `feedback: Optional[List[str]]` を追加。古い→新しい順の修正指示履歴を受け取る。
  - `_build_feedback_block(...)` を追加。フィードバック履歴をDALL-Eプロンプトに「USER REVISION INSTRUCTIONS」として整形して挿入。
  - `SampleResponse` / `ThumbnailGenerateResponse` に `feedback: List[str]` を追加して履歴をエコーバック。
  - サムネ生成は `generate_thumbnail_async(..., feedback=...)` を呼ぶようにした。古いパイプラインに対する `TypeError` フォールバックも追加して後方互換を確保。
- `backend/pipeline/thumbnail_generator.py`
  - `design_brief(title, api_key, channel_meta=None, feedback=None)` を拡張。フィードバックがあれば GPT-4o のシステム/ユーザープロンプトに「ユーザーからの修正指示」ブロックとして注入し、最新指示を優先させる。
  - `generate_thumbnail` / `generate_thumbnail_async` 両方に `feedback` キーワード引数を追加して `design_brief` まで貫通。

### フロントエンド変更
- `frontend/src/lib/api.ts`
  - `SampleIllustrationRequest` / `SampleIllustrationResponse`、`ThumbnailGenerateRequest` / `ThumbnailGenerateResponse` に `feedback?: string[]` を追加。
- `frontend/src/app/generate/GenerateForm.tsx`
  - サンプル用に `sampleFeedback` / `sampleFeedbackDraft` のstateを追加。チャンネル/テーマが変わったら履歴をリセット。
  - `onGenerateSample(extraFeedback?, clearFeedback?)` に拡張。新しいフィードバックを履歴に積んで送信し、レスポンスで履歴を確定。
  - サンプル確認カードに以下を追加:
    - 修正履歴ブロック (`📝 修正履歴 (n回)` + 番号付きリスト + 履歴クリア)
    - 修正リクエスト テキストエリア (`textarea`)
    - 「✏️ 修正して再生成」ボタン (履歴に追加して再生成)
    - 「🔁 再生成（履歴維持）」/「✅ OK 進む」の2ボタン
  - サムネ用にも `thumbFeedback` / `thumbFeedbackDraft` を追加して同等のUIを実装。「✏️ 修正して文字だけ作り直す」/「✏️ 修正して背景ごと作り直す」の2系統に対応。
- `frontend/src/app/channels/new/NewChannelForm.tsx`
  - `/channels/new` ウィザードのStep3 (サンプル確認) にも同等のフィードバックUI／履歴／修正リクエスト欄を追加。

### 検証
- `python3 -c "import ast; ast.parse(...)"` で `api_phase5.py`, `thumbnail_generator.py` 構文OK
- `npx tsc --noEmit` 成功（型エラーなし）
- 既存の `.next` ビルド成果物は残存。サンドボックスのbashタイムアウト(45s)制限のため `next build` を完走させられなかったが、tscが通っているため型・構文レベルでは問題なし。

## 自動実行できなかったステップ（要マニュアル実行）

このタスクはスケジュール実行のためユーザー不在で動作しています。以下はホストOSの認証情報やGUI操作が必要なため、ユーザー側で実行してください:

1. **バックエンド再起動** (uvicornが `--reload` 付きで起動中なら自動的に変更を拾います。停止していた場合のみ):
   ```bash
   cd /Users/ayukiyamazaki/Developer/youtube-factory/backend
   python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
2. **フロントエンドの本番デプロイ** (Vercel CLIの認証情報がサンドボックスに無いため):
   ```bash
   cd /Users/ayukiyamazaki/Developer/youtube-factory/frontend
   vercel --prod --yes
   ```
3. **動作確認**:
   - `/generate` ページでチャンネル＋テーマを入れてサンプル生成 → テキストで「もっと明るい色で」など入力 →「✏️ 修正して再生成」を押す → 履歴が `1回` と表示されることを確認
   - 同じく `/generate` ページのサムネプレビューでも同じ流れを確認
   - `/channels/new` のStep3でも同じ流れを確認

## 変更ファイル一覧
- `backend/api_phase5.py`
- `backend/pipeline/thumbnail_generator.py`
- `frontend/src/lib/api.ts`
- `frontend/src/app/generate/GenerateForm.tsx`
- `frontend/src/app/channels/new/NewChannelForm.tsx`
