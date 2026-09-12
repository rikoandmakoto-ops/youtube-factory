#!/bin/bash
# =====================================================================
# 2026-09-12 指揮者 Phase 4: 制作指示（Mac 側で実行する）
#
# 指揮者のサンドボックスからは localhost:8000 に到達できないため、
# Phase 4 は本スクリプトとして書き出し、Mac 側で人が実行する。
#
# ⛔ 先に読むこと ⛔
#   2026-09-09 以降、**YouTube へのアップロードは 4 日連続で 0 本**である。
#   動画の生成自体は成功している（09-10 に 41 本、09-11 に 24 本が Job completed）。
#   止まっているのは公開だけで、原因は全 13ch の OAuth リフレッシュトークン失効:
#       invalid_grant: Token has been expired or revoked.
#   したがって **再認可を通す前にこのスクリプトを流しても、動画が Desktop に積み上がるだけ**
#   でレンダーワーカー 2 本を無駄に占有する。必ず ①→② の順で進めること。
#
#   ① GCP の OAuth 同意画面を「テスト」→「本番」に公開する
#        テスト状態の同意画面はリフレッシュトークンの寿命が 7 日で固定される。
#        これが 7 日周期で全 ch が同時に落ちている原因（09-01〜03、09-07〜08、09-10〜 と再発）。
#        寿命は「認可した瞬間」に確定するので、**本番公開 → そのあと再認可** の順でなければ
#        再認可しても 7 日後にまた全滅する。
#   ② 管理画面から各チャンネルを再認可する
#        http://localhost:3000 → チャンネル設定 → YouTube 連携 → 再認可
#        （Google の同意画面はブラウザで人が通す必要がある。自動化できない）
#
# 再認可が済んだら、本スクリプトで滞留分の制作を回す。
# =====================================================================
set -u
BASE="http://localhost:8000"
MOVIEPY=(daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts)

echo "=================================================="
echo " 2026-09-12 指揮者 Phase 4: 制作指示"
echo "=================================================="
echo
echo "== 1. バックエンド疎通 =="
if ! curl -s -m 5 "$BASE/health" ; then
  echo "  ⛔ バックエンドが応答しない。restart_backend.command を先に実行すること。"
  exit 1
fi
echo
echo

echo "== 2. OAuth 状態 =="
curl -s -m 10 "$BASE/youtube/auth-status" || echo "  (auth-status 取得失敗)"
echo
echo "  ↑ ここが失効のままなら、この先を実行しても公開はされない。"
read -r -p "  再認可は完了しているか？ 続行する場合は y を入力: " ok
if [ "$ok" != "y" ]; then
  echo "  中止した。先に GCP 同意画面の本番公開 → 再認可を済ませること。"
  exit 0
fi
echo

echo "== 3. ログイン（セッショントークン取得） =="
echo "  /api/channels/{id}/autopilot/run-now は Bearer 認証が要る。"
read -r -s -p "  管理パスワード: " PW
echo
TOKEN=$(curl -s -m 10 -X POST "$BASE/api/auth/login" \
          -H 'Content-Type: application/json' \
          -d "{\"password\":\"$PW\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
unset PW
if [ -z "$TOKEN" ]; then
  echo "  ⛔ ログインに失敗した。パスワードを確認すること。"
  exit 1
fi
echo "  ✅ トークン取得"
echo

echo "== 4. moviepy 系 6ch に制作指示 =="
echo "  ※ clip-lab（凍結中）/ akashic-librarian（台本ユーザー作成）/ 切り抜き4ch はスキップ"
for ch in "${MOVIEPY[@]}"; do
  echo "  -- $ch"
  curl -s -m 30 -X POST "$BASE/api/channels/$ch/autopilot/run-now" \
       -H "Authorization: Bearer $TOKEN" || echo "     ⛔ 失敗: $ch"
  echo
  sleep 3
done
unset TOKEN
echo
echo "=================================================="
echo " 完了。logs/backend.log で「✅ アップロード完了」が出るか確認すること。"
echo " 出ないまま「⚠️ 自動公開スキップ」が続く場合は、再認可が効いていない。"
echo "=================================================="
