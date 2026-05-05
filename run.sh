#!/bin/bash
# YouTube Factory — マルチチャンネル自動動画生成
# Usage:
#   ./run.sh              → ファクトリーサーバー起動
#   ./run.sh generate     → ショート＋メイン両方生成して終了
#   ./run.sh generate --type short → ショートのみ
#   ./run.sh generate --bg-type static → 静的背景で生成
#   ./run.sh generate --bg-type video  → 動的（動画）背景で生成

cd "$(dirname "$0")"

# Check dependencies
python3 -c "import PIL, moviepy, numpy, fastapi, uvicorn" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 依存パッケージをインストール中..."
    pip3 install -r backend/requirements.txt
    pip3 install Pillow moviepy numpy
fi

# Check VOICEVOX
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ VOICEVOX検出"
else
    echo "⚠️  VOICEVOX未検出 → Mock TTSを使用"
fi

if [ "$1" = "generate" ]; then
    shift
    echo "🎬 動画生成開始..."
    python3 -m backend.pipeline.video_generator "$@"
else
    echo "🏭 YouTube Factory 起動���... http://localhost:8000"
    echo "   マルチチャンネル自動動画生成プラットフ���ーム"
    echo "   停止: Ctrl+C"
    cd backend
    python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
fi
