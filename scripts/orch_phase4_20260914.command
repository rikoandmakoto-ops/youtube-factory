#!/bin/bash
# =====================================================================
# 2026-09-14 指揮者 Phase 4: 制作指示 ＋ 本日の最重要作業
#
# 指揮者のサンドボックスからは localhost:8000 に到達できないため、
# Phase 4 は本スクリプトとして書き出し、Mac 側で実行する。
#
# ===========================  ① まず読む  ===========================
#
# ■ 復旧した: OAuth（2026-09-13）
#   09-09 以降 5 日止まっていた公開は復旧している。
#   yokai-watch / scp-lab / daily-science / company-facts / 2ch-matome / socio-rx は
#   09-13 に再認可済みで、09-13 に 7 本、以降も公開が通っている。
#   バックエンドログの直近 200KB には invalid_grant が 1 件も出ていない。
#
# ■ ただし再発する: OAuth 同意画面が「テスト」のままなら 7 日で失効する
#   09-01〜03 / 09-07〜08 / 09-09〜13 と 3 回再発している。
#   GCP の OAuth 同意画面を「テスト」→「本番」に公開しない限り、
#   次は 2026-09-20 前後にまた全滅する。**本番公開してから再認可し直すこと。**
#   （寿命は認可した瞬間に確定するので、順序を逆にすると意味がない）
#
# ■ 未再認可: pokemon-lab は 09-09 以降トークンが更新されていない
#   他の ch と違い再認可が通っていない。公開は落ちたままのはず。
#
# ■ ★本日の最重要★ カスタムサムネイルが 10ch 中 9ch で 1 枚も設定できていない
#   バックエンドログ全体（84MB）を横断して数えた結果:
#       サムネイル設定 成功 = daily-science 21 本のみ
#       サムネイル設定 失敗 = scp-lab 25 / company-facts 22 / pokemon-lab 20 /
#                             2ch-matome 20 / yokai-watch 19 / clip-kaneko 19 /
#                             fake-paper 13 / clip-lab 10 / clip-fukada 8 / clip-animal 2
#       → 失敗 163 本、成功 21 本。成功しているのは daily-science だけ。
#   エラーは全件これ:
#       HTTP 403 "The authenticated user doesn't have permissions to
#                 upload and set custom video thumbnails."
#   これは API の不具合ではなく、**YouTube アカウントが電話番号確認(本人確認)を
#   済ませていない**ときの仕様。未確認チャンネルはカスタムサムネを設定できない。
#
#   影響: 当該 9ch の公開済みショートは、こちらが作ったサムネではなく
#   YouTube が動画から自動抽出したフレームがサムネになっている。
#   「サムネ品質最優先」で積み上げてきた改善が、daily-science 以外では
#   1 枚も視聴者に届いていない。パイプライン側では直せない。
#
#   → 各チャンネルで https://www.youtube.com/verify を開き、電話番号確認を通すこと。
#      （チャンネルごとに別アカウントなので、9 回必要）
#      反映まで最大 24 時間かかる。確認後は滞留分のサムネを貼り直せる。
#
# =====================================================================
set -u
BASE="http://localhost:8000"
# autopilot.enabled=true の 4ch のみトリガする。
# 2ch-matome と pokemon-lab は enabled=false のまま（指揮者は enabled を変更していない）。
# 理由は reports/orch_config_changes_20260914.json の _hold を参照。
ENABLED=(daily-science scp-lab yokai-watch company-facts)

echo "=================================================="
echo " 2026-09-14 指揮者 Phase 4: 制作指示"
echo "=================================================="
echo
echo "== 1. バックエンド疎通 =="
if ! curl -s -m 5 "$BASE/health" ; then
  echo "  ⛔ バックエンドが応答しない。RestartBackend.app を先に実行すること。"
  exit 1
fi
echo
echo "== 2. サムネイル権限の確認（最重要） =="
echo "  未確認のチャンネルは https://www.youtube.com/verify で電話番号確認を通すこと。"
echo "  現時点で確認済みなのは daily-science のみ。"
echo
echo "== 3. 制作トリガ（autopilot 有効な 4ch） =="
for ch in "${ENABLED[@]}"; do
  echo "-- $ch"
  curl -s -m 30 -X POST "$BASE/api/autopilot/${ch}/trigger" \
    -H 'Content-Type: application/json' -d '{}' | head -c 400
  echo
  sleep 3
done
echo
echo "== 4. スキップした ch =="
echo "  2ch-matome  : autopilot.enabled=false（人が落とした状態。指揮者は触らない）"
echo "  pokemon-lab : autopilot.enabled=false ＋ OAuth 未再認可（09-09 以降）"
echo "  clip-lab    : 凍結中"
echo "  akashic-librarian : 台本ユーザー作成・OAuth 未連携"
echo
echo "== 5. 本日のコンフィグ変更 =="
echo "  投稿枠と theme_queue の型を実測の登録/千再生に基づいて変更済み。"
echo "  詳細: reports/orch_config_changes_20260914.json"
echo "  バックアップ: data/channels/*.json.bak_pdca_20260914_orch"
echo "  ※ APScheduler は新しい投稿枠をバックエンド再起動後に読み込む。"
echo "     RestartBackend.app を一度流しておくこと。"
echo
echo "完了。"
