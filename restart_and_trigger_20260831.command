#!/bin/bash
# =============================================================================
# 2026-08-31 PDCA 反映用: バックエンド再起動 → 全チャンネル制作トリガー
# =============================================================================
# 指揮者タスクが本日 backend/pipeline 配下のコードを修正したが、
# 起動中のバックエンドは修正前のコードをメモリに保持している。
# 再起動しない限り、本日 17:00〜19:00 の自動投稿には修正が反映されない。
#
# 本日の修正内容:
#   1. video_generator.py  尺ガードを警告のみ → 実際にトリムするよう変更
#   2. power_word_amplifier.py  形態素境界を無視した置換による日本語破損を修正
#   3. replay_loop_seeder.py  最終行に非単語が混入する不具合を修正
#   4. cta_rotator.py  「シリーズシリーズ」重複の解消 + 高評価CTAを常時挿入
#   5. completion_rate_optimizer.py  注入句を3箇所 → 1箇所に削減
#   6. shorts_length_guard.py  読点による末尾節除去をフォールバックに追加
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
for ch in daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts; do
  code=$(curl -s -m 30 -o /tmp/trigger_"$ch".json -w "%{http_code}" \
    -X POST "http://localhost:8000/api/autopilot/${ch}/trigger")
  echo "  ${ch}: HTTP ${code}"
done

echo "✅ 完了。生成台本は data/scenarios/*/archive/ で確認できます。"
echo "   尺ガードの発動は logs/backend.log の「✂️ ShortsLengthGuard」で確認してください。"
