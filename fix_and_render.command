#!/bin/bash
# Claude分析有効化 + SCP-3000長尺レンダリング
cd "$(dirname "$0")"

echo "========================================="
echo "  1. anthropic SDK インストール確認"
echo "========================================="
python3 -c "from anthropic import Anthropic; print('✅ anthropic SDK OK')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 anthropic SDK をインストール中..."
    pip3 install anthropic
    echo ""
fi

echo ""
echo "========================================="
echo "  2. ANTHROPIC_API_KEY 確認"
echo "========================================="
source backend/.env 2>/dev/null
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "✅ ANTHROPIC_API_KEY 設定済み (${#ANTHROPIC_API_KEY}文字)"
else
    echo "❌ ANTHROPIC_API_KEY が未設定です"
    echo "   backend/.env に以下を追加してください:"
    echo '   ANTHROPIC_API_KEY=sk-ant-api03-xxxxx'
    echo ""
    read -p "Enterで続行（レンダリングのみ実行）..."
fi

echo ""
echo "========================================="
echo "  3. VOICEVOX 疎通確認"
echo "========================================="
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=3)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ VOICEVOX OK"
else
    echo "❌ VOICEVOXが起動していません"
    echo "   VOICEVOXを起動してからもう一度実行してください"
    read -p "Enterで閉じる..."
    exit 1
fi

echo ""
echo "========================================="
echo "  4. SCP-3000 長尺レンダリング開始"
echo "========================================="
echo "60行のシナリオを動画化します（10-20分かかります）"
echo ""
cd backend
python3 run_scp3000_from_scenario.py

echo ""
echo "========================================="
echo "  完了！"
echo "========================================="
read -p "Enterで閉じる..."
