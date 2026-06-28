"""
TikTok OAuth 2.0 ヘルパ — チャンネル別連携

YouTube (`youtube_oauth.py`) と同じ設計思想で、各チャンネル（内部 channel_id 単位）が
独立した TikTok OAuth フローを持つ:
  1. /api/channels/{channel_id}/tiktok/auth で認可URLを生成
  2. ユーザーが TikTok で認可
  3. /api/channels/{channel_id}/tiktok/callback で `code` をトークンに交換
  4. SQLite に Fernet で暗号化して保存

Client Key / Client Secret もチャンネル別に保存。

TikTok OAuth v2 の仕様:
  - 認可URL:   https://www.tiktok.com/v2/auth/authorize/
  - トークン:  POST https://open.tiktokapis.com/v2/oauth/token/  (x-www-form-urlencoded)
  - リフレッシュ: 同上 (grant_type=refresh_token)
  - 失効:      POST https://open.tiktokapis.com/v2/oauth/revoke/
  - access_token は 24h、refresh_token は 365日有効。
  - パラメータ名は `client_key` / `client_secret`（YouTube の client_id とは異なる）。

注: 暗号化キーは YouTube と同じ JWT_SECRET 由来 Fernet を流用する。
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 依存（任意）──
try:
    from cryptography.fernet import Fernet  # type: ignore
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── 定数 ──
# Direct Post (video.publish) + Inbox (video.upload) + プロフィール表示 (user.info.basic)
SCOPES = ["user.info.basic", "video.publish", "video.upload"]

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "tiktok_tokens.db"

_HTTP_TIMEOUT = 30


# =====================================================================
# 暗号化キー（YouTube と同じ JWT_SECRET 由来 Fernet）
# =====================================================================

def _fernet_key() -> bytes:
    import base64
    import hashlib

    secret = os.environ.get("JWT_SECRET", "") or os.environ.get(
        "APP_PASSWORD_HASH", ""
    ) or "ytf-default-secret"
    h = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


def _encrypt(plaintext: str) -> str:
    if not HAS_CRYPTO:
        import base64
        return "B64:" + base64.b64encode(plaintext.encode("utf-8")).decode()
    f = Fernet(_fernet_key())
    return "F:" + f.encrypt(plaintext.encode("utf-8")).decode()


def _decrypt(ciphertext: str) -> str:
    if ciphertext.startswith("F:"):
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography がインストールされていません")
        f = Fernet(_fernet_key())
        return f.decrypt(ciphertext[2:].encode("utf-8")).decode()
    if ciphertext.startswith("B64:"):
        import base64
        return base64.b64decode(ciphertext[4:]).decode("utf-8")
    return ciphertext  # legacy plaintext


# =====================================================================
# DB
# =====================================================================

def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tiktok_tokens (
            channel_id TEXT PRIMARY KEY,
            open_id TEXT,
            display_name TEXT,
            username TEXT,
            token_data TEXT NOT NULL,
            expires_at INTEGER,
            refresh_expires_at INTEGER,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tiktok_state (
            state TEXT PRIMARY KEY,
            channel_id TEXT,
            redirect_uri TEXT NOT NULL,
            code_verifier TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tiktok_clients (
            channel_id TEXT PRIMARY KEY,
            client_data TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


# =====================================================================
# トークン保存（チャンネル別）
# =====================================================================

def save_token_for(
    channel_id: str,
    token: Dict[str, Any],
    open_id: Optional[str] = None,
    display_name: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    """指定チャンネルの TikTok トークンを暗号化保存。

    `token` には access_token / refresh_token / scope などを含む dict を渡す。
    expires_at / refresh_expires_at は token 内の expires_in / refresh_expires_in
    から絶対時刻 (epoch) を計算して保存する。
    """
    if not channel_id:
        raise ValueError("channel_id is required")
    now = int(time.time())
    expires_at = now + int(token.get("expires_in", 0)) if token.get("expires_in") else None
    refresh_expires_at = (
        now + int(token.get("refresh_expires_in", 0))
        if token.get("refresh_expires_in")
        else None
    )
    # 絶対時刻も dict に保存しておく（リフレッシュ時の判定で使う）
    payload = dict(token)
    payload["_expires_at"] = expires_at
    payload["_refresh_expires_at"] = refresh_expires_at
    enc = _encrypt(json.dumps(payload))
    conn = _ensure_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO tiktok_tokens "
            "(channel_id, open_id, display_name, username, token_data, "
            " expires_at, refresh_expires_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                channel_id,
                open_id or token.get("open_id"),
                display_name,
                username,
                enc,
                expires_at,
                refresh_expires_at,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_token_dict_for(channel_id: str) -> Optional[Dict[str, Any]]:
    if not DB_PATH.exists() or not channel_id:
        return None
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT token_data, open_id, display_name, username "
            "FROM tiktok_tokens WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        d = json.loads(_decrypt(row[0]))
        d["_open_id"] = row[1]
        d["_display_name"] = row[2]
        d["_username"] = row[3]
        return d
    except Exception:
        return None


def clear_credentials_for(channel_id: str) -> None:
    if not DB_PATH.exists() or not channel_id:
        return
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM tiktok_tokens WHERE channel_id = ?", (channel_id,))
        conn.commit()
    finally:
        conn.close()


def list_connected_channels() -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT channel_id, open_id, display_name, username, updated_at "
            "FROM tiktok_tokens"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "channel_id": r[0],
            "open_id": r[1],
            "display_name": r[2],
            "username": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


# =====================================================================
# state（CSRF 対策、チャンネルID紐付け）
# =====================================================================

def save_state(
    state: str,
    redirect_uri: str,
    channel_id: Optional[str] = None,
    code_verifier: Optional[str] = None,
) -> None:
    conn = _ensure_db()
    try:
        conn.execute(
            "DELETE FROM tiktok_state WHERE created_at < ?",
            (int(time.time()) - 600,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO tiktok_state "
            "(state, channel_id, redirect_uri, code_verifier, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (state, channel_id, redirect_uri, code_verifier, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def consume_state(state: str) -> Optional[Dict[str, Optional[str]]]:
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT redirect_uri, channel_id, code_verifier FROM tiktok_state "
            "WHERE state = ? AND created_at >= ?",
            (state, int(time.time()) - 600),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM tiktok_state WHERE state = ?", (state,))
            conn.commit()
            return {
                "redirect_uri": row[0],
                "channel_id": row[1],
                "code_verifier": row[2],
            }
    finally:
        conn.close()
    return None


# =====================================================================
# OAuth クライアント情報（チャンネル別）
# =====================================================================

def get_oauth_client_for(channel_id: str) -> Optional[Dict[str, str]]:
    """チャンネル別 client_key/client_secret を取得。
    未設定時は環境変数 (TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET) にフォールバック。"""
    if channel_id:
        conn = _ensure_db()
        try:
            row = conn.execute(
                "SELECT client_data FROM tiktok_clients WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        finally:
            conn.close()
        if row:
            try:
                d = json.loads(_decrypt(row[0]))
                if d.get("client_key") and d.get("client_secret"):
                    return {
                        "client_key": d["client_key"],
                        "client_secret": d["client_secret"],
                    }
            except Exception:
                pass
    cid = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    csec = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    if cid and csec:
        return {"client_key": cid, "client_secret": csec}
    return None


def set_oauth_client_for(channel_id: str, client_key: str, client_secret: str) -> None:
    if not channel_id:
        raise ValueError("channel_id is required")
    payload = json.dumps({"client_key": client_key, "client_secret": client_secret})
    enc = _encrypt(payload)
    conn = _ensure_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO tiktok_clients "
            "(channel_id, client_data, updated_at) VALUES (?, ?, ?)",
            (channel_id, enc, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def clear_oauth_client_for(channel_id: str) -> None:
    if not channel_id:
        return
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM tiktok_clients WHERE channel_id = ?", (channel_id,))
        conn.commit()
    finally:
        conn.close()


# =====================================================================
# 認可フロー
# =====================================================================

def build_auth_url_for(channel_id: str, redirect_uri: str) -> Dict[str, str]:
    """指定チャンネル用の TikTok 認可URLを生成。

    Web フロー（client_secret 保持）のため PKCE は必須ではないが、
    将来のデスクトップ対応に備え state のみ保存する。
    """
    cfg = get_oauth_client_for(channel_id)
    if not cfg:
        raise RuntimeError(
            "TikTok OAuth クライアント (client_key / client_secret) が未設定です。"
            "チャンネル設定画面から登録してください。"
        )
    state = secrets.token_urlsafe(24)
    save_state(state, redirect_uri, channel_id=channel_id)

    from urllib.parse import urlencode

    params = {
        "client_key": cfg["client_key"],
        "scope": ",".join(SCOPES),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


def _post_token(data: Dict[str, str]) -> Dict[str, Any]:
    if not HAS_REQUESTS:
        raise RuntimeError("requests がインストールされていません: pip install requests")
    resp = requests.post(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_HTTP_TIMEOUT,
    )
    try:
        body = resp.json()
    except Exception:
        raise RuntimeError(f"TikTok token endpoint が不正な応答: {resp.status_code} {resp.text[:300]}")
    # TikTok はエラーを {"error": "...", "error_description": "..."} で返す
    if body.get("error"):
        raise RuntimeError(
            f"TikTok OAuth エラー: {body.get('error')} - {body.get('error_description', '')}"
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"TikTok token endpoint HTTP {resp.status_code}: {resp.text[:300]}")
    return body


def _fetch_user_info(access_token: str) -> Dict[str, Optional[str]]:
    info: Dict[str, Optional[str]] = {"open_id": None, "display_name": None, "username": None}
    if not HAS_REQUESTS:
        return info
    try:
        resp = requests.get(
            USERINFO_URL,
            params={"fields": "open_id,display_name,username"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_HTTP_TIMEOUT,
        )
        data = (resp.json() or {}).get("data", {}).get("user", {})
        info["open_id"] = data.get("open_id")
        info["display_name"] = data.get("display_name")
        info["username"] = data.get("username")
    except Exception:
        pass
    return info


def exchange_code_for(channel_id: str, state: str, code: str) -> Dict[str, Any]:
    """state を検証し、code をトークン化して指定チャンネルに保存。"""
    info = consume_state(state)
    if not info:
        raise RuntimeError("Invalid or expired state")
    state_channel = info.get("channel_id")
    if state_channel and channel_id and state_channel != channel_id:
        raise RuntimeError(
            f"state の channel_id ({state_channel}) と要求 ({channel_id}) が一致しません"
        )
    target_channel = channel_id or state_channel
    if not target_channel:
        raise RuntimeError("channel_id を解決できませんでした")

    cfg = get_oauth_client_for(target_channel)
    if not cfg:
        raise RuntimeError("TikTok OAuth クライアントが未設定です")

    from urllib.parse import unquote

    token = _post_token(
        {
            "client_key": cfg["client_key"],
            "client_secret": cfg["client_secret"],
            "code": unquote(code),
            "grant_type": "authorization_code",
            "redirect_uri": info["redirect_uri"],
        }
    )

    user = _fetch_user_info(token.get("access_token", ""))
    save_token_for(
        target_channel,
        token,
        open_id=user.get("open_id") or token.get("open_id"),
        display_name=user.get("display_name"),
        username=user.get("username"),
    )
    return {
        "connected": True,
        "channel_id": target_channel,
        "open_id": user.get("open_id") or token.get("open_id"),
        "display_name": user.get("display_name"),
        "username": user.get("username"),
        "scope": token.get("scope"),
    }


def _refresh_token_for(channel_id: str, d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """refresh_token でアクセストークンを更新し、保存して返す。失敗時 None。"""
    cfg = get_oauth_client_for(channel_id)
    refresh_token = d.get("refresh_token")
    if not cfg or not refresh_token:
        return None
    try:
        token = _post_token(
            {
                "client_key": cfg["client_key"],
                "client_secret": cfg["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )
    except Exception as e:
        print(f"⚠️ TikTok token refresh failed for {channel_id}: {e}")
        return None
    save_token_for(
        channel_id,
        token,
        open_id=d.get("_open_id") or token.get("open_id"),
        display_name=d.get("_display_name"),
        username=d.get("_username"),
    )
    out = dict(token)
    out["_open_id"] = d.get("_open_id") or token.get("open_id")
    out["_display_name"] = d.get("_display_name")
    out["_username"] = d.get("_username")
    return out


def get_access_token_for(channel_id: str) -> Optional[str]:
    """指定チャンネルの有効な access_token を返す。期限切れ間際なら自動リフレッシュ。"""
    if not channel_id:
        return None
    d = load_token_dict_for(channel_id)
    if not d:
        return None
    expires_at = d.get("_expires_at")
    # 期限の 5 分前を切っていればリフレッシュ
    if expires_at and int(time.time()) >= int(expires_at) - 300:
        refreshed = _refresh_token_for(channel_id, d)
        if refreshed:
            d = refreshed
    return d.get("access_token")


def is_connected_for(channel_id: str) -> bool:
    return get_access_token_for(channel_id) is not None


def get_status_for(channel_id: str) -> Dict[str, Any]:
    """指定チャンネルの TikTok 接続状態。"""
    d = load_token_dict_for(channel_id) if channel_id else None
    cfg = get_oauth_client_for(channel_id) if channel_id else None
    scope = d.get("scope", "") if d else ""
    return {
        "channel_id": channel_id,
        "connected": is_connected_for(channel_id) if d else False,
        "open_id": d.get("_open_id") if d else None,
        "display_name": d.get("_display_name") if d else None,
        "username": d.get("_username") if d else None,
        "scopes": scope.split(",") if scope else [],
        # video.publish が無いと Direct Post 不可 → Inbox 投稿のみ
        "can_direct_post": "video.publish" in (scope or ""),
        "client_configured": cfg is not None,
        "client_key_preview": (
            f"{cfg['client_key'][:6]}...{cfg['client_key'][-4:]}"
            if cfg and len(cfg["client_key"]) > 10
            else (cfg["client_key"] if cfg else "")
        ),
        "requests_installed": HAS_REQUESTS,
        "crypto_installed": HAS_CRYPTO,
    }
