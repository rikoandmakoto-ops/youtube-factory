#!/bin/bash
# APIサーバー起動（VOICEVOX対応）
# 起動後、Claudeからの指示で動画生成が可能になります
cd "$(dirname "$0")"

echo "🚀 ゆっくり動画生成APIサーバー"
echo "================================"

# Check Python deps
python3 -c "import fastapi, uvicorn, PIL, moviepy, numpy" 2>/dev/null
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
    echo "⚠️  VOICEVOXが起動していません → Mock TTSになります"
fi

echo ""
echo "📡 サーバー起動中... http://localhost:8000"
echo "   Claudeから動画生成を指示できます"
echo "   停止するには Ctrl+C"
echo ""

cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
