#!/bin/bash
# SCP-035 ショート動画生成 → YouTube投稿
cd "$(dirname "$0")/backend"

echo "========================================="
echo "🎬 SCP-035 ショート動画生成・投稿"
echo "========================================="
echo ""

# VOICEVOX確認
VOICEVOX_OK=$(curl -s --max-time 3 http://localhost:50021/version 2>/dev/null)
if [ -z "$VOICEVOX_OK" ]; then
    echo "⚠️  VOICEVOX未起動 — 起動します..."
    open -a VOICEVOX
    echo "VOICEVOX起動待ち(最大60秒)..."
    for i in $(seq 1 60); do
        VOICEVOX_OK=$(curl -s --max-time 2 http://localhost:50021/version 2>/dev/null)
        if [ -n "$VOICEVOX_OK" ]; then
            echo "✅ VOICEVOX起動完了: $VOICEVOX_OK"
            break
        fi
        sleep 1
    done
    if [ -z "$VOICEVOX_OK" ]; then
        echo "❌ VOICEVOX起動失敗"
        echo "Press Enter to close..."
        read
        exit 1
    fi
else
    echo "✅ VOICEVOX起動済み: $VOICEVOX_OK"
fi

echo ""
echo ">>> シナリオ生成 → 動画生成 → YouTube投稿"
echo ""

export SHORT_THEME_TITLE="SCP-035に装着された7人の研究員が全員別人格になった——財団が仮面を絶対に破壊しない本当の理由"
export SHORT_THEME_ANGLE="SCP-035（取り憑く仮面）の個別オブジェクト解説。装着者を支配する仮面の恐怖と財団が破壊を選ばない真の理由。数字入り断定調。30秒ショート。"
export SHORT_TARGET_SEC=30
export SHORT_PRIVACY=public

python3 run_scp_short_upload.py 2>&1 | tee "../logs/scp035_short_$(date +%Y%m%d_%H%M%S).log"
EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 完了！"
else
    echo "❌ エラー (exit code: $EXIT_CODE)"
fi
echo "========================================="
echo ""
echo "Press Enter to close..."
read
