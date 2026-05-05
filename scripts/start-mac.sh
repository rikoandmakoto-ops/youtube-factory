#!/usr/bin/env bash
# ============================================================
# YouTube Factory — Mac ローカル起動スクリプト
# バックエンド (FastAPI/uvicorn) + ngrok トンネル を起動
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

# プロジェクトルート（このスクリプトの親ディレクトリ）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="${PROJECT_DIR}/backend"

# 設定
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"
USE_TUNNEL="${USE_TUNNEL:-true}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"  # 固定ドメイン（空ならランダムURL）

# PIDファイル
PID_DIR="${PROJECT_DIR}/.pids"
mkdir -p "${PID_DIR}"
BACKEND_PID_FILE="${PID_DIR}/backend.pid"
NGROK_PID_FILE="${PID_DIR}/ngrok.pid"

# ngrok から取得した Public URL を保持
NGROK_PUBLIC_URL=""

# ============================================================
# クリーンアップ（Ctrl+C / 終了時）
# ============================================================
cleanup() {
    echo ""
    warn "シャットダウン中..."

    # バックエンド停止
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            info "バックエンド停止中 (PID: $BACKEND_PID)..."
            kill "$BACKEND_PID" 2>/dev/null || true
            wait "$BACKEND_PID" 2>/dev/null || true
        fi
        rm -f "$BACKEND_PID_FILE"
    fi

    # ngrok 停止
    if [ -f "$NGROK_PID_FILE" ]; then
        NGROK_PID=$(cat "$NGROK_PID_FILE")
        if kill -0 "$NGROK_PID" 2>/dev/null; then
            info "ngrok 停止中 (PID: $NGROK_PID)..."
            kill "$NGROK_PID" 2>/dev/null || true
            wait "$NGROK_PID" 2>/dev/null || true
        fi
        rm -f "$NGROK_PID_FILE"
    fi

    ok "全プロセス停止完了"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# ============================================================
# VOICEVOX チェック
# ============================================================
check_voicevox() {
    info "VOICEVOX エンジンを確認中..."
    VOICEVOX_URL="${VOICEVOX_URL:-http://localhost:50021}"
    if curl -s --max-time 3 "${VOICEVOX_URL}/version" >/dev/null 2>&1; then
        VOICEVOX_VERSION=$(curl -s --max-time 3 "${VOICEVOX_URL}/version" 2>/dev/null || echo "unknown")
        ok "VOICEVOX 接続OK (${VOICEVOX_URL}) — v${VOICEVOX_VERSION}"
    else
        warn "VOICEVOX が起動していません (${VOICEVOX_URL})"
        warn "音声生成機能を使うには VOICEVOX を先に起動してください"
    fi
}

# ============================================================
# バックエンド起動
# ============================================================
start_backend() {
    info "バックエンドを起動中..."

    cd "$BACKEND_DIR"

    # .env があれば読み込み
    if [ -f .env ]; then
        info ".env ファイルを読み込み中..."
        set -a
        source .env
        set +a
        # .env から読み込んだ NGROK_DOMAIN を反映
        NGROK_DOMAIN="${NGROK_DOMAIN:-}"
    fi

    # Python 仮想環境チェック
    if [ -d "${PROJECT_DIR}/venv" ]; then
        info "仮想環境を有効化中..."
        source "${PROJECT_DIR}/venv/bin/activate"
    elif [ -d "${PROJECT_DIR}/.venv" ]; then
        source "${PROJECT_DIR}/.venv/bin/activate"
    fi

    # 依存パッケージチェック
    if ! python3 -c "import fastapi" 2>/dev/null; then
        warn "FastAPI が見つかりません。依存パッケージをインストール中..."
        pip3 install -r "${BACKEND_DIR}/requirements.txt"
    fi

    # uvicorn でバックエンド起動（バックグラウンド）
    python3 -m uvicorn main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level info \
        &
    echo $! > "$BACKEND_PID_FILE"
    ok "バックエンド起動完了 (PID: $(cat $BACKEND_PID_FILE), http://${HOST}:${PORT})"
}

# ============================================================
# ngrok トンネル起動 & Public URL 取得
# ============================================================
start_ngrok() {
    if [ "$USE_TUNNEL" != "true" ]; then
        info "ngrok トンネルはスキップ（USE_TUNNEL=false）"
        return
    fi

    if ! command -v ngrok &>/dev/null; then
        warn "ngrok が見つかりません。トンネルなしで続行します。"
        warn "セットアップ: ./scripts/setup-ngrok.sh"
        return
    fi

    info "ngrok トンネルを起動中..."

    # 固定ドメインがあれば使う
    if [ -n "$NGROK_DOMAIN" ]; then
        info "固定ドメインを使用: ${NGROK_DOMAIN}"
        ngrok http --domain="$NGROK_DOMAIN" "$PORT" --log=stdout --log-level=warn &
    else
        ngrok http "$PORT" --log=stdout --log-level=warn &
    fi
    echo $! > "$NGROK_PID_FILE"

    # ngrok の Local API が起動するまで待機
    info "ngrok Public URL を取得中..."
    local retries=10
    local wait_sec=1

    for i in $(seq 1 $retries); do
        sleep $wait_sec
        NGROK_PUBLIC_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tunnels = data.get('tunnels', [])
    for t in tunnels:
        url = t.get('public_url', '')
        if url.startswith('https://'):
            print(url)
            break
    else:
        if tunnels:
            print(tunnels[0]['public_url'])
except:
    pass
" 2>/dev/null || echo "")

        if [ -n "$NGROK_PUBLIC_URL" ]; then
            break
        fi
    done

    if [ -n "$NGROK_PUBLIC_URL" ]; then
        ok "ngrok 起動完了 (PID: $(cat $NGROK_PID_FILE))"
        echo ""
        echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "  ${GREEN}  🌐 Public URL: ${NGROK_PUBLIC_URL}${NC}"
        echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo -e "  ${BLUE}ngrok 管理画面: http://localhost:4040${NC}"

        # 固定ドメインでなければURL変更の注意
        if [ -z "$NGROK_DOMAIN" ]; then
            echo ""
            warn "ランダムURLのため、再起動のたびにURLが変わります。"
            warn "Vercel の NEXT_PUBLIC_API_URL を都度更新してください。"
            warn "固定URLが欲しい場合: ./scripts/setup-ngrok.sh で Static Domain を設定"
        fi
    else
        warn "ngrok は起動しましたが、Public URL を取得できませんでした"
        warn "http://localhost:4040 で確認してください"
    fi
}

# ============================================================
# ヘルスチェック
# ============================================================
health_check() {
    info "ヘルスチェック中..."
    local retries=15
    local wait_sec=2

    for i in $(seq 1 $retries); do
        if curl -s --max-time 3 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
            HEALTH=$(curl -s "http://localhost:${PORT}/health" 2>/dev/null)
            ok "バックエンド正常稼働"
            echo -e "  ${GREEN}${HEALTH}${NC}"
            return 0
        fi
        echo -n "."
        sleep $wait_sec
    done

    err "ヘルスチェック失敗（${retries}回リトライ後）"
    err "ログを確認してください"
    return 1
}

# ============================================================
# メイン
# ============================================================
main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}🏭 YouTube Factory — ローカル起動${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    check_voicevox
    start_backend
    sleep 2

    if health_check; then
        start_ngrok

        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo -e "${GREEN}🎉 YouTube Factory 起動完了!${NC}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo -e "  ローカル:      http://localhost:${PORT}"
        echo -e "  ヘルス:        http://localhost:${PORT}/health"
        echo -e "  ダッシュボード:  http://localhost:${PORT}/dashboard/index.html"
        if [ -n "$NGROK_PUBLIC_URL" ]; then
            echo -e "  外部公開URL:   ${NGROK_PUBLIC_URL}"
        fi
        echo ""
        echo -e "  ${YELLOW}Ctrl+C で全プロセス停止${NC}"
        echo ""
    fi

    # フォアグラウンドで待機（Ctrl+Cを捕捉するため）
    wait
}

main "$@"
