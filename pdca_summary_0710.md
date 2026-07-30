# PDCA日次レポート 2026-07-10

## チャンネル状況

| チャンネル | 登録者 | 増減 | 総再生 | 動画数 | 登録効率 |
|-----------|--------|------|--------|--------|---------|
| 日常科学 | 36人 | +1 | 100,553 | 103本 | 0.35人/本 |
| SCPラボ | 77人 | +3 | 69,594 | 75本 | 1.03人/本 |

## 完了事項

**テーマ重複制限** — generate()に類似度チェック(閾値0.8)を全経路追加。ブラックリストで飽和テーマ自動ブロック。反映済み。

## 未解決事項

1. **YouTube Analytics API 403** — 再生数が全て0。PDCAが機能していない
   - 確認URL: https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=844705815004

2. **Anthropic APIキー** — 末尾lQAAで credit balance too low
   - 確認先: https://console.anthropic.com
