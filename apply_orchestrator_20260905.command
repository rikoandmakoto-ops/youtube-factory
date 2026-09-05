#!/bin/bash
# ============================================================
#  YouTube Factory — 2026-09-05 指揮者 反映（Finderでダブルクリック）
#
#  やること:
#    1. サムネA/Bのベースライン単位バグを修正（DB更新）
#    2. バックエンド再起動 → 新しい投稿枠を APScheduler に再登録
#    3. 反映結果を確認して表示
#
#  なぜ手元実行が要るのか:
#    - data/analytics/analytics.db はサンドボックスから書き込むと
#      disk I/O error になるため、DB更新だけ切り出している。
#    - 投稿枠(cron)は起動時の restore_all() でしか再登録されないので、
#      style_rules や max_count と違って再起動が必須。
# ============================================================
set -u
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1

echo ""
echo "🎼 YouTube Factory — 2026-09-05 指揮者の反映"
echo "============================================"
echo "📁 $PROJECT_DIR"
echo ""

# --- 1. サムネA/B ベースライン修正 ---------------------------------------
echo "▶ 1/3  サムネA/B ベースラインの単位バグを修正"
echo "        (thumbnail_ab_tests.channel_avg_ctr に 42.4 / 37.3 という"
echo "         百分率スケールの遺物が残り、切替判定が壊れていた)"
echo ""
echo "   --- ドライラン ---"
python3 scripts/fix_thumbnail_ab_baseline_20260905.py
echo ""
read -r -p "   この内容で書き込む？ [y/N]: " ans
if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
  python3 scripts/fix_thumbnail_ab_baseline_20260905.py --apply
else
  echo "   スキップした（後で --apply を付けて実行できる）"
fi
echo ""

# --- 2. バックエンド再起動 ------------------------------------------------
echo "▶ 2/3  バックエンド再起動（新しい投稿枠を反映）"
echo "        2ch-matome 18:00 → 21:00"
echo "        scp-lab    09:00 → 17:00"
echo "        yokai-watch 19:00 → 17:45"
echo ""
if [ -x "$PROJECT_DIR/restart_backend.sh" ]; then
  "$PROJECT_DIR/restart_backend.sh"
else
  bash "$PROJECT_DIR/restart_backend.command"
fi
echo ""

# --- 3. 反映確認 ----------------------------------------------------------
echo "▶ 3/3  反映確認"
sleep 5
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 3 http://localhost:8000/health >/dev/null 2>&1; then
    echo "   ✅ バックエンド応答あり"
    break
  fi
  echo "   ... 起動待ち ($i/10)"
  sleep 3
done

echo ""
echo "   --- 登録された autopilot ジョブ（logs/backend.log より） ---"
grep -E "Autopilot for (2ch-matome|scp-lab|yokai-watch)" "$PROJECT_DIR/logs/backend.log" 2>/dev/null | tail -12

echo ""
echo "   --- 各chの現在の投稿枠（設定ファイル） ---"
python3 - <<'PY'
import json
for ch in ['daily-science','scp-lab','2ch-matome','pokemon-lab','yokai-watch','company-facts']:
    d = json.load(open(f'data/channels/{ch}.json', encoding='utf-8'))
    ts = d['autopilot']['schedule']['times']
    slots = ", ".join(f"{t['hour']:02d}:{t['minute']:02d}" for t in ts)
    arm = d.get('_experiments', {}).get('length_20260905', {}).get('arm', '-')
    print(f"   {ch:15} 尺実験={arm:9} 枠= {slots}")
PY

echo ""
echo "============================================"
echo "✅ 完了。詳細は reports/youtube_analysis_20260905.xlsx を見て。"
echo ""
echo "⚠️  尺の対照実験は 2026-09-12 に評価すること："
echo "    実験群 scp-lab / 2ch-matome（32〜36秒）"
echo "    対照群 daily-science / pokemon-lab / yokai-watch（現行26秒帯・変更禁止）"
echo ""
read -r -p "Enterで閉じる..." _
