#!/bin/bash
# ============================================================
#  YouTube Factory — バックエンド再起動（Finderダブルクリック用）
#  既存の uvicorn を停止 → バックグラウンドで起動 → 起動確認
#  ログ: logs/backend.log
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_FILE="$PROJECT_DIR/logs/backend.log"

echo ""
echo "🏭 YouTube Factory — バックエンド再起動"
echo "============================================"
echo "📁 $PROJECT_DIR"
echo ""

# --- 既存プロセスの停止 ---------------------------------------------------
# このプロジェクト配下で動いている uvicorn だけを対象にする
# （他プロジェクトの uvicorn は絶対に落とさない）
find_pids() {
    local found=""
    for pid in $(pgrep -f "uvicorn main:app" 2>/dev/null); do
        local cwd
        cwd=$(lsof -a -d cwd -p "$pid" -Fn 2>/dev/null | grep '^n' | cut -c2-)
        case "$cwd" in
            "$PROJECT_DIR"|"$PROJECT_DIR"/*) found="$found $pid" ;;
        esac
    done
    echo $found
}

echo "🔍 既存のバックエンドを確認中..."
PIDS=$(find_pids)
if [ -n "$PIDS" ]; then
    echo "⏹  停止中 (PID:$PIDS)..."
    kill $PIDS 2>/dev/null
    sleep 2
    PIDS=$(find_pids)
    if [ -n "$PIDS" ]; then
        echo "   応答がないため強制終了 (PID:$PIDS)"
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
    echo "✅ 停止しました"
else
    echo "ℹ️  実行中のバックエンドはありません"
fi

# --- 起動 -----------------------------------------------------------------
mkdir -p "$PROJECT_DIR/logs"

echo ""
echo "🚀 バックエンドを起動中..."
cd "$BACKEND_DIR" || { echo "❌ backend フォルダが見つかりません"; echo ""; read -n 1 -s -r -p "何かキーを押すと閉じます..."; exit 1; }

# --reload なし（動画生成ジョブが途中で死ぬため）
nohup python3 -u -m uvicorn main:app --host 0.0.0.0 --port 8000 >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
disown 2>/dev/null

# --- 起動確認（最大30秒待つ）-----------------------------------------------
echo "⏳ 起動を待っています..."
OK=""
for i in $(seq 1 30); do
    sleep 1
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        break
    fi
    if curl -s -m 2 http://localhost:8000/health >/dev/null 2>&1; then
        OK="yes"
        break
    fi
done

echo ""
if [ -n "$OK" ]; then
    echo "============================================"
    echo "✅ 起動しました！(PID: $NEW_PID)"
    echo "   ダッシュボード: http://localhost:3000"
    echo "   API:            http://localhost:8000"
    echo "============================================"
elif kill -0 "$NEW_PID" 2>/dev/null; then
    echo "============================================"
    echo "⚠️  プロセスは動いていますが、応答がまだありません (PID: $NEW_PID)"
    echo "   数十秒待ってから http://localhost:3000 を開いてください"
    echo "============================================"
else
    echo "============================================"
    echo "❌ 起動に失敗しました。ログの最後を表示します:"
    echo "--------------------------------------------"
    tail -20 "$LOG_FILE"
    echo "============================================"
fi

echo ""
echo "📄 ログ: $LOG_FILE"
echo ""
read -n 1 -s -r -p "何かキーを押すとこのウィンドウを閉じられます..."
echo ""
