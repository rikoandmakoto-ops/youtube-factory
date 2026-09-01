#!/bin/bash
# サムネイル修正 — バックエンド再起動 + 診断
cd "$(dirname "$0")"

echo "=== サムネイル修正 ==="
echo ""

# 1. バックエンドを再起動
echo "1. バックエンド再起動中..."
pkill -f "uvicorn.*main:app" 2>/dev/null || true
sleep 2

cd backend
nohup python3 -c "
import uvicorn
from main import app
uvicorn.run(app, host='0.0.0.0', port=8000)
" > /tmp/yt-factory-restart.log 2>&1 &
cd ..

echo "   バックエンド再起動完了（ポート8000）"
echo ""

# APIが立ち上がるまで待機
echo "2. API起動待機中..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "   API起動確認OK"
    break
  fi
  sleep 1
done
echo ""

# 3. ログイントークン取得
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"factory2024"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

if [ -z "$TOKEN" ]; then
  echo "❌ ログイン失敗"
  read -p "Press Enter to close..."
  exit 1
fi
echo "3. ログイン成功"
echo ""

# 4. thumbnail-test: ショート動画 r2UB_4Xr-1c にテストサムネイルをアップロード
echo "4. ショート動画のサムネイルテスト (video: r2UB_4Xr-1c)..."
RESULT=$(curl -s -X POST "http://localhost:8000/api/youtube/thumbnail-test/daily-science/r2UB_4Xr-1c" \
  -H "Authorization: Bearer $TOKEN")
echo "   結果: $RESULT"
echo ""

# 5. 結果判定
SUCCESS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)
if [ "$SUCCESS" = "True" ]; then
  echo "✅ ショート動画へのサムネイルアップロード成功！"
  echo "   → thumbnails().set() はショートでも動作します"
  echo ""
  echo "   次に、実際のサムネイルをリトライアップロード..."
  # thumbnail-retry で実際のサムネイルを再アップ
  RETRY=$(curl -s -X POST "http://localhost:8000/api/youtube/thumbnail-retry/daily-science/r2UB_4Xr-1c" \
    -H "Authorization: Bearer $TOKEN")
  echo "   リトライ結果: $RETRY"
else
  echo "❌ ショート動画へのサムネイルアップロード失敗"
  ERROR=$(echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('diagnosis',''), r.get('error',''))" 2>/dev/null)
  echo "   エラー: $ERROR"
fi

echo ""
echo "=== 診断完了 ==="
echo ""
echo "ログ確認: tail -f /tmp/yt-factory-restart.log"
read -p "Press Enter to close..."
