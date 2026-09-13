#!/bin/bash
# =====================================================================
# YouTube Factory 復旧スクリプト (2026-09-13)
#
# 【現状】2026-09-09 以降、全チャンネルの OAuth リフレッシュトークンが
#        invalid_grant (Token has been expired or revoked) で失効しており、
#        動画の生成は成功しているが **公開が 1 本も通っていない**。
#        09-09〜09-13 で 95 本が生成済み・未公開のまま滞留している。
#
# 【原因】全 ch のトークンがほぼ同時に失効している。GCP の OAuth 同意画面が
#        「テスト」のままだと、発行されたリフレッシュトークンは 7 日で失効する。
#        各 ch は別々の OAuth クライアントを使っているが、同時多発である以上
#        この 7 日ルールが最有力。
#
# 【手順】① GCP 同意画面を「本番」に公開（←これが通らないと再認可しても7日で再発）
#        ② 各 ch を再認可（このスクリプトが案内する）
#        ③ 滞留分を公開
#
# 使い方: Finder でダブルクリック、または  bash scripts/orch_recover_20260913.command
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

API="http://localhost:8000"
FRONT="http://localhost:5173"

CHANNELS=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "============================================================"
echo " YouTube Factory 復旧 — 2026-09-13"
echo "============================================================"
echo

# --- 0. バックエンド疎通 --------------------------------------------------
echo "[0] バックエンド疎通確認"
if curl -s -m 5 "$API/api/status" >/dev/null 2>&1 || curl -s -m 5 "$API/docs" >/dev/null 2>&1; then
  echo "    ✅ $API に到達"
else
  echo "    ❌ $API に到達できません。先に restart_backend.command を実行してください。"
  read -r -p "    Enter で終了"
  exit 1
fi
echo

# --- 1. トークン状態の一覧 -------------------------------------------------
echo "[1] 各チャンネルのトークン状態"
python3 - <<'PY'
import sqlite3, time, datetime, pathlib
db = pathlib.Path("data/youtube_tokens.db")
if not db.exists():
    print("    token DB が見つかりません:", db); raise SystemExit
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
now = time.time()
rows = list(c.execute(
    "SELECT channel_id, youtube_channel_name, expires_at, updated_at "
    "FROM oauth_tokens ORDER BY updated_at DESC"))
print(f"    {'channel_id':20}{'最終更新':>18}{'状態':>12}")
for r in rows:
    upd = datetime.datetime.fromtimestamp(r["updated_at"]).strftime("%m-%d %H:%M")
    age_days = (now - r["updated_at"]) / 86400
    state = "要再認可" if age_days > 2 else "OK?"
    print(f"    {r['channel_id']:20}{upd:>18}{state:>12}  ({age_days:.1f}日前)")
PY
echo

# --- 2. 滞留している未公開動画 ---------------------------------------------
echo "[2] 生成済み・未公開の滞留本数（09-09 以降）"
OUTDIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/macmini iphone共有用/動画出力"
if [ -d "$OUTDIR" ]; then
  find "$OUTDIR" -maxdepth 1 -mindepth 1 -type d -newermt "2026-09-09" 2>/dev/null \
    | wc -l | xargs printf "    滞留: %s 本\n"
else
  echo "    出力フォルダが見つかりません: $OUTDIR"
fi
echo

# --- 3. GCP 同意画面の確認（手動）------------------------------------------
cat <<'EOS'
[3] ★最優先★ GCP OAuth 同意画面を「本番」に公開する
    → https://console.cloud.google.com/auth/overview
    各 ch の OAuth クライアントが属するプロジェクトすべてで、
    公開ステータスが「テスト」なら「アプリを公開」を押す。

    これをやらずに再認可だけしても、7 日後にまた同じ状態に戻ります。
EOS
read -r -p "    同意画面の公開が済んだら Enter（まだなら Ctrl-C で中断）"
echo

# --- 4. 再認可 --------------------------------------------------------------
echo "[4] 各チャンネルの再認可"
echo "    管理画面を開きます: $FRONT"
echo "    チャンネル設定 → YouTube 連携 → 「再接続」を ch ごとに実行してください。"
open "$FRONT" 2>/dev/null || echo "    （ブラウザで $FRONT を開いてください）"
echo
read -r -p "    全 ch の再認可が済んだら Enter"
echo

# --- 5. 再認可の検証 --------------------------------------------------------
echo "[5] 再認可の検証"
python3 - <<'PY'
import sqlite3, time, pathlib
c = sqlite3.connect(pathlib.Path("data/youtube_tokens.db")); c.row_factory = sqlite3.Row
now = time.time(); ok = ng = 0
for r in c.execute("SELECT channel_id, updated_at FROM oauth_tokens"):
    fresh = (now - r["updated_at"]) < 3600
    print(f"    {'✅' if fresh else '❌'} {r['channel_id']}")
    ok += fresh; ng += (not fresh)
print(f"\n    再認可済み {ok} ch / 未了 {ng} ch")
PY
echo

# --- 6. 制作トリガ（任意）---------------------------------------------------
cat <<'EOS'
[6] 制作トリガ（任意）

    ※ 注意: すでに 95 本が未公開で滞留しています。公開が復旧するまで
      追加生成すると在庫が積み上がるだけです。
      また autopilot は APScheduler で自動発火し続けているため、
      通常は手動トリガは不要です。
      「復旧を確認したうえで、今日の分を追加で回したい」場合のみ y を選んでください。
EOS
read -r -p "    手動トリガを実行しますか？ [y/N]: " DO_TRIGGER
if [[ "${DO_TRIGGER:-N}" =~ ^[Yy]$ ]]; then
  read -r -s -p "    管理画面のパスワード: " PW; echo
  TOKEN=$(curl -s -m 10 -X POST "$API/api/auth/login" \
            -H 'Content-Type: application/json' \
            -d "{\"password\":\"$PW\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
  if [ -z "$TOKEN" ]; then
    echo "    ❌ ログインに失敗しました。トリガはスキップします。"
  else
    for ch in "${CHANNELS[@]}"; do
      # 正しいエンドポイントは /api/channels/{id}/autopilot/run-now
      RES=$(curl -s -m 20 -X POST "$API/api/channels/$ch/autopilot/run-now" \
              -H "Authorization: Bearer $TOKEN")
      echo "    $ch → $RES"
      sleep 2
    done
  fi
else
  echo "    スキップしました（推奨）。"
fi

echo
echo "============================================================"
echo " 完了。滞留していた 95 本は再認可後、公開キューから順次処理されます。"
echo " 反映されない場合は restart_backend.command でバックエンドを再起動してください。"
echo "============================================================"
read -r -p "Enter で閉じる"
