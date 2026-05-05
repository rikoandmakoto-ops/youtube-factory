#!/bin/bash
# ダブルクリックで動画生成（VOICEVOX対応）
cd "$(dirname "$0")"

echo "🎬 ゆっくり動画生成パイプライン"
echo "================================"

# Check Python deps
python3 -c "import PIL, moviepy, numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 依存パッケージをインストール中..."
    pip3 install Pillow moviepy numpy
fi

# Check VOICEVOX
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ VOICEVOX検出 → VOICEVOX音声で生成します"
else
    echo "⚠️  VOICEVOXが起動していません"
    echo "    VOICEVOXを起動してからもう一度実行するか、"
    echo "    このままMock TTSで続行します"
    echo ""
    echo "    続行しますか？ (y/n)"
    read -r ans
    if [ "$ans" != "y" ]; then
        echo "中止しました。VOICEVOXを起動してから再実行してください。"
        exit 1
    fi
fi

echo ""
python3 -m backend.pipeline.video_generator --type both "$@"

echo ""
echo "Press Enter to close..."
read
