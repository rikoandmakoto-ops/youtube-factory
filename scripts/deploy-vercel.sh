#!/usr/bin/env bash
# ============================================================
# YouTube Factory — Vercel デプロイスクリプト
# Next.js 静的ダッシュボードを Vercel にデプロイ
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${PROJECT_DIR}/frontend-vercel"

# ============================================================
# 前提チェック
# ============================================================
check_prerequisites() {
    info "前提条件を確認中..."

    # Node.js
    if ! command -v node &>/dev/null; then
        err "Node.js が見つかりません。インストールしてください。"
        exit 1
    fi
    ok "Node.js: $(node --version)"

    # npm
    if ! command -v npm &>/dev/null; then
        err "npm が見つかりません。"
        exit 1
    fi
    ok "npm: $(npm --version)"

    # Vercel CLI
    if ! command -v vercel &>/dev/null; then
        info "Vercel CLI をインストール中..."
        npm install -g vercel
    fi
    ok "Vercel CLI: $(vercel --version)"
}

# ============================================================
# ビルドテスト
# ============================================================
build_test() {
    info "フロントエンドをビルド中..."
    cd "$FRONTEND_DIR"

    # 依存パッケージインストール
    npm install

    # ビルド
    npm run build

    if [ -d "out" ]; then
        ok "静的エクスポート成功 (out/ ディレクトリ生成)"
        FILE_COUNT=$(find out -type f | wc -l | tr -d ' ')
        ok "ファイル数: ${FILE_COUNT}"
    else
        err "ビルド失敗: out/ ディレクトリが生成されませんでした"
        exit 1
    fi
}

# ============================================================
# 環境変数の案内
# ============================================================
show_env_guide() {
    echo ""
    echo -e "${YELLOW}■ Vercel 環境変数の設定:${NC}"
    echo ""
    echo "  デプロイ前に以下の環境変数を Vercel に設定してください:"
    echo ""
    echo "  1. Vercel ダッシュボード → Project Settings → Environment Variables"
    echo "     または vercel CLI:"
    echo ""
    echo -e "     ${GREEN}vercel env add NEXT_PUBLIC_API_URL${NC}"
    echo "       → ngrok の Public URL (例: https://your-name.ngrok-free.app)"
    echo "       ※ 固定ドメイン推奨。取得: https://dashboard.ngrok.com/domains"
    echo ""
    echo -e "     ${GREEN}vercel env add NEXT_PUBLIC_API_KEY${NC}"
    echo "       → backend/pipeline/credentials/api_key.txt の内容"
    echo ""

    # 既存の API キーがあれば表示
    API_KEY_FILE="${PROJECT_DIR}/backend/pipeline/credentials/api_key.txt"
    if [ -f "$API_KEY_FILE" ]; then
        ok "API キーファイル検出: ${API_KEY_FILE}"
        echo -e "  現在の API キー: ${YELLOW}$(cat "$API_KEY_FILE")${NC}"
    fi
    echo ""
}

# ============================================================
# デプロイ実行
# ============================================================
deploy() {
    cd "$FRONTEND_DIR"

    echo ""
    echo -e "${BLUE}■ デプロイ先を選択:${NC}"
    echo "  1) プレビュー（Preview）— テスト用"
    echo "  2) 本番（Production）"
    echo ""
    echo -n "  選択 (1/2): "
    read -r choice

    case "$choice" in
        2)
            info "本番デプロイを実行中..."
            vercel --prod
            ok "本番デプロイ完了"
            ;;
        *)
            info "プレビューデプロイを実行中..."
            vercel
            ok "プレビューデプロイ完了"
            ;;
    esac
}

# ============================================================
# メイン
# ============================================================
main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}🚀 YouTube Factory — Vercel デプロイ${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    check_prerequisites
    build_test
    show_env_guide

    echo -n "デプロイを続行しますか? (y/N): "
    read -r answer
    if [[ "$answer" =~ ^[Yy] ]]; then
        deploy
    else
        info "デプロイをスキップしました"
        info "手動デプロイ: cd frontend-vercel && vercel --prod"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}✅ 完了${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

main "$@"
