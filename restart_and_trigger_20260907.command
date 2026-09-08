#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-07 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達
#  できない。そのため Phase 4（制作指示）はこのスクリプトを Mac 上で
#  ダブルクリックして実行する必要がある。
#
#  ★ 今日の変更点（実データに基づく。詳細は reports/youtube_analysis_20260907.xlsx）
#    1. タイトルの「数字必須」ルールを撤回し、機械ゲートで逆に制限した
#       → 09-03 の「数字は1.56倍」はチャンネル間の交絡だった。チャンネル内
#         対照では3ch全てで数字ありが劣後（views 0.60倍 / 登録 0.43倍）。
#    2. 台本6行構成の「2行目」を根本から作り替えた
#       → 最大離脱が再生13〜22%地点に全ch共通で集中しており、そこに
#         「相槌だけで情報ゼロの行」を構造として置いていたのが原因。
#    3. 投稿枠の午後半ば（15時・16時）を廃止し 19時・9時30分へ移した。
#       ★ この3番目は APScheduler の再登録が要るので backend 再起動が必須。
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")" || exit 1

BASE="http://localhost:8000"
MOVIEPY_CH=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "================================================================"
echo " YouTube Factory 指揮者 — 2026-09-07"
echo "================================================================"
echo

# ---------------------------------------------------------------------
# 1. バックエンド再起動（投稿枠の変更を APScheduler に反映するため必須）
# ---------------------------------------------------------------------
echo "[1/4] バックエンド再起動..."
if [ -x ./restart-backend.command ]; then
  ./restart-backend.command || echo "  ⚠️ 再起動スクリプトが異常終了しました（続行します）"
else
  echo "  ⚠️ restart-backend.command が見つかりません。手動で再起動してください。"
fi
echo "  ...起動待ち 20秒"
sleep 20
echo

# ---------------------------------------------------------------------
# 2. 疎通確認
# ---------------------------------------------------------------------
echo "[2/4] バックエンド疎通確認..."
if ! curl -s -m 5 -o /dev/null "${BASE}/api/health" && ! curl -s -m 5 -o /dev/null "${BASE}/docs"; then
  echo "  ✗ localhost:8000 に到達できません。restart-backend.command を手動で実行してください。"
  exit 1
fi
echo "  ✓ バックエンド稼働中"
echo

# ---------------------------------------------------------------------
# 3. 投稿枠が新しい時刻で登録されたかの確認
# ---------------------------------------------------------------------
echo "[3/4] 投稿枠の確認（pokemon-lab は 8:30 / 17:30 / 19:00、yokai-watch は 9:30 / 12:00 / 17:45 が期待値）..."
for ch in pokemon-lab yokai-watch; do
  echo -n "  ${ch}: "
  curl -s -m 10 "${BASE}/api/channels/${ch}/autopilot" \
    | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    ts=((d.get("autopilot") or d).get("schedule") or {}).get("times") or []
    print(", ".join(f"{t[\"hour\"]}:{t.get(\"minute\",0):02d}" for t in ts) or "(枠なし)")
except Exception as e:
    print("取得失敗:", e)' 2>/dev/null || echo "取得失敗"
done
echo

# ---------------------------------------------------------------------
# 4. 制作指示（moviepy系6ch）
#    clip-lab は凍結中、akashic-librarian は台本ユーザー作成のためスキップ。
# ---------------------------------------------------------------------
echo "[4/4] 制作指示を送信..."
for ch in "${MOVIEPY_CH[@]}"; do
  echo -n "  ${ch} ... "
  code=$(curl -s -m 30 -o /tmp/yf_trigger_${ch}.json -w "%{http_code}" \
         -X POST "${BASE}/api/channels/${ch}/autopilot/run-now")
  if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "202" ]; then
    echo "✓ (HTTP ${code})"
  else
    echo "✗ HTTP ${code}"
    head -c 300 /tmp/yf_trigger_${ch}.json 2>/dev/null; echo
  fi
  sleep 2
done
echo

cat <<'GUIDE'
================================================================
 完了後に見るところ
================================================================
  生成ログ:      logs/ 配下の当日分
  分析シート:    reports/youtube_analysis_20260907.xlsx
  変更の根拠:    各 data/channels/*.json の pdca_log 末尾（date=2026-09-07）
  ロールバック:  data/channels/<ch>.json.bak_pdca_20260907_orch を戻す

 明日以降に必ず確認すること
  1. 09-04〜09-06 コホート（1日3本体制の初回分）の公開3日後の再生数。
     08月の水準は 700〜900回/本。ここを割っていたら投稿本数を1日2本へ戻す。
  2. タイトルから数字が抜けた回の再生数と登録数。
     数字なし群が数字あり群を上回れば、09-07 の撤回判断が正しかったことになる。
  3. 2行目の作りを変えた回の維持率カーブ。13〜22%地点の落ち込みが浅くなるか。
================================================================
GUIDE
