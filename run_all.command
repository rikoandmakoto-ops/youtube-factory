#!/bin/bash
cd "$(dirname "$0")"

echo "=== 1. Git コミット ==="
rm -f .git/index.lock
git add data/channels/daily-science.json data/channels/scp-lab.json
git commit -m "PDCAレポート提案: スケジュール変更 & ブロックリスト追加"
echo ""

echo "=== 2. SCP-3000 レンダリング ==="
cd backend
python3 run_scp3000_from_scenario.py

echo ""
echo "=== 完了 ==="
read -p "Enterで閉じる..."
