#!/bin/bash
# =============================================================================
# 2026-09-01 PDCA 反映用: バックエンド再起動 → 全チャンネル制作トリガー
# =============================================================================
# 指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達できない
# （host.docker.internal / host.lima.internal いずれも経路なし）。そのため
# Phase 4 の制作指示はこのスクリプトとして生成した。
#
# 起動中のバックエンドは修正前のコードをメモリに保持しているため、
# 再起動しない限り本日の自動投稿には修正が反映されない。
#
# 本日の修正内容:
#   1. pipeline/cta_enforcer.py【新規】
#      ショート最終行に「高評価→登録」を決定論的に保証する。
#      08-29〜31 の実台本32本の実測で 高評価CTA 50% / 登録CTA 38% しか無く、
#      62%のショートが登録を一度も求めていなかったため。
#      CTA後ろのループ誘導句（…待って、Xに戻って）も除去する。
#   2. pipeline/video_generator.py
#      上記を shorts_length_guard の直前（実レンダリング経路）に接続。
#   3. pipeline/scenario_validator.py
#      LIKE_PATTERNS を追加し、_check_cta を「登録のみ」→「高評価+登録の両方」必須に。
#   4. data/channels/*.json, data/channels_orchestrator/*.json（6ch）
#      - yokai-watch: extra_rules が存在しない「8行目」を指していたのを「6行目」に修正
#      - 根拠を 2.16倍 → 6.3倍(n=322・単調) に更新し、
#        「終盤維持率は登録と無相関」という否定的知見を明記
#      - short_format.cta_fallback を追加（cta_enforcer が使う語り口）
#      - company-facts: 6行目に登録CTAを明示（唯一 高評価0/4・登録0/4 だった）
#
# 根拠（成熟動画 n=322 の高評価率4分位 × 登録/1000再生）:
#   0-0.2% 0.17 / 0.2-0.4% 0.32 / 0.4-0.8% 0.53 / 0.8%+ 1.07  ← 最下位の6.3倍・単調
#   終盤維持率(90-100%)は 0.41/0.26/0.42/0.30 と無相関。
# =============================================================================
set -u
cd "$(dirname "$0")" || exit 1

echo "▶ バックエンドを再起動します..."
if [ -x ./restart_backend.sh ]; then
  ./restart_backend.sh
elif [ -f ./restart_backend.command ]; then
  bash ./restart_backend.command
else
  echo "  ⚠️ 再起動スクリプトが見つかりません。手動で再起動してください。"
  exit 1
fi

echo "▶ 起動を待機中..."
for i in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null http://localhost:8000/api/health; then
    echo "  ✅ バックエンド応答を確認"
    break
  fi
  sleep 2
done

echo "▶ 制作トリガーを発行します（moviepy系6ch / clip-lab・akashic はスキップ）"
ok=0; ng=0
for ch in daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts; do
  code=$(curl -s -m 120 -o /tmp/trigger_"$ch".json -w "%{http_code}" \
    -X POST "http://localhost:8000/api/autopilot/${ch}/trigger")
  if [ "$code" = "200" ]; then
    echo "  ✅ ${ch}: HTTP ${code}"
    ok=$((ok+1))
  else
    echo "  ❌ ${ch}: HTTP ${code}  $(head -c 160 /tmp/trigger_"$ch".json 2>/dev/null)"
    ng=$((ng+1))
  fi
done

echo
echo "=== 結果: 成功 ${ok} / 失敗 ${ng} ==="
echo
echo "▶ 検証のしかた"
echo "  1) CTA補正の発動: logs/backend.log で「📣 CTA補正」を検索"
echo "     grep '📣 CTA補正' logs/backend.log | tail -20"
echo "  2) 生成台本の最終行に高評価と登録の両方が入っているか:"
echo "     python3 scripts/verify_cta_20260901.py"
echo "  3) 尺ガードの発動: grep '✂️' logs/backend.log | tail"
