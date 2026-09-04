#!/bin/bash
# =====================================================================
#  YouTube Factory 指揮者 — 2026-09-03 実行スクリプト
#
#  指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達できない。
#  そのため Phase 4（制作指示）と OAuth 再認可は、このスクリプトを Mac 上で
#  ダブルクリックして実行する必要がある。
#
#  ★★★ 今日の最重要事項 ★★★
#  2026-09-02 15:01 をもって 全13チャンネルの OAuth トークンが失効した。
#  09-02 の予測（「09-07 前後に残り4chも失効」）より 5日早く、既に全滅している。
#  再認可しない限り、本日以降に生成される動画は1本も公開されない。
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")" || exit 1

BASE="http://localhost:8000"
MOVIEPY_CH=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "================================================================"
echo " YouTube Factory 指揮者 — 2026-09-03"
echo "================================================================"
echo

# ---------------------------------------------------------------------
# 0. バックエンド疎通
# ---------------------------------------------------------------------
echo "[0/4] バックエンド疎通確認..."
if ! curl -s -m 3 -o /dev/null "${BASE}/api/health" && ! curl -s -m 3 -o /dev/null "${BASE}/docs"; then
  echo "  ✗ localhost:8000 に到達できません。"
  echo "    先に restart-backend.command を実行してください。"
  exit 1
fi
echo "  ✓ バックエンド稼働中"
echo

# ---------------------------------------------------------------------
# 1. トークン健康診断（これが今日の本丸）
# ---------------------------------------------------------------------
echo "[1/4] OAuth トークン健康診断..."
python3 backend/check_youtube_tokens.py || true
echo
echo "  ── 指揮者による 09-03 10:04 時点の実測 ──"
echo "     全13ch が失効済み。失効時刻は3群に分かれる:"
echo "       08-31 05:07  clip-fukada / clip-kaneko"
echo "       08-31 15:00  daily-science"
echo "       09-01 03:04  2ch-matome / clip-lab / company-facts / pokemon-lab / scp-lab / yokai-watch"
echo "       09-02 15:00  akashic-librarian / clip-animal / fake-paper / socio-rx"
echo

# ---------------------------------------------------------------------
# 2. 恒久対策の案内（再認可は7日で再発するため、ここを先に潰す）
# ---------------------------------------------------------------------
cat <<'GUIDE'
[2/4] 恒久対策 ── ここを先にやらないと7日ごとに全チャンネルが止まり続けます

  原因: GCP の OAuth 同意画面が「テスト中」のままだと、Google はリフレッシュ
        トークンに 7日 の寿命を付ける。テスト中である限り、何度再認可しても
        7日後にまた全滅する（08-24・08-31・09-02 と3回起きている）。

  恒久対策: 同意画面を「本番」に公開する（公開すればトークンは無期限になる）
        https://console.cloud.google.com/auth/audience?project=844705815004
        → 「アプリを公開」→「本番環境に push」

  未解決の副次問題:
        backend/pipeline/credentials/client_secret.json が存在せず、
        アップロード経路が FileNotFoundError で落ち続けている（09-02 に5回）。
        同意画面の公開とあわせて、このファイルの設置も必要。

GUIDE
read -r -p "  同意画面の公開ページをブラウザで開きますか？ [y/N]: " OPENGCP
if [[ "${OPENGCP:-N}" =~ ^[Yy]$ ]]; then
  open "https://console.cloud.google.com/auth/audience?project=844705815004"
fi
echo

# ---------------------------------------------------------------------
# 3. 再認可
# ---------------------------------------------------------------------
echo "[3/4] 再認可..."
echo "  管理画面のチャンネル設定 → YouTube連携 から、各チャンネルを再認可してください。"
read -r -p "  管理画面を開きますか？ [y/N]: " OPENUI
if [[ "${OPENUI:-N}" =~ ^[Yy]$ ]]; then
  open "${BASE}/"
fi
echo
read -r -p "  再認可が完了したら Enter を押してください（スキップは Ctrl+C）: " _
python3 backend/check_youtube_tokens.py || true
echo

# ---------------------------------------------------------------------
# 4. 制作指示（Phase 4）
# ---------------------------------------------------------------------
echo "[4/4] 制作指示..."
echo "  注意: autopilot は既にスケジュール稼働しており、本日も scp-lab が 08:15 に発火済みです。"
echo "        各チャンネルは以下の時刻に自動発火するため、通常は手動トリガ不要です。"
echo "          company-facts 16:15 / 2ch-matome 17:15 / scp-lab 18:15 / yokai-watch 18:15"
echo "        再認可が上記より後になった場合のみ、手動トリガを実行してください。"
echo
read -r -p "  6チャンネルに手動トリガを発行しますか？ [y/N]: " DOTRIG
if [[ "${DOTRIG:-N}" =~ ^[Yy]$ ]]; then
  read -r -s -p "  管理画面のパスワード: " PW; echo
  TOKEN=$(curl -s -m 10 -X POST "${BASE}/api/auth/login" \
            -H 'Content-Type: application/json' \
            -d "{\"password\":\"${PW}\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
  if [ -z "$TOKEN" ]; then
    echo "  ✗ ログインに失敗しました。トリガをスキップします。"
  else
    echo "  ✓ ログイン成功"
    for ch in "${MOVIEPY_CH[@]}"; do
      code=$(curl -s -m 60 -o "/tmp/trigger_${ch}.json" -w "%{http_code}" \
        -X POST "${BASE}/api/channels/${ch}/autopilot/run-now" \
        -H "Authorization: Bearer ${TOKEN}")
      printf '    %-16s HTTP %s  %s\n' "$ch" "$code" "$(head -c 120 "/tmp/trigger_${ch}.json" 2>/dev/null)"
      sleep 2
    done
  fi
fi
echo
echo "  clip-lab（凍結中）と akashic-librarian（台本ユーザー作成）はスキップしました。"
echo

# ---------------------------------------------------------------------
# 後片付け: 実績再取得
# ---------------------------------------------------------------------
cat <<'TAIL'
================================================================
 完了。最後に実績を取り直しておくと、明日の指揮者の分析が正確になります。

   video_metrics は 6ch中5chが 08-31 で止まっています
   （2ch-matome / daily-science / pokemon-lab / scp-lab / yokai-watch）。
   トークン失効中は Analytics API も叩けないため、再認可後に:

     curl -s -X POST http://localhost:8000/api/analytics/fetch | head -c 400

================================================================
TAIL
