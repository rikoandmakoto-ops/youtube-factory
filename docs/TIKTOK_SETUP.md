# TikTok 自動投稿セットアップガイド

YouTube Factory に **TikTok Content Posting API**（正規ルート）で自動投稿する機能を追加しました。
YouTube と並行して「YouTube + TikTok 同時投稿」「TikTok のみ」などを選べます。

このドキュメントは、TikTok アカウント作成 → 開発者登録 → アプリ作成 → 連携 → 審査申請までの
手順をまとめたものです。**コード側は実装済みなので、以下の準備が整い次第すぐ使えます。**

---

## 0. 全体像（先に結論）

| 項目 | 値 |
|------|-----|
| 使用 API | TikTok **Content Posting API**（Direct Post） + **Login Kit**（OAuth v2） |
| 必要スコープ | `user.info.basic` / `video.publish` / `video.upload` |
| **Redirect URI（本番）** | `https://youtube-factory-eight.vercel.app/oauth/tiktok/callback` |
| **Redirect URI（ローカル）** | `http://localhost:3000/oauth/tiktok/callback` |
| 連携に必要な情報 | **Client key** と **Client secret**（アプリ作成後に発行） |
| 投稿できる動画 | MP4(H.264) / 3〜600秒 / 最大 4GB |
| ⚠️ 審査前の制限 | **全投稿が非公開(SELF_ONLY)に強制**される。一般公開は審査(audit)通過後 |

> **戦略**: まず未審査のまま連携して「非公開投稿」で動作確認 → その後アプリ審査を申請して
> 一般公開を解禁、という二段構えで進めます。審査待ちの間もコードは完成しているので、
> 審査が通ったら設定で公開範囲を `PUBLIC_TO_EVERYONE` に変えるだけです。

---

## 1. TikTok アカウントを作る

