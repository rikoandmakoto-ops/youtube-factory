#!/bin/bash
# =============================================================================
# 2026-09-02 PDCA 反映用: バックエンド再起動 → 全チャンネル制作トリガー
# =============================================================================
# 指揮者はサンドボックスVM上で動作しており Mac の localhost:8000 へ到達できない。
# さらに本日は実行時点でバックエンドが停止していた（health 応答なし）。
# そのため Phase 4 の制作指示はこのスクリプトとして生成した。
#
# 本日の変更内容（data/channels/*.json = channels_orchestrator と symlink 共有）:
#   1. 読み上げ速度 speed を 1.3 → 1.2 に統一（2ch-matome のみ 1.35 → 1.25）
#      ★これは確定的な改善ではなく「仮説検証」である。反証条件を下に明記した。
#      唯一 speed=1.2 の company-facts が 平均視聴33.9秒＝他ch(14.8-17.3秒)の約2倍、
#      登録転換0.076%も最良。speed は company-facts の設定上の唯一の差分。
#      ただし company-facts は推定尺55.5秒（最長）でもあり、速度単独の効果とは分離できていない。
#      また 2ch-matome は speed 1.35（最速）で維持率52.4%（2位）であり、
#      「速度が低いほど維持率が高い」は単純には成立しない
#      （2ch-matome の高維持率は推定尺30.7秒＝最短による機械的なもので、
#        絶対視聴秒15.6秒・登録転換0.016%＝最下位）。
#      → 維持率(率)は尺に交絡するため、判断は絶対視聴秒で行う。
#      company-facts は 1.2 のまま据え置き、対照群として翌日コホートで検証する。
#   2. short_format.structure に「答えの遅延」ルールを追加
#      （daily-science / scp-lab / pokemon-lab / yokai-watch）
#      scp-lab は 維持率40.3% / 平均視聴14.8秒 でいずれも全ch最下位。
#      各chとも推定尺の39-46%地点で離脱しており、3行目で核心を出し切る構成が原因と判断。
#      1行目の問いの答えを5行目まで伏せる制約を明文化。
#   3. 2ch-matome の short_endcard を登録訴求型に変更
#      登録転換率 0.016%（最良の company-facts 0.076% の約1/5・全ch最下位）。
#      参加型お題でコメントには誘導できているが登録動線が無かった。
#   4. テーマキュー補充（+37本）
#      scp-lab が 0 本 = 本日の制作が停止する状態だった（最優先修正）。
#      scp-lab 0→12 / daily-science 5→13 / pokemon-lab 7→12 /
#      yokai-watch 12→16 / company-facts 8→16
#
# 根拠データ（data/analytics/analytics.db, published_at>=2026-08-10, views>150, n=138）:
#   ch別        speed  維持率  平均視聴  推定尺  登録転換
#   daily-science 1.3   42.3%  15.0s   36.8s  0.047%
#   scp-lab       1.3   40.3%  14.8s   39.8s  0.066%
#   2ch-matome   1.35   52.4%  15.6s   30.7s  0.016%
#   pokemon-lab   1.3   43.1%  16.4s   41.6s  0.024%
#   yokai-watch   1.3   46.6%  17.3s   37.6s  0.022%
#   company-facts 1.2   58.5%  33.9s   55.5s  0.076%
#
#   絶対視聴秒 × 登録転換: 0-14s 0.031% / 14-17s 0.038% / 17-22s 0.035% / 22s+ 0.061%
#     → 22秒以上視聴されると登録転換が約2倍。これが本日の変更の実質的な狙い。
#   ナンバリング型タイトル 維持率 33.3% vs 自然文 52.3%
#     → 08-31 適用の禁止ルールは有効に機能（08-31公開分 0/7本）。維持。
#
# ★反証条件: 変更した5chの「絶対視聴秒」が3日以内に改善しない場合、速度は主因ではないと
#   判断し、speed を元の値（4ch=1.3 / 2ch-matome=1.35）へ戻すこと。
#
# 注意: video_metrics.views は累積スナップショットであり日次デルタではない。
#       本日の分析は全て前週スナップショットとの差分で算出している。
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
up=0
for i in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null http://localhost:8000/api/health; then
    echo "  ✅ バックエンド応答を確認"
    up=1
    break
  fi
  sleep 2
done
if [ "$up" != "1" ]; then
  echo "  ❌ バックエンドが起動しませんでした。logs/backend.log を確認してください。"
  exit 1
fi

echo "▶ 制作トリガーを発行します（moviepy系6ch / clip-lab・akashic はスキップ）"
ok=0; ng=0
for ch in daily-science scp-lab 2ch-matome pokemon-lab yokai-watch company-facts; do
  code=$(curl -s -m 180 -o /tmp/trigger_"$ch".json -w "%{http_code}" \
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
echo "  1) 速度変更の反映: grep -i 'speed' logs/backend.log | tail -20"
echo "  2) テーマキューの消費: python3 -c \"import json;[print(c, len(json.load(open(f'data/channels/{c}.json'))['autopilot']['theme_queue'])) for c in ['daily-science','scp-lab','2ch-matome','pokemon-lab','yokai-watch','company-facts']]\""
echo "  3) CTA補正の発動: grep '📣 CTA補正' logs/backend.log | tail -20"
echo "  4) 実績の再取得（アナリティクス更新）:"
echo "     curl -s -X POST http://localhost:8000/api/analytics/fetch | head -c 400"
echo
echo "▶ 明日の指揮者タスクでの検証項目"
echo "  speed を下げた5ch（daily-science/scp-lab/pokemon-lab/yokai-watch/2ch-matome）の"
echo "  「絶対視聴秒」が 14.8-17.3秒 から改善しているか。"
echo "  対照群 company-facts（speed 1.2 据え置き・視聴33.9秒）との差が縮まれば仮説を支持。"
echo "  3日以内に改善しなければ speed を元の値へ戻すこと（反証条件）。"
