# YouTube Analytics API 有効化手順

## 現状

YouTube Factory の PDCA レポートで動画別の再生数・CTR・維持率が全て0になっている。原因は Google Cloud プロジェクト `844705815004` で YouTube Analytics API が無効のため。

YouTube Data API v3（動画一覧・登録者数の取得）は有効で正常動作中。Analytics API は別のAPIなので個別に有効化が必要。

## 手順

### 1. Google Cloud Console にアクセス

以下のURLを開く（プロジェクト指定済み）:

https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=844705815004

### 2. プロジェクトの確認

ページ上部のプロジェクト名が自分のプロジェクトか確認。プロジェクト番号が `844705815004` であること。

### 3. APIを有効化

- 「有効にする」ボタンが表示されていたらクリック
- 既に「有効」と表示されていれば対応不要（反映に数分かかる場合がある）

### 4. YouTube Reporting API も確認（任意）

維持率データの取得に必要な場合がある:

https://console.developers.google.com/apis/api/youtubereporting.googleapis.com/overview?project=844705815004

### 5. 反映確認

有効化後、5〜10分待ってからバックエンドで確認:

```bash
cd ~/Developer/youtube-factory/backend
# バックエンド再起動
kill $(lsof -ti:8000) 2>/dev/null; sleep 2
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > /tmp/uvicorn_restart.log 2>&1 &

# 30秒待ってからsync実行
sleep 30
curl -s -X POST http://localhost:8000/api/analytics/sync/daily-science | python3 -m json.tool
```

レスポンスに `"views": 数値` が含まれていれば成功。`403` や `accessNotConfigured` が出たらまだ反映されていない。

### 6. PDCAレポート再実行

```bash
cd ~/Developer/youtube-factory/backend
python3 run_daily_pdca.py
```

`data/reports/latest.md` に再生数・CTRが入ったレポートが出力される。

## 補足: Anthropic API キーの確認

シナリオ生成・コメント分析で「credit balance too low」エラーが出ている場合:

1. https://console.anthropic.com にアクセス
2. 左メニューの「API Keys」で末尾「lQAA」のキーを探す
3. そのキーが属する Organization にクレジットがあるか確認
4. Workspace の spend limit が設定されていないか確認
5. 別組織のキーだった場合、クレジットのある組織で新キーを発行して `backend/.env` の `ANTHROPIC_API_KEY` を差し替え
