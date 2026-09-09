#!/bin/bash
# ===================================================================
#  YouTube Factory 指揮者 2026-09-09 — 人手が要る2工程だけ
# ===================================================================
#
# なぜ人手が要るか:
#   指揮者が動いているのは隔離された Linux サンドボックスで、
#   この Mac の localhost:8000 にも YouTube Data API にも到達できない
#   （googleapis.com=タイムアウト / host 経由=403）。通っているのは
#   マウント経由のファイル読み書きだけ。
#   → 分析・コンフィグ反映・xlsx・メモリは指揮者側で完了済み。
#     ネットワークが要る工程だけをここで実行する。
#
# 使い方: このファイルをダブルクリック
#
# 注意: Phase 4（制作指示）は **このスクリプトでは叩かない**。
#   backend/api_channel_autopilot.py が APScheduler に各チャンネルの
#   投稿枠を CronTrigger で登録しており、枠は毎日自動発火する。
#   ここで run-now を叩くと 1日3本の計画に**上乗せで**もう1本作られる。
#   本日のコンフィグ変更は、次に来る枠から自動で効く。
# ===================================================================
set -u
cd "$(dirname "$0")" || exit 1

CHANNELS="daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts"

echo "==================================================================="
echo " 指揮者 2026-09-09 — Phase 1（実績取得）"
echo "==================================================================="

if ! curl -s -m 5 -o /dev/null http://localhost:8000/health; then
  echo "✗ バックエンド(localhost:8000)が応答しません。"
  echo "  先に restart-backend.command を実行してください。"
  echo ""
  read -r -p "Enter で閉じる"
  exit 1
fi
echo "✓ バックエンド応答あり"
echo ""

echo "--- reach バルクレポート取り込み（全ch・窓から落ちると二度と取れない） ---"
curl -s -m 900 -X POST 'http://localhost:8000/api/analytics/reach/ingest-all?days=30' | head -c 1200
echo ""
echo ""

echo "--- チャンネル別メトリクス同期 ---"
for ch in $CHANNELS; do
  echo "▶ $ch"
  curl -s -m 600 -X POST "http://localhost:8000/api/analytics/sync/${ch}" \
    -H 'Content-Type: application/json' -d '{}' | head -c 400
  echo ""
done

echo ""
echo "==================================================================="
echo " ⚠️ 要バックエンド再起動（2点）"
echo "==================================================================="
cat <<'EOS'
【1】稼働中のバックエンドが、指揮者の設定変更を上書きして消す。
  本日 10:38 に反映した yokai-watch.json は、11:15:13 にバックエンドに
  丸ごと書き戻され、変更が全て消えていた（検証で気づいて再適用済み）。
  theme_queue の再生成のたびに、プロセスが起動時に読んだツリーで
  チャンネル JSON 全体が書き戻されるため。
  → 再起動するまで、本日の全チャンネルの変更が再び消えうる。

【2】scp-lab の autopilot 枠は 6 枠（同一時刻が2回ずつ）に重複登録されていた。
本日 3 枠へ直したが、APScheduler のジョブ ID は
  _job_id(channel_id, idx)   ← 枠の**添字**
で振られているため、稼働中プロセスには idx=3,4,5 の古いジョブが
そのまま残っている（JSON から消しても replace_existing は idx 0〜2 にしか
効かない）。つまり **再起動するまで scp-lab は 1日6本作り続ける。**

  → restart-backend.command を実行してください。

再起動後、以下で 3 枠になっていることを確認できる:
  curl -s http://localhost:8000/api/channels/scp-lab/autopilot | python3 -m json.tool
EOS
echo ""
read -r -p "Enter で閉じる"
