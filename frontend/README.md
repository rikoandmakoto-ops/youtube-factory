# YouTube Factory — Frontend (Phase 1)

Next.js 14 (App Router) + TypeScript + Tailwind CSS で実装した動画生成管理パネル。
モバイルファースト設計で、iPhone から外部アクセス可能。

## 構成

```
frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx                  # / ダッシュボード（Server Component）
│   │   ├── login/                    # /login パスワードログイン
│   │   ├── generate/                 # /generate 動画生成フォーム
│   │   ├── channels/[id]/            # /channels/:id チャンネル詳細
│   │   └── api/                      # Next.js Route Handlers
│   │       ├── auth/login            # FastAPI 経由でログイン → httpOnly Cookie
│   │       ├── auth/logout
│   │       ├── jobs/                 # 動画生成ジョブ操作（FastAPI へプロキシ）
│   │       └── themes/suggest        # AIテーマ提案
│   ├── components/                   # 共有 UI コンポーネント
│   ├── lib/
│   │   ├── api.ts                    # FastAPI クライアント（型付き）
│   │   └── auth.ts                   # Cookie / セッショントークンヘルパー
│   └── middleware.ts                 # 認証ガード（未ログイン → /login へ）
├── package.json
└── tailwind.config.ts
```

## セットアップ

### 1. 依存インストール

```bash
cd frontend
npm install
```

### 2. 環境変数

```bash
cp .env.local.example .env.local
# 必要に応じて BACKEND_URL を編集
```

| 変数              | デフォルト                | 説明                              |
| ----------------- | ------------------------- | --------------------------------- |
| `BACKEND_URL`     | `http://localhost:8000`   | FastAPI バックエンドの URL        |
| `SESSION_SECRET`  | （任意）                  | Cookie 署名用の予備シークレット   |

### 3. バックエンド側のパスワード設定

```bash
cd ../backend
python scripts/hash_password.py
# 表示された APP_PASSWORD_HASH='...' を backend/.env に貼り付ける
# JWT_SECRET も .env に追加（openssl rand -hex 32）
```

### 4. 起動

```bash
# ターミナル A: バックエンド
cd backend
python main.py

# ターミナル B: フロントエンド
cd frontend
npm run dev
```

ブラウザで <http://localhost:3000> を開くとログイン画面に飛ばされる。

## 開発

```bash
npm run dev         # 開発サーバー（HMR）
npm run typecheck   # TypeScript 型チェック
npm run build       # 本番ビルド
npm run start       # 本番サーバー
```

---

## 外部アクセス（Cloudflare Tunnel / ngrok）

iPhone やリモート端末からアクセスする場合、`localhost` を公開する必要がある。
**フロントエンド (3000)** と **バックエンド (8000)** の両方を公開するか、
Next.js の `BACKEND_URL` を `http://localhost:8000` のままにしてフロントだけ公開する。

> 推奨: **フロントだけ公開**。Next.js のサーバーコンポーネントから内部的に
> バックエンドを叩くので、外部にバックエンドを露出する必要はない。

### 方式 A: Cloudflare Tunnel（無料・固定 URL）

Cloudflare アカウントが必要。固定ドメインを使えるので iPhone から再アクセスしやすい。

```bash
# 1. cloudflared をインストール
brew install cloudflared

# 2. Cloudflare へログイン
cloudflared tunnel login

# 3. トンネルを作成（一度だけ）
cloudflared tunnel create youtube-factory

# 4. config.yml を作成（~/.cloudflared/config.yml）
#    tunnel: <UUID>
#    credentials-file: /Users/<you>/.cloudflared/<UUID>.json
#    ingress:
#      - hostname: ytf.example.com
#        service: http://localhost:3000
#      - service: http_status:404

# 5. DNS ルートを追加
cloudflared tunnel route dns youtube-factory ytf.example.com

# 6. トンネル起動（バックグラウンド可）
cloudflared tunnel run youtube-factory
```

iPhone から `https://ytf.example.com` にアクセス → ログイン画面。

### 方式 B: ngrok（即席・無料は URL 変動あり）

```bash
# 1. ngrok をインストール
brew install ngrok

# 2. authtoken を設定（https://dashboard.ngrok.com/get-started/your-authtoken）
ngrok config add-authtoken <YOUR_TOKEN>

# 3. フロントエンドを公開
ngrok http 3000

# Forwarding https://abcd-1234.ngrok-free.app -> http://localhost:3000
```

無料プランは URL が毎回変わる。固定ドメインを取るには有料プラン or Cloudflare Tunnel を推奨。

### iPhone のホーム画面に追加

Safari で開く → 共有 → 「ホーム画面に追加」で PWA ライクに使える。

---

## セキュリティメモ

- パスワードは bcrypt ハッシュで `.env` に保存（平文 `APP_PASSWORD` は開発フォールバック）
- セッションは JWT（HS256, 7日有効）
- フロントから JWT を直接触れないよう httpOnly Cookie に格納
- ログインは IP あたり 5回/分 の制限
- 本番では HTTPS（Cloudflare Tunnel / ngrok の HTTPS 終端）必須
- `JWT_SECRET` を必ず設定すること（未設定だと派生キーになるが推奨されない）

## Phase 2 以降の TODO

- 新規チャンネル作成 UI
- チャンネル設定編集画面
- 動画詳細ページ（再生・差分編集）
- YouTube Analytics メトリクス取得（再生数・登録者）
- サムネイルプレビュー
- 自動投稿スケジューラ（Phase 3）
