"""
YouTube OAuth 2.0 ヘルパ — Phase 3

Web ベースの OAuth フロー：
  1. /api/youtube/auth-url で認証URLを生成
  2. ユーザーがGoogleで認可
  3. /api/youtube/callback で `code` をトークンに交換
  4. SQLite に Fernet で暗号化して保存

トークンは自動リフレッシュ。OAuth クライアント情報は settings/api_settings.json に保存。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ── 依存（任意）──
try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    from google.oauth2.credentials import Credentials  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore
    from google_auth_oauthlib.flow import Flow  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

# ── 定数 ──
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "youtube_tokens.db"
SETTINGS_FILE = Path(__file__).parent / "credentials" / "api_settings.json"


# =====================================================================
# 暗号化キー
# =====================================================================

def _fernet_key() -> bytes:
    """JWT_SECRET から導出。32 byte url-safe base64."""
    import base64
    import hashlib

    secret = os.environ.get("JWT_SECRET", "") or os.environ.get(
        "APP_PASSWORD_HASH", ""
    ) or "ytf-default-secret"
    h = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


def _encrypt(plaintext: str) -> str:
    if not HAS_CRYPTO:
        # フォールバック：base64（暗号化ではない、警告ログ）
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

def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY,
            account_email TEXT,
            token_data TEXT NOT NULL,
            expires_at INTEGER,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_state (
            state TEXT PRIMARY KEY,
            redirect_uri TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def save_credentials(creds_dict: Dict[str, Any], account_email: Optional[str] = None) -> None:
    """Credentials を暗号化して保存（id=1 固定で1ユーザー想定）"""
    payload = json.dumps(creds_dict)
    enc = _encrypt(payload)
    expires_at = int(creds_dict.get("expiry", 0)) if creds_dict.get("expiry") else None
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM oauth_tokens WHERE id = 1")
        conn.execute(
            "INSERT INTO oauth_tokens (id, account_email, token_data, expires_at, updated_at) "
            "VALUES (1, ?, ?, ?, ?)",
            (account_email, enc, expires_at, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def load_credentials_dict() -> Optional[Dict[str, Any]]:
    if not DB_PATH.exists():
        return None
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT token_data, account_email FROM oauth_tokens WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        plaintext = _decrypt(row[0])
        d = json.loads(plaintext)
        d["_account_email"] = row[1]
        return d
    except Exception:
        return None


def clear_credentials() -> None:
    if DB_PATH.exists():
        conn = _ensure_db()
        try:
            conn.execute("DELETE FROM oauth_tokens")
            conn.commit()
        finally:
            conn.close()


def save_state(state: str, redirect_uri: str) -> None:
    """CSRF 対策：認可開始時の state を保存。10分で失効。"""
    conn = _ensure_db()
    try:
        conn.execute(
            "DELETE FROM oauth_state WHERE created_at < ?",
            (int(time.time()) - 600,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO oauth_state (state, redirect_uri, created_at) VALUES (?, ?, ?)",
            (state, redirect_uri, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def consume_state(state: str) -> Optional[str]:
    """state を検証して redirect_uri を返す（消費）"""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT redirect_uri FROM oauth_state WHERE state = ? AND created_at >= ?",
            (state, int(time.time()) - 600),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
            conn.commit()
            return row[0]
    finally:
        conn.close()
    return None


# =====================================================================
# OAuth クライアント情報（client_id / client_secret）
# =====================================================================

def _load_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(s: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(s, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_oauth_client() -> Optional[Dict[str, str]]:
    """環境変数 or 設定ファイルから client_id / client_secret を取得"""
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if cid and csec:
        return {"client_id": cid, "client_secret": csec}
    s = _load_settings()
    cid = s.get("youtube_client_id", "")
    csec = s.get("youtube_client_secret", "")
    if cid and csec:
        return {"client_id": cid, "client_secret": csec}
    return None


def set_oauth_client(client_id: str, client_secret: str) -> None:
    s = _load_settings()
    s["youtube_client_id"] = client_id
    s["youtube_client_secret"] = client_secret
    _save_settings(s)


# =====================================================================
# Flow / Credentials
# =====================================================================

def _build_flow(redirect_uri: str) -> "Flow":
    if not HAS_GOOGLE:
        raise RuntimeError(
            "google-auth-oauthlib がインストールされていません: "
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )
    cfg = get_oauth_client()
    if not cfg:
        raise RuntimeError(
            "YouTube OAuth クライアント (client_id / client_secret) が未設定です。"
            "設定画面から登録してください。"
        )
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri
    )
    return flow


def build_auth_url(redirect_uri: str) -> Dict[str, str]:
    """認可URL生成。state も返す。"""
    flow = _build_flow(redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # refresh_token を確実に得る
    )
    save_state(state, redirect_uri)
    return {"auth_url": auth_url, "state": state}


def exchange_code(state: str, code: str) -> Dict[str, Any]:
    """コードをトークンに交換して保存。"""
    redirect_uri = consume_state(state)
    if not redirect_uri:
        raise RuntimeError("Invalid or expired state")
    flow = _build_flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # アカウントメール取得（取得失敗しても致命的ではない）
    email = None
    try:
        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
        email = info.get("email")
    except Exception:
        pass

    creds_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
    }
    save_credentials(creds_dict, account_email=email)
    return {"connected": True, "account_email": email}


def get_credentials() -> Optional["Credentials"]:
    """保存済み creds を Credentials 化し、必要ならリフレッシュ。"""
    if not HAS_GOOGLE:
        return None
    d = load_credentials_dict()
    if not d:
        return None
    from datetime import datetime

    expiry = d.get("expiry")
    expiry_dt = datetime.fromtimestamp(expiry) if expiry else None
    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=d.get("scopes", SCOPES),
        expiry=expiry_dt,
    )
    if not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
            d["token"] = creds.token
            d["expiry"] = int(creds.expiry.timestamp()) if creds.expiry else None
            save_credentials(d, account_email=d.get("_account_email"))
        except Exception:
            return None
    return creds


def is_connected() -> bool:
    return get_credentials() is not None


def get_status() -> Dict[str, Any]:
    """設定画面用: 接続状態 + アカウント情報"""
    d = load_credentials_dict()
    cfg = get_oauth_client()
    return {
        "connected": is_connected() if d else False,
        "account_email": d.get("_account_email") if d else None,
        "scopes": d.get("scopes", []) if d else [],
        "client_configured": cfg is not None,
        "client_id_preview": (
            f"{cfg['client_id'][:12]}...{cfg['client_id'][-12:]}"
            if cfg and len(cfg["client_id"]) > 24
            else (cfg["client_id"] if cfg else "")
        ),
        "google_libs_installed": HAS_GOOGLE,
        "crypto_installed": HAS_CRYPTO,
    }
