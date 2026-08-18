#!/bin/bash
# 生成済み動画をyoutube-factoryフォルダにコピー
SRC1="$HOME/Desktop/動画出力用/なぜ蔦屋書店だけ？有給消化率92%のホワイトな秘密/company-facts_ショート.mp4"
SRC2="$HOME/Desktop/動画出力用/ヤフーだけ異次元？有給80%・離職率3%に隠されたホワイト企業の真実/company-facts_ショート.mp4"
DEST="$HOME/Developer/youtube-factory/"

if [ -f "$SRC1" ]; then
    cp "$SRC1" "$DEST/蔦屋書店_ショート.mp4"
    echo "✅ 蔦屋書店 コピー完了"
fi

if [ -f "$SRC2" ]; then
    cp "$SRC2" "$DEST/ヤフー_ショート.mp4"
    echo "✅ ヤフー コピー完了"
fi

echo "完了"
sleep 2
