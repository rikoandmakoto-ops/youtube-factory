#!/usr/bin/env bash
# ============================================================
# Cloudflare Tunnel セットアップスクリプト
# YouTube Factory: Vercel → Cloudflare Tunnel → 自宅Mac(FastAPI)
# ============================================================
set -euo pipefail

# 色付き出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

TUNNEL_NAME="${TUNNEL_NAME:-youtube-factory}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
TUNNEL_HOSTNAME="${TUNNEL_HOSTNAME:-}"  # 例: ytf-api.example.com

# ============================================================
# 1. cloudflared インストール（brew）
# ============================================================
install_cloudflared() {
    info "cloudflared のインストールを確認中..."
    if command -v cloudflared &>/dev/null; then
        ok "cloudflared は既にインストール済み: $(cloudflared --version)"
        return
    fi

    if ! command -v brew &>/dev/null; then
        err "Homebrew が見つかりません。先にインストールしてください:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi

    info "cloudflared をインストール中..."
    brew install cloudflare/cloudflare/cloudflared
    ok "cloudflared インストール完了: $(cloudflared --version)"
}

# ============================================================
# 2. Cloudflare ログイン
# ============================================================
login_cloudflare() {
    info "Cloudflare ログイン状態を確認中..."
    if cloudflared tunnel list &>/dev/null 2>&1; then
        ok "Cloudflare に認証済み"
        return
    fi

    info "ブラウザでCloudflareにログインしてください..."
    cloudflared tunnel login
    ok "Cloudflare ログイン完了"
}

