# ============================================================
# YouTube Factory — FastAPI バックエンド Dockerfile
# ============================================================
FROM python:3.11-slim

# システム依存パッケージ（moviepy/Pillow用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージインストール（キャッシュ活用のため先にコピー）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコピー
COPY . .

# 認証情報ディレクトリ作成
RUN mkdir -p pipeline/credentials

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# uvicorn で起動
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
