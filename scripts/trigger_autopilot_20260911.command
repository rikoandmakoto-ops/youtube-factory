#!/bin/bash
# 2026-09-11 指揮者 Phase 4: moviepy 系 6ch の制作トリガ
# 指揮者はサンドボックスから localhost:8000 に到達できないため、Mac 側で実行する。
# 注意: OAuth が全ch失効中（invalid_grant）。再認可するまで生成はできてもアップロードは失敗する。
set -u
BASE="http://localhost:8000"
echo "== backend health =="
curl -s -m 5 "$BASE/api/health" || echo "(backend 応答なし)"
echo
for ch in daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts; do
  echo "== trigger: $ch =="
  curl -s -m 30 -X POST "$BASE/api/autopilot/$ch/trigger" || echo "  失敗: $ch"
  echo
  sleep 2
done
echo "完了。clip-lab（凍結中）と akashic-librarian（OAuth未連携）はスキップ。"