# ============================================================
# 3. トンネル作成・config.yml 生成
# ============================================================
create_tunnel() {
    info "トンネル '${TUNNEL_NAME}' を確認中..."

    # 既存トンネルチェック
    TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null | python3 -c "
import sys, json
tunnels = json.load(sys.stdin)
for t in tunnels:
    if t['name'] == '${TUNNEL_NAME}':
        print(t['id'])
        break
" 2>/dev/null || echo "")

    if [ -n "$TUNNEL_ID" ]; then
        ok "既存トンネルを使用: ${TUNNEL_NAME} (${TUNNEL_ID})"
    else
        info "新規トンネルを作成中..."
        cloudflared tunnel create "${TUNNEL_NAME}"
        TUNNEL_ID=$(cloudflared tunnel list --output json | python3 -c "
import sys, json
tunnels = json.load(sys.stdin)
for t in tunnels:
    if t['name'] == '${TUNNEL_NAME}':
        print(t['id'])
        break
")
        ok "トンネル作成完了: ${TUNNEL_NAME} (${TUNNEL_ID})"
    fi

    # config.yml 生成
    CONFIG_DIR="${HOME}/.cloudflared"
    CONFIG_FILE="${CONFIG_DIR}/config.yml"
    mkdir -p "${CONFIG_DIR}"

    # ホスト名の設定
    if [ -z "$TUNNEL_HOSTNAME" ]; then
        warn "TUNNEL_HOSTNAME が未設定です。"
        echo -n "  使用するホスト名を入力 (例: ytf-api.example.com): "
        read -r TUNNEL_HOSTNAME
        if [ -z "$TUNNEL_HOSTNAME" ]; then
            err "ホスト名が必要です。TUNNEL_HOSTNAME 環境変数で設定してください。"
            exit 1
        fi
    fi

    cat > "${CONFIG_FILE}" <<EOF
# YouTube Factory — Cloudflare Tunnel 設定
# 自動生成: $(date +"%Y-%m-%d %H:%M:%S")
tunnel: ${TUNNEL_ID}
credentials-file: ${CONFIG_DIR}/${TUNNEL_ID}.json

ingress:
  # FastAPI バックエンド → ローカル uvicorn
  - hostname: ${TUNNEL_HOSTNAME}
    service: http://localhost:${BACKEND_PORT}
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s

  # ヘルスチェック用
  - hostname: ${TUNNEL_HOSTNAME}
    path: /health
    service: http://localhost:${BACKEND_PORT}

  # フォールバック（必須）
  - service: http_status:404
EOF

    ok "config.yml を生成しました: ${CONFIG_FILE}"
    echo ""
    info "DNS レコードの設定:"
    echo -e "  ${YELLOW}cloudflared tunnel route dns ${TUNNEL_NAME} ${TUNNEL_HOSTNAME}${NC}"
    echo ""
    echo -n "  今すぐ DNS を設定しますか? (y/N): "
    read -r dns_answer
    if [[ "$dns_answer" =~ ^[Yy] ]]; then
        cloudflared tunnel route dns "${TUNNEL_NAME}" "${TUNNEL_HOSTNAME}"
        ok "DNS ルート設定完了"
    else
        warn "後で手動で設定してください"
    fi
}

# ============================================================
# 4. macOS launchd サービス登録（自動起動）
# ============================================================
setup_launchd() {
    info "launchd サービスを設定中..."

    PLIST_DIR="${HOME}/Library/LaunchAgents"
    PLIST_FILE="${PLIST_DIR}/com.cloudflare.${TUNNEL_NAME}.plist"
    mkdir -p "${PLIST_DIR}"

    CLOUDFLARED_PATH=$(which cloudflared)
    CONFIG_FILE="${HOME}/.cloudflared/config.yml"
    LOG_DIR="${HOME}/Library/Logs/cloudflared"
    mkdir -p "${LOG_DIR}"

    cat > "${PLIST_FILE}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cloudflare.${TUNNEL_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${CLOUDFLARED_PATH}</string>
        <string>tunnel</string>
        <string>--config</string>
        <string>${CONFIG_FILE}</string>
        <string>run</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${TUNNEL_NAME}.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${TUNNEL_NAME}.error.log</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

    ok "launchd plist を作成: ${PLIST_FILE}"

    # 既存サービスをアンロード（エラーは無視）
    launchctl unload "${PLIST_FILE}" 2>/dev/null || true

    echo -n "  今すぐサービスを開始しますか? (y/N): "
    read -r start_answer
    if [[ "$start_answer" =~ ^[Yy] ]]; then
        launchctl load "${PLIST_FILE}"
        ok "サービス開始完了"
    else
        info "手動で開始するには:"
        echo "  launchctl load ${PLIST_FILE}"
    fi
}

# ============================================================
# 5. 使い方の案内表示
# ============================================================
show_usage() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}🎉 Cloudflare Tunnel セットアップ完了!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${BLUE}■ アーキテクチャ:${NC}"
    echo "  Vercel (Next.js) → https://${TUNNEL_HOSTNAME} → Cloudflare Tunnel → localhost:${BACKEND_PORT} (FastAPI)"
    echo ""
    echo -e "${BLUE}■ 手動起動:${NC}"
    echo "  cloudflared tunnel --config ~/.cloudflared/config.yml run"
    echo ""
    echo -e "${BLUE}■ launchd 操作:${NC}"
    echo "  起動: launchctl load ~/Library/LaunchAgents/com.cloudflare.${TUNNEL_NAME}.plist"
    echo "  停止: launchctl unload ~/Library/LaunchAgents/com.cloudflare.${TUNNEL_NAME}.plist"
    echo ""
    echo -e "${BLUE}■ ログ確認:${NC}"
    echo "  tail -f ~/Library/Logs/cloudflared/${TUNNEL_NAME}.log"
    echo ""
    echo -e "${BLUE}■ ステータス確認:${NC}"
    echo "  cloudflared tunnel info ${TUNNEL_NAME}"
    echo ""
    echo -e "${BLUE}■ Vercel 環境変数に設定:${NC}"
    echo "  NEXT_PUBLIC_API_URL = https://${TUNNEL_HOSTNAME}"
    echo ""
    echo -e "${YELLOW}■ 次のステップ:${NC}"
    echo "  1. バックエンドを起動: ./scripts/start-mac.sh"
    echo "  2. Vercelにデプロイ:   ./scripts/deploy-vercel.sh"
    echo ""
}

# ============================================================
# メイン実行
# ============================================================
main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}🌐 YouTube Factory — Cloudflare Tunnel セットアップ${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    install_cloudflared
    login_cloudflare
    create_tunnel
    setup_launchd
    show_usage
}

main "$@"
