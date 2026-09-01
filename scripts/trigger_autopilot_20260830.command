#!/bin/bash
# 2026-08-30 指揮者 Phase 4: moviepy系6chへの制作指示
#
# 指揮者はサンドボックスVM上で動作しており、Macの localhost:8000 に到達できないため
# このスクリプトを生成した。Finderからダブルクリック、または以下で実行:
#   bash scripts/trigger_autopilot_20260830.command
#
# 前提: バックエンドが起動していること（restart_backend.command）
# 注意: clip-lab（凍結中）と akashic-librarian（OAuth未連携）は対象外。

set -u
BASE="http://localhost:8000"
CHANNELS=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "=== バックエンド疎通確認 ==="
if ! curl -sS -m 5 -o /dev/null "$BASE/docs" 2>/dev/null; then
  echo "❌ $BASE に接続できません。先にバックエンドを起動してください。"
  echo "   ./restart_backend.command"
  exit 1
fi
echo "✅ 疎通OK"
echo

ok=0; ng=0
for ch in "${CHANNELS[@]}"; do
  printf "%-15s " "$ch"
  code=$(curl -sS -m 120 -X POST -o /tmp/autopilot_$ch.json \
         -w "%{http_code}" "$BASE/api/autopilot/$ch/trigger" 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo "✅ $code  $(head -c 160 /tmp/autopilot_$ch.json)"
    ok=$((ok+1))
  else
    echo "❌ $code  $(head -c 160 /tmp/autopilot_$ch.json 2>/dev/null)"
    ng=$((ng+1))
  fi
done

echo
echo "=== 結果: 成功 $ok / 失敗 $ng ==="
echo
echo "生成後、以下のログで新しい尺強制が効いているか確認してください:"
echo "  '✂️ ShortsLengthGuard' の行が出ていれば Phase L が作動しています。"
echo "  期待値: 各chの台本が total_chars_max（165〜225字）以下に収まること。"
