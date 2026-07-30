#!/bin/bash
# YouTube Factory Backend — 再起動スクリプト
# nohup でバックグラウンド実行、ログは logs/backend.log に出力
# --reload なし（ジョブが死ぬため）

cd "$(dirname "$0")/backend"

# 既存プロセスの停止
echo "🔍 既存のuvicornプロセスを確認中..."
PIDS=$(pgrep -f "uvicorn main:app" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "⏹ 既存プロセスを停止中 (PID: $PIDS)..."
    kill $PIDS 2>/dev/null
    sleep 2
    # まだ生きていたら強制終了
    PIDS=$(pgrep -f "uvicorn main:app" 2>/dev/null)
    if [ -n "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
    echo "✅ 停止完了"
else
    echo "ℹ️  実行中のプロセスなし"
fi

# ログディレクトリ確保
mkdir -p ../logs

echo ""
echo "🚀 バックエンドを起動中..."
echo "   --reload なし（ジョブ保護のため）"
echo "   ログ: $(cd .. && pwd)/logs/backend.log"
echo ""

# 起動（--reload なし、nohup でバックグラウンド）
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 >> ../logs/backend.log 2>&1 &
NEW_PID=$!
echo "✅ 起動完了 (PID: $NEW_PID)"

# 8秒待って起動確認
echo "⏳ 起動確認中 (8秒待機)..."
sleep 8
if kill -0 $NEW_PID 2>/dev/null; then
    echo ""
    echo "🏭 YouTube Factory is running!"
    echo ""
    # ヘルスチェック
    HEALTH=$(curl -s --max-time 10 http://localhost:8000/health 2>/dev/null)
    if [ -n "$HEALTH" ]; then
        echo "📊 ヘルスチェック結果:"
        echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
    else
        echo "⚠️ ヘルスチェック応答なし（起動に時間がかかっている可能性）"
    fi
else
    echo "❌ 起動失敗。ログを確認してください:"
    tail -20 ../logs/backend.log
fi

echo ""
echo "このウィンドウは閉じて構いません。サーバーはバックグラウンドで動き続けます。"
echo "Press Enter to close..."
read
