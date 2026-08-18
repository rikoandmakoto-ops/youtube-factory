#!/bin/bash
# daily-science ショート動画生成＆投稿（睡眠・夢ジャンル）
cd "$(dirname "$0")/backend"

# 睡眠・夢ジャンルの新テーマを指定
export SHORT_THEME_TITLE="なぜ夜中の3時に決まって目が覚めるのか？体内時計が仕掛けるある罠の正体"
export SHORT_THEME_ANGLE="睡眠サイクルとコルチゾールの関係"
export SHORT_TARGET_SEC=60
export SHORT_PRIVACY=public

echo "🎬 daily-science ショート動画パイプライン開始"
echo "テーマ: $SHORT_THEME_TITLE"
echo ""

python3 run_ds_short_upload.py 2>&1

echo ""
echo "完了しました。このウインドウを閉じてOKです。"
