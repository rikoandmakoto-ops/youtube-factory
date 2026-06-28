#!/bin/bash
# ========================================
# YouTube Factory - ショート動画生成スクリプト
# 両チャンネル (daily-science, scp-lab) 対応
# ========================================

cd "$(dirname "$0")"
LOG_FILE="short_gen_$(date +%Y%m%d_%H%M%S).log"
DONE_MARKER="../.short_gen_done"
RESULT_MARKER="../.short_gen_result"

# Remove old markers
rm -f "$DONE_MARKER" "$RESULT_MARKER"

echo "========================================" | tee "$LOG_FILE"
echo "ショート動画生成開始: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Step 1: Check VOICEVOX
echo "" | tee -a "$LOG_FILE"
echo ">>> Step 1: VOICEVOX確認" | tee -a "$LOG_FILE"
VOICEVOX_OK=$(curl -s --max-time 3 http://localhost:50021/version 2>/dev/null)
if [ -z "$VOICEVOX_OK" ]; then
    echo "VOICEVOX未起動 — 起動します..." | tee -a "$LOG_FILE"
    open -a VOICEVOX
    echo "VOICEVOX起動待ち(最大60秒)..." | tee -a "$LOG_FILE"
    for i in $(seq 1 60); do
        VOICEVOX_OK=$(curl -s --max-time 2 http://localhost:50021/version 2>/dev/null)
        if [ -n "$VOICEVOX_OK" ]; then
            echo "VOICEVOX起動完了: $VOICEVOX_OK" | tee -a "$LOG_FILE"
            break
        fi
        sleep 1
    done
    if [ -z "$VOICEVOX_OK" ]; then
        echo "ERROR: VOICEVOX起動失敗" | tee -a "$LOG_FILE"
        echo "VOICEVOX_FAIL" > "$DONE_MARKER"
        exit 1
    fi
else
    echo "VOICEVOX起動済み: $VOICEVOX_OK" | tee -a "$LOG_FILE"
fi

# Step 2: Start backend
echo "" | tee -a "$LOG_FILE"
echo ">>> Step 2: バックエンド起動" | tee -a "$LOG_FILE"

# Kill any existing backend
pkill -f "python3 main.py" 2>/dev/null
sleep 1

python3 main.py >> "$LOG_FILE" 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID" | tee -a "$LOG_FILE"

# Wait for health check
echo "Health check待ち(最大30秒)..." | tee -a "$LOG_FILE"
for i in $(seq 1 30); do
    HEALTH=$(curl -s --max-time 2 http://localhost:8000/health 2>/dev/null)
    if [ -n "$HEALTH" ]; then
        echo "Backend起動完了: $HEALTH" | tee -a "$LOG_FILE"
        break
    fi
    sleep 1
done

# Verify channels loaded
echo "" | tee -a "$LOG_FILE"
echo ">>> チャンネル確認" | tee -a "$LOG_FILE"
CHANNELS=$(curl -s http://localhost:8000/api/channels 2>/dev/null)
echo "Channels response: $CHANNELS" | tee -a "$LOG_FILE"

# Step 3: Run short generation
echo "" | tee -a "$LOG_FILE"
echo ">>> Step 3: ショート動画生成実行" | tee -a "$LOG_FILE"
echo "python3 run_short_only.py 開始: $(date)" | tee -a "$LOG_FILE"

python3 run_short_only.py 2>&1 | tee -a "$LOG_FILE"
GEN_EXIT=$?

echo "" | tee -a "$LOG_FILE"
echo ">>> 生成完了 (exit code: $GEN_EXIT): $(date)" | tee -a "$LOG_FILE"

# Find the latest result file
LATEST_RESULT=$(ls -t short_only_results_*.json 2>/dev/null | head -1)
if [ -n "$LATEST_RESULT" ]; then
    echo "結果ファイル: $LATEST_RESULT" | tee -a "$LOG_FILE"
    cp "$LATEST_RESULT" "$RESULT_MARKER"
    cat "$LATEST_RESULT" >> "$LOG_FILE"
else
    echo "結果ファイルが見つかりません" | tee -a "$LOG_FILE"
fi

# Step 4: Stop backend
echo "" | tee -a "$LOG_FILE"
echo ">>> Step 4: バックエンド停止" | tee -a "$LOG_FILE"
kill $BACKEND_PID 2>/dev/null
echo "Backend停止済み" | tee -a "$LOG_FILE"

echo "DONE" > "$DONE_MARKER"
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "全処理完了: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo ""
echo "このウィンドウは閉じて構いません。"
