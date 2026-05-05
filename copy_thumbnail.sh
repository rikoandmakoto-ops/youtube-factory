#!/bin/bash
# Copy wrinkly_fingers thumbnail to Desktop and iCloud
SRC="/Users/ayukiyamazaki/Developer/youtube-factory/wrinkly_fingers_サムネイル_v2.png"

DESK_DIR="/Users/ayukiyamazaki/Desktop/動画出力用/お風呂で指がシワシワになる本当の理由"
mkdir -p "$DESK_DIR"
cp "$SRC" "$DESK_DIR/wrinkly_fingers_サムネイル.png"
echo "Copied to Desktop"

ICLOUD_DIR="/Users/ayukiyamazaki/Library/Mobile Documents/com~apple~CloudDocs/macmini iphone共有用/動画出力/お風呂で指がシワシワになる本当の理由"
mkdir -p "$ICLOUD_DIR"
cp "$SRC" "$ICLOUD_DIR/wrinkly_fingers_サムネイル.png"
echo "Copied to iCloud"

echo "DONE"
