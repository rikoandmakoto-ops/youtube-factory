#!/bin/bash
# 指揮者 Phase 4 — 2026-09-15 制作指示（手動トリガ）
#
# ★通常は実行不要★
#   APScheduler が本日分の枠をすべて正常に発火している（09-15 07:30 に
#   daily-science が公開済み、以降 13 枠が予約済み）ことをバックエンドログで
#   確認済み。本日のコンフィグ変更はテーマキュー補充と維持率目標帯の明記だけで、
#   投稿枠は変更していないためバックエンド再起動も不要。
#   このスクリプトを流すと **予約枠とは別に追加の動画が生成・公開される**。
#   在庫を余計に消費するので、枠が飛んだときの補填用としてのみ使うこと。
#
# 指揮者のサンドボックスから localhost:8000 には到達できない
# （host.docker.internal は "blocked-by-allowlist" で 403）ため .command で出力している。

cd "$(dirname "$0")/.." || exit 1
BASE="http://localhost:8000"

echo "=== バックエンド疎通確認 ==="
if ! curl -s -m 5 -o /dev/null "$BASE/docs"; then
  echo "❌ バックエンドに到達できません。RestartBackend.app を実行してください。"
  exit 1
fi
echo "✅ 応答あり"
echo

# autopilot 有効かつ OAuth 正常な 4ch のみ。
# 2ch-matome / pokemon-lab は autopilot.enabled=false（pokemon-lab は OAuth も
# invalid_grant のまま）。clip-lab は凍結中、akashic-librarian は OAuth 未連携。
CHANNELS=(daily-science scp-lab yokai-watch company-facts)

read -r -p "予約枠とは別に ${#CHANNELS[@]} 本を追加生成します。よろしいですか? [y/N] " ans
case "$ans" in
  [yY]*) ;;
  *) echo "中止しました。"; exit 0 ;;
esac

for ch in "${CHANNELS[@]}"; do
  echo "--- $ch ---"
  curl -s -X POST "$BASE/api/autopilot/$ch/trigger" -w '\nHTTP %{http_code}\n'
  echo
  sleep 3
done

echo "=== 完了 ==="
echo "進行状況: tail -f logs/backend.log"
