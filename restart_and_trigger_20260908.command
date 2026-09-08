#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-08 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達
#  できない。そのため Phase 4（制作指示）はこのスクリプトを Mac 上で
#  ダブルクリックして実行する必要がある。
#
#  ★ 今日の変更点（実データ根拠。詳細は reports/youtube_analysis_20260908.xlsx）
#    1. 【全6ch】タイトルを「答え提示型」に必須化した。
#       根拠: 09-07スナップショット n=196 で、答え提示語（理由/正体/本当の/
#       実は/わけ/なぜ/真相/裏側/実態）ありは 登録/千再生 0.57、なしは 0.31。
#       同じデータで維持率は逆に 45.0% vs 58.0% と提示型のほうが低い。
#       → 「最後まで見せる」ことと「登録させる」ことは別物である。
#    2. 【2ch-matome】参加型フォーマットを全面撤回した（最重要）。
#       根拠: 当ch内で参加型 登録/千再生 0.06 vs 結論型 0.31（5.2倍差）。
#       平均再生は 1004 vs 1069 でほぼ同じ＝参加型は「再生は取れるが
#       登録に一切変換しない」。当chは登録/千 0.20・高評価率 0.241% で
#       ともに6ch最下位だが、原因は面白さではなく「答えを渡さない構造」。
#       - short_format 3〜5行目: 「正解を断定せず余白を残す」を撤回、
#         5行目で必ず答えを言い切る構成へ
#       - 6行目CTA: コメント併記をやめ「高評価＋登録」に一本化
#       - theme_queue: 参加型27件を削除し結論型20件を投入
#    3. 【投稿枠】ch内実測で劣後する3枠だけ移設した。
#       company-facts 13:30→19:00（14時台 0.38 vs 19時 0.94）
#       pokemon-lab   17:30→17:00（18時台 0.21 vs 17時台 0.41）
#       yokai-watch   17:45→17:00（19時台 0.24 が当ch最下位、17時台は全ch最良 0.70）
#       ★ この3番目は APScheduler の再登録が要るので backend 再起動が必須。
#
#  ★ 検証済み
#    backend/tests は 変更前 8 failed → 変更後 7 failed（1件解消・新規ゼロ）。
#    残る7件は sandbox に fastapi / moviepy が無いことによる環境起因、および
#    clip-animal / clip-kaneko のハッシュタグ（本日は非対象ch）。
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")" || exit 1

BASE="http://localhost:8000"
MOVIEPY_CH=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "================================================================"
echo " YouTube Factory 指揮者 — 2026-09-08"
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

# ---------------------------------------------------------------------
# 2. ヘルスチェック
# ---------------------------------------------------------------------
echo
echo "[2/4] ヘルスチェック..."
for i in $(seq 1 10); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$BASE/health" || echo "000")
  if [ "$CODE" = "200" ]; then echo "  ✅ backend 応答 OK"; break; fi
  echo "  ...待機中 ($i/10) code=$CODE"; sleep 5
done
if [ "${CODE:-000}" != "200" ]; then
  echo "  ❌ backend が応答しません。以降の制作指示はスキップします。"
  echo "     start_server.command を手動で実行してから、このスクリプトを再実行してください。"
  exit 1
fi

# ---------------------------------------------------------------------
# 3. 投稿枠が反映されたか確認
# ---------------------------------------------------------------------
echo
echo "[3/4] 投稿枠の反映確認..."
for ch in company-facts pokemon-lab yokai-watch; do
  echo "  --- $ch"
  curl -s -m 10 "$BASE/api/autopilot/$ch/status" 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('     ',[f\"{t['hour']:02d}:{t['minute']:02d}\" for t in (d.get('schedule') or {}).get('times',[])])" \
    2>/dev/null || echo "      (status API 無し。data/channels/$ch.json の times を目視確認してください)"
done

# ---------------------------------------------------------------------
# 4. 制作指示（moviepy系6ch）
#    clip-lab は凍結中、akashic-librarian は OAuth 未連携のためスキップ
# ---------------------------------------------------------------------
echo
echo "[4/4] 制作指示（moviepy系6ch）..."
OK=0; NG=0
for ch in "${MOVIEPY_CH[@]}"; do
  printf "  %-16s ... " "$ch"
  RESP=$(curl -s -m 120 -X POST "$BASE/api/autopilot/$ch/trigger" -H "Content-Type: application/json" -d '{}' 2>&1)
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 5 -X POST "$BASE/api/autopilot/$ch/trigger" -H "Content-Type: application/json" -d '{}' 2>/dev/null || echo "000")
  if echo "$RESP" | grep -qiE '"(ok|success)"\s*:\s*true|job_id|queued|started'; then
    echo "✅"; OK=$((OK+1))
  else
    echo "❌  $(echo "$RESP" | head -c 200)"; NG=$((NG+1))
  fi
  sleep 3
done

echo
echo "================================================================"
echo " 完了: 成功 $OK ch / 失敗 $NG ch"
echo "================================================================"
echo
echo "▼ 生成後に必ず目視で確認すること（本日の変更の合否判定）"
echo "  1. 全6chのタイトルに 理由/正体/本当の/実は/わけ/なぜ/真相/裏側/実態 のいずれかが入っているか"
echo "  2. 2ch-matome の台本5行目が『つまり〇〇やったんや』で答えを断定して終わっているか"
echo "  3. 2ch-matome の6行目に『高評価』と『チャンネル登録』が入り、コメント誘導が消えているか"
echo
echo "▼ 反証の期限: 2026-09-15"
echo "  (a) 答え提示型100%化後も全体の 登録/千再生 が 0.47 を上回らなければ撤回"
echo "  (b) 2ch-matome の 登録/千再生 が 0.20→0.35 を超えなければ参加型撤回を戻す"
echo "  (c) 移設した3枠が移設前の実績を下回れば戻す"
echo
echo "▼ 積み残し（指揮者では解決できない・ユーザー操作が必要）"
echo "  - OAuth 7日失効: GCP同意画面を「テスト中」→「本番」へ公開してから13ch再認可"
echo "    https://console.cloud.google.com/auth/audience (project 844705815004)"
echo "    ★順序厳守: ①本番公開 → ②再認可。逆だと7日後に同じことが起きる。"
echo "  - サムネ403: https://www.youtube.com/verify を各chで実施（未実施ch分）"
echo "  - backend/.env に ANTHROPIC_API_KEY が無い（series_engine が全chで未応答の真因）"
echo
read -n 1 -s -r -p "Enterキーで閉じます..."
