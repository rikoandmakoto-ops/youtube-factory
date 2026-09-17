#!/bin/bash
# backend.log のローテーション（2026-09-17 新設）
#
# launchd が StandardOutPath へ O_APPEND で書き続けるため、mv 方式では
# 新ファイルに切り替わらない。copytruncate 方式（コピーしてから切り詰め）を使う。
# O_APPEND なので truncate 後も書き込み位置は自動で先頭に戻り、ログは欠けない
# （コピーと truncate の間に書かれた数行だけは失われうるが許容する）。
#
# launchd（com.youtube-factory.logrotate）から毎日 04:30 に呼ばれる。
# 手動実行も可: bash scripts/rotate_backend_log.sh
set -u

LOG="/Users/ayukiyamazaki/Developer/youtube-factory/logs/backend.log"
KEEP=7                     # 圧縮済み世代の保持数
MAX_BYTES=$((20 * 1024 * 1024))  # これ未満ならローテートしない（20MB）

[ -f "$LOG" ] || exit 0
size=$(stat -f%z "$LOG" 2>/dev/null || echo 0)
[ "$size" -ge "$MAX_BYTES" ] || exit 0

ts=$(date +%Y%m%d_%H%M%S)
cp "$LOG" "${LOG}.${ts}"
: > "$LOG"
gzip "${LOG}.${ts}"
echo "🔄 backend.log rotated: ${size} bytes -> ${LOG}.${ts}.gz" >> "$LOG"

# 古い世代を削除（新しい順に KEEP 件残す）
ls -t "${LOG}".*.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r f; do
  rm -f "$f"
done