1. スマホアプリ or [tiktok.com](https://www.tiktok.com) でアカウント作成。
2. **メールアドレス**で登録しておく（開発者登録・審査の連絡に使う）。
3. プロフィール（アイコン・名前・自己紹介）を埋める。審査では「実在する運用アカウント」
   であることが見られるため、**先に数本は手動投稿しておく**と審査が通りやすい。
4. （重要）**電話番号認証**を済ませておく。一部機能で要求される。

> チャンネルごとに別 TikTok アカウントを使う場合は、アカウントの数だけ用意します。
> （本実装はチャンネル別に OAuth トークンを保存するので、複数アカウント運用に対応済み）

---

## 2. TikTok for Developers に登録 → アプリ作成

1. [developers.tiktok.com](https://developers.tiktok.com) にアクセスし、上記アカウントでログイン。
2. **Manage apps** → **Connect an app**（アプリ作成）。
3. アプリ情報を入力:
   - **App name**: 例 `YouTube Factory Poster`
   - **App icon / Category / Description**: 用途（自社コンテンツの自動投稿）を記述。
   - **Terms of Service URL / Privacy Policy URL**: 審査で**必須**。
     簡単な静的ページでよいので用意する（Vercel に置いてもよい）。
4. **Products** に以下を追加:
   - **Login Kit**（OAuth 認証用）
   - **Content Posting API**（投稿用）
5. **Scopes** に以下を追加:
   - `user.info.basic`
   - `video.publish` ← Direct Post（自動公開）に必須
   - `video.upload` ← Inbox 投稿（手動公開）用、保険で付けておく
6. **Login Kit の Redirect URI** に以下を**両方**登録:
   ```
   https://youtube-factory-eight.vercel.app/oauth/tiktok/callback
   http://localhost:3000/oauth/tiktok/callback
   ```
   > Redirect URI が 1 文字でも違うと `redirect_uri` エラーになります。末尾スラッシュ無しで正確に。
7. 保存すると **Client key** と **Client secret** が発行されます。これを控えておく。

---

## 3. （任意）Content Posting API の "Direct Post" を有効化

Content Posting API のページで **Direct Post** 機能を有効にします。
未審査でも Direct Post 自体は使えますが、**投稿は SELF_ONLY（非公開）に強制**されます。

未審査クライアントの制限（2026 時点）:
- 投稿は全て **SELF_ONLY（本人のみ閲覧可）**。
- 投稿に使えるユーザーは **24 時間で最大 5 人**まで。
- 連携アカウントは投稿時点で**非公開設定**である必要がある場合あり。

---

## 4. YouTube Factory に連携する

1. YouTube Factory を開き、対象チャンネルの **設定（config）** ページへ。
2. **「📱 TikTok 連携」** セクションを開く。
3. **🔧 TikTok クライアント情報** に、手順 2-7 で控えた
   **Client key** と **Client secret** を入力して保存。
4. **「🔗 TikTok と連携する」** を押すとポップアップで TikTok 認可画面が開く。
   - ⚠️ 連携は必ず **`https://youtube-factory-eight.vercel.app`** から行うこと
     （別の Vercel プレビュー URL から始めると Redirect URI 不一致になる）。本実装は
     自動で canonical ドメインへ誘導します。
5. 認可すると「✅ 連携完了: <アカウント名>」と表示されれば成功。

---

## 5. 自動投稿の設定

同じ「📱 TikTok 連携」セクション下部で設定します（**保存ボタンで反映**）:

- **自動投稿の投稿先**:
  - `YouTube のみ`（デフォルト）
  - `YouTube + TikTok 同時投稿`
  - `TikTok のみ`
- **TikTok 自動投稿を有効化**: ON にすると生成完了時に自動でショートを TikTok へ投稿。
- **公開範囲 (privacy_level)**:
  - 審査前は **`SELF_ONLY`（非公開）** にしておく（それ以外を選んでも API 側で SELF_ONLY に落ちます）。
  - **審査通過後**に `PUBLIC_TO_EVERYONE`（全員に公開）へ変更。
- **追加ハッシュタグ**: YouTube タグに加えて TikTok caption へ付与（例 `#fyp, #おすすめ`）。
- **コメント/デュエット/ステッチ無効**: 必要に応じて。

> 自動投稿は既存の「フルオート自動投稿（autopilot）」の生成完了フックに乗ります。
> ペア生成された**ショート動画**を TikTok に投稿します（TikTok は最大 600 秒のため、
> 12 分のフル動画ではなくショートを使用）。

---

## 6. 動作確認（手動アップロードでテスト）

連携後、バックエンドから手動でテスト投稿できます:

```bash
cd backend
python -m pipeline.tiktok_uploader \
  --channel daily-science \
  --video "/path/to/ショート.mp4" \
  --title "テスト投稿" \
  --hashtags "#fyp,#科学" \
  --privacy SELF_ONLY
```

成功すると `publish_id` と `status`（`PUBLISH_COMPLETE` 等）が表示されます。
TikTok アプリの「自分だけに表示」投稿として確認できます。

---

## 7. アプリ審査（audit）を申請して一般公開を解禁

非公開投稿で動作確認できたら、一般公開のために審査を申請します。

1. TikTok for Developers のアプリページから **Submit for review**（審査申請）。
2. 求められる主な準備:
   - **Terms of Service / Privacy Policy** の URL。
   - アプリの用途説明、**投稿フローのデモ動画**（OAuth → 投稿までの画面録画が有効）。
   - 実際に運用している TikTok アカウント（手動投稿実績があると良い）。
3. **審査期間は 2〜4 週間**、複数回のフィードバック往復があることが多い。
4. 審査通過後:
   - YouTube Factory の TikTok 設定で **公開範囲を `PUBLIC_TO_EVERYONE`** に変更。
   - 以降の自動投稿が一般公開されます。

---

## 付録 A: 環境変数（任意）

チャンネル別 UI から Client key/secret を保存するのが基本ですが、
共通クライアントを使う場合は `backend/.env` に設定してフォールバックできます:

```bash
TIKTOK_CLIENT_KEY=awxxxxxxxxxxxxx
TIKTOK_CLIENT_SECRET=xxxxxxxxxxxxxxxx
```

トークンは `data/tiktok_tokens.db` に `JWT_SECRET` 由来の Fernet で暗号化保存されます
（YouTube と同じ方式）。

---

## 付録 B: トラブルシューティング

| 症状 | 原因 / 対処 |
|------|-------------|
| `redirect_uri` エラー | TikTok 側の Redirect URI 登録と完全一致していない。canonical ドメインから連携する |
| 連携できるが Direct Post 不可 | `video.publish` スコープ未付与。Developer ポータルでスコープ追加 → 再連携 |
| 投稿が常に非公開 | **未審査アプリの仕様**。審査通過まで SELF_ONLY 固定 |
| `creator_info 取得失敗` | アクセストークン失効。再連携、または refresh の確認 |
| `video/init 失敗` | 動画が仕様外（尺/サイズ/コーデック）。MP4 H.264 / 3〜600秒 を確認 |
| `requests 未インストール` | `pip install requests`（backend/requirements.txt に追記済み） |

---

## 付録 C: 実装ファイル（開発者向け）

| 役割 | ファイル |
|------|----------|
| OAuth（チャンネル別トークン管理） | `backend/pipeline/tiktok_oauth.py` |
| 動画アップロード（Content Posting API） | `backend/pipeline/tiktok_uploader.py` |
| API エンドポイント | `backend/api_phase3.py`（`/api/channels/{id}/tiktok/*`） |
| 自動投稿フック | `backend/api_phase4.py`（`_start_tiktok_publish` / `on_generation_complete`） |
| チャンネル設定スキーマ | `backend/channels/channel_manager.py`（`tiktok` / `publish_targets`） |
| 連携 UI | `frontend/src/components/ChannelTiktokConnect.tsx` |
| 設定 UI | `frontend/src/app/channels/[id]/config/ConfigEditor.tsx` |
| OAuth コールバック | `frontend/src/app/oauth/tiktok/callback/page.tsx` |
| API プロキシ | `frontend/src/app/api/channels/[id]/tiktok/*` |
