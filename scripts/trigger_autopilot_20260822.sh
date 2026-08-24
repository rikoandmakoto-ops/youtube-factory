#!/bin/bash
# 指揮者 Phase4: moviepy系6chへの制作指示
# 生成日: 2026-08-22
# 注: 指揮者はサンドボックス実行のため localhost:8000 に到達できない。
#     autopilot は enabled=true + APScheduler で自走するため通常は不要だが、
#     本日分を即時実行したい場合はこのスクリプトをローカルで実行する。
#   使い方: bash scripts/trigger_autopilot_20260822.sh

set -u
BASE="http://localhost:8000"

# clip-lab（凍結中）と akashic-librarian（OAuth未連携）は対象外
CHANNELS=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

if ! curl -s -m 5 "${BASE}/api/health" > /dev/null 2>&1; then
  echo "✗ バックエンドが起動していません: ${BASE}"
  echo "  先に ./restart_backend.sh を実行してください。"
  exit 1
fi

echo "✓ バックエンド疎通OK"
echo

for ch in "${CHANNELS[@]}"; do
  printf '%-16s ' "$ch"
  code=$(curl -s -o /tmp/trig_out.txt -w '%{http_code}' -m 120 \
    -X POST "${BASE}/api/autopilot/${ch}/trigger")
  if [ "$code" = "200" ]; then
    echo "OK (200)"
  else
    echo "NG (${code}) -> $(head -c 300 /tmp/trig_out.txt)"
  fi
done

echo
echo "完了。ログ: logs/ を確認してください。"
