#!/bin/bash
# ゆっくりポケラボ — ショート動画1本生成 → YouTube投稿
cd "$(dirname "$0")"

echo "🎬 ゆっくりポケラボ ショート動画生成 → YouTube投稿"
echo "=================================================="

# Check Python deps
python3 -c "import PIL, moviepy, numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 依存パッケージをインストール中..."
    pip3 install Pillow moviepy numpy
fi

# Check VOICEVOX
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ VOICEVOX検出"
else
    echo "⚠️  VOICEVOXが起動していません。起動中..."
    open -a VOICEVOX
    echo "   VOICEVOXの起動を待っています (最大60秒)..."
    for i in $(seq 1 30); do
        sleep 2
        python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "   ✅ VOICEVOX起動完了"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "   ❌ VOICEVOXが起動しませんでした。手動で起動してからやり直してください。"
            echo "Press Enter to close..."
            read
            exit 1
        fi
    done
fi

echo ""
echo "📺 pokemon-lab ショート動画パイプライン開始..."
python3 backend/run_pokemon_short_upload.py

echo ""
echo "Press Enter to close..."
read
