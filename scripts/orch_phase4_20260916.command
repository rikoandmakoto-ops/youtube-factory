#!/bin/bash
# 指揮者 Phase 4 — 2026-09-16 制作指示
#
# ★本日は「再起動」を 1 回だけ実行してほしい★
#
#   本日 2ch-matome の autopilot.enabled を false → true に戻した
#   （scripts/orch_apply_20260916.py）。APScheduler のジョブ登録は
#   backend/api_channel_autopilot.py の restore_all() が起動時に
#   data/channels/*.json を読んで行うため、**バックエンドを再起動しないと
#   2ch-matome の枠は登録されない**。
#
#   再起動すれば本日の 12:15 / 17:30 の 2 枠が自動で入る。
#   手動トリガは不要（下の TRIGGER セクションは枠が飛んだときの補填用）。
#
#   他 4ch（daily-science / scp-lab / yokai-watch / company-facts）は
#   APScheduler が正常に発火している（09-16 06:45 に daily-science が発火し
#   07:30 に cTHPSuJr0nA を公開済み）。手動トリガを流すと予約枠とは別に
#   追加の動画が生成・公開され、テーマ在庫を余計に消費する。
#
# 指揮者のサンドボックスから localhost:8000 には到達できない
# （host.docker.internal は "blocked-by-allowlist" で 403）ため .command で出力している。

cd "$(dirname "$0")/.." || exit 1
BASE="http://localhost:8000"

echo "=============================================="
echo " 指揮者 Phase 4 — 2026-09-16"
echo "=============================================="
echo
echo "【1】バックエンド再起動（2ch-matome の枠を登録するために必須）"
read -r -p "    RestartBackend.app を実行して再起動しますか? [y/N] " ans
case "$ans" in
  [yY]*)
    open -a "$(pwd)/RestartBackend.app" 2>/dev/null \
      || bash "$(pwd)/restart-backend.command" \
      || echo "⚠️ 自動再起動に失敗。手動で RestartBackend.app を実行してください。"
    echo "    起動を待っています..."
    for _ in $(seq 1 30); do
      sleep 3
      curl -s -m 3 -o /dev/null "$BASE/docs" && break
    done
    ;;
  *) echo "    スキップしました。" ;;
esac
echo

echo "【2】疎通確認と autopilot 登録状況"
if ! curl -s -m 5 -o /dev/null "$BASE/docs"; then
  echo "❌ バックエンドに到達できません。RestartBackend.app を実行してください。"
  exit 1
fi
echo "✅ 応答あり"
echo
echo "  ログで以下を確認してください（2ch-matome が並んでいれば成功）:"
echo "    grep -a 'Autopilot restored' logs/backend.log | tail -1"
echo "    grep -a 'Autopilot scheduled for 2ch-matome' logs/backend.log | tail -3"
echo

echo "=============================================="
echo "【3】手動トリガ（★通常は実行不要★・枠が飛んだときの補填用）"
echo "=============================================="
read -r -p "    予約枠とは別に追加生成しますか? [y/N] " ans2
case "$ans2" in
  [yY]*) ;;
  *) echo "    実行しませんでした。以上で完了です。"; exit 0 ;;
esac

# autopilot 有効 かつ OAuth が生きている 5ch のみ。
# pokemon-lab は 09-10 07:43 を最後にトークンが失効（invalid_grant）しており
# 生成しても公開に到達しないので入れない。
# clip-lab は凍結中、akashic-librarian は OAuth 未連携。
CHANNELS=(daily-science scp-lab yokai-watch company-facts 2ch-matome)

for ch in "${CHANNELS[@]}"; do
  echo "--- $ch ---"
  curl -s -X POST "$BASE/api/autopilot/$ch/trigger" -w '\nHTTP %{http_code}\n'
  echo
  sleep 3
done

echo "=== 完了 ==="
echo "進行状況: tail -f logs/backend.log"
