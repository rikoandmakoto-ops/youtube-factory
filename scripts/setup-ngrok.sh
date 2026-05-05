#!/usr/bin/env bash
# ============================================================
# YouTube Factory — ngrok セットアップスクリプト
# Vercel (Next.js) → ngrok トンネル → 自宅Mac (FastAPI + VOICEVOX)
#
# ドメインもCloudflareアカウントも不要。ngrok無料プランでOK。
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

BACKEND_PORT="${BACKEND_PORT:-8000}"

# ============================================================
# 1. ngrok インストール（brew）
# ============================================================
install_ngrok() {
    info "ngrok のインストールを確認中..."
    if command -v ngrok &>/dev/null; then
        ok "ngrok は既にインストール済み: $(ngrok version)"
        return
    fi

    if ! command -v brew &>/dev/null; then
        err "Homebrew が見つかりません。先にインストールしてください:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi

    info "ngrok をインストール中..."
    brew install ngrok/ngrok/ngrok
    ok "ngrok インストール完了: $(ngrok version)"
}

# ============================================================
# 2. ngrok authtoken 設定
# ============================================================
setup_authtoken() {
    info "ngrok 認証状態を確認中..."

    # 既に設定済みかチェック（config ファイルの存在確認）
    NGROK_CONFIG="${HOME}/Library/Application Support/ngrok/ngrok.yml"
    if [ -f "$NGROK_CONFIG" ] && grep -q "authtoken:" "$NGROK_CONFIG" 2>/dev/null; then
        ok "ngrok authtoken は設定済み"
        return
    fi

    # 環境変数から取得を試みる
    if [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        info "環境変数から authtoken を設定中..."
        ngrok config add-authtoken "$NGROK_AUTHTOKEN"
        ok "authtoken 設定完了（環境変数から）"
        return
    fi

    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  ngrok authtoken の設定が必要です${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  1. https://dashboard.ngrok.com/signup でアカウント作成（無料）"
    echo "  2. https://dashboard.ngrok.com/get-started/your-authtoken で"
    echo "     authtoken をコピー"
    echo ""
    echo -n "  authtoken を入力: "
    read -r token

    if [ -z "$token" ]; then
        err "authtoken が入力されませんでした"
        echo "  後で手動設定: ngrok config add-authtoken <YOUR_TOKEN>"
        exit 1
    fi

    ngrok config add-authtoken "$token"
    ok "authtoken 設定完了"
}

# ============================================================
# 3. 固定URL（Static Domain）の案内
# ============================================================
setup_static_domain() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  固定URL（Static Domain）について${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  ngrok 無料プランでも1つの固定ドメインが使えます。"
    echo "  毎回URLが変わらないので、Vercelの環境変数を更新する手間がなくなります。"
    echo ""
    echo "  取得方法:"
    echo "    1. https://dashboard.ngrok.com/domains にアクセス"
    echo "    2.「Create Domain」で固定ドメインを作成"
    echo "       例: your-name-random.ngrok-free.app"
    echo ""
    echo "  使い方:"
    echo -e "    ${GREEN}ngrok http --domain=your-name-random.ngrok-free.app ${BACKEND_PORT}${NC}"
    echo ""
    echo "  .env に設定しておくと start-mac.sh が自動で使います:"
    echo -e "    ${GREEN}NGROK_DOMAIN=your-name-random.ngrok-free.app${NC}"
    echo ""
}

# ============================================================
# 4. テスト起動
# ============================================================
test_tunnel() {
    echo -n "ngrok をテスト起動しますか? (y/N): "
    read -r test_answer
    if [[ ! "$test_answer" =~ ^[Yy] ]]; then
        info "テストをスキップしました"
        return
    fi

    NGROK_DOMAIN="${NGROK_DOMAIN:-}"

    if [ -n "$NGROK_DOMAIN" ]; then
        info "固定ドメインでテスト起動中: ${NGROK_DOMAIN}"
        ngrok http --domain="$NGROK_DOMAIN" "$BACKEND_PORT" &
    else
        info "ランダムURLでテスト起動中..."
        ngrok http "$BACKEND_PORT" &
    fi
    NGROK_PID=$!

    # ngrok API が起動するまで少し待つ
    sleep 3

    # public URL を取得
    PUBLIC_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tunnels = data.get('tunnels', [])
    if tunnels:
        print(tunnels[0]['public_url'])
except:
    pass
" 2>/dev/null || echo "")

    if [ -n "$PUBLIC_URL" ]; then
        ok "ngrok トンネル起動成功!"
        echo -e "  Public URL: ${GREEN}${PUBLIC_URL}${NC}"
        echo -e "  管理画面:   ${BLUE}http://localhost:4040${NC}"
    else
        warn "Public URL の取得に失敗しました"
        echo "  管理画面で確認: http://localhost:4040"
    fi

    echo ""
    echo -n "  Enterで停止..."
    read -r
    kill "$NGROK_PID" 2>/dev/null || true
    ok "テスト終了"
}

# ============================================================
# 5. 使い方の案内表示
# ============================================================
show_usage() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}🎉 ngrok セットアップ完了!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${BLUE}■ アーキテクチャ:${NC}"
    echo "  Vercel (Next.js) → https://xxxx.ngrok-free.app → ngrok → localhost:${BACKEND_PORT} (FastAPI)"
    echo ""
    echo -e "${BLUE}■ 手動起動:${NC}"
    echo "  ngrok http ${BACKEND_PORT}                                  # ランダムURL"
    echo "  ngrok http --domain=YOUR_DOMAIN.ngrok-free.app ${BACKEND_PORT}  # 固定URL"
    echo ""
    echo -e "${BLUE}■ 一括起動（推奨）:${NC}"
    echo "  ./scripts/start-mac.sh"
    echo ""
    echo -e "${BLUE}■ ngrok 管理画面:${NC}"
    echo "  http://localhost:4040  （トンネル起動中のみ）"
    echo ""
    echo -e "${BLUE}■ Vercel 環境変数に設定:${NC}"
    echo "  NEXT_PUBLIC_API_URL = ngrok の Public URL"
    echo "  （固定ドメイン使用時は一度設定すればOK）"
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
    echo -e "${BLUE}🌐 YouTube Factory — ngrok セットアップ${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    install_ngrok
    setup_authtoken
    setup_static_domain
    test_tunnel
    show_usage
}

main "$@"
