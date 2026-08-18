#!/bin/bash
# ゆっくり妖怪ラボ ショート動画1本生成＆YouTube公開アップロード
cd "$(dirname "$0")/backend"

export SHORT_TARGET_SEC=60
export SHORT_PRIVACY=public

echo "🎬 ゆっくり妖怪ラボ ショート動画パイプライン開始"
echo "チャンネル: yokai-watch"
echo ""

# VOICEVOX 確認
python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:50021/speakers', timeout=2)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ VOICEVOX検出"
else
    echo "⚠️  VOICEVOX未検出 — Mock TTS で続行"
fi
echo ""

python3 run_channel_short_upload.py yokai-watch 2>&1

echo ""
echo "完了しました。このウインドウを閉じてOKです。"
