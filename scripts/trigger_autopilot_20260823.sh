#!/usr/bin/env bash
# 制作指示（Phase 4） 2026-08-23
#
# 指揮者はサンドボックスLinux上で動作しており、Mac上の localhost:8000 に到達できない。
# 本日(日曜)の autopilot 枠は下記の通りで、いずれも本スクリプト作成時点より後に発火するため、
# 更新済みコンフィグ（新タイトル規則・新テーマキュー）は自動的に反映される。
#   scp-lab       13:00 / 19:00
#   daily-science 13:00
#   yokai-watch   12:00
#   pokemon-lab   12:00
#   2ch-matome    12:00
#   company-facts 14:00
#   clip-lab      停止（2026-08-23に enabled=false へ変更）
#
# 即時に走らせたい場合のみ、Mac のターミナルで本スクリプトを実行する。
set -uo pipefail
API="http://localhost:8000"

if ! curl -sf -m 5 "${API}/docs" >/dev/null 2>&1; then
  echo "!! バックエンド ${API} に到達できません。restart_backend.command を先に実行してください。"
  exit 1
fi

for ch in daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts; do
  echo "--- ${ch} ---"
  curl -sS -X POST "${API}/api/autopilot/${ch}/trigger" \
    -H 'Content-Type: application/json' -m 30 \
    && echo "" || echo "  失敗: ${ch}"
  sleep 2
done

echo
echo "clip-lab と akashic-librarian は運用方針によりスキップ（clip-lab は本日 autopilot を停止）"
