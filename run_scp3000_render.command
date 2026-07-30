#!/bin/bash
# SCP-3000 動画レンダリング（事前生成済みシナリオから実行）
cd "$(dirname "$0")"

echo "=== SCP-3000 動画レンダリング ==="
echo ""

# Check VOICEVOX
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "VOICEVOX: OK"
else
    echo "VOICEVOX が起動していません。起動してから再実行してください。"
    echo ""
    echo "Press Enter to close..."
    read
    exit 1
fi

echo ""
cd backend
python3 run_scp3000_from_scenario.py 2>&1 | tee /tmp/scp3000_render.log

echo ""
echo "=== 完了 ==="
echo "Press Enter to close..."
read
