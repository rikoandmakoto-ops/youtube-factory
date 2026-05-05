#!/bin/bash
# ジョブウォッチャー起動
# Claudeからの指示で自動的に動画生成されます
cd "$(dirname "$0")"

echo "👀 ゆっくり動画ジョブウォッチャー"
echo "================================"

# Check deps
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
    echo "⚠️  VOICEVOX未検出 → Mock TTSを使用します"
    echo "    VOICEVOXを起動すると次のジョブから自動で切り替わります"
fi

echo ""
python3 watcher.py
