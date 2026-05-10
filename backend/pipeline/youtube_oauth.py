"""
YouTube OAuth 2.0 ヘルパ — チャンネル別連携

各チャンネル（内部 channel_id 単位）で独立した OAuth フローを持つ:
  1. /api/channels/{channel_id}/youtube/auth で認証URLを生成
  2. ユーザーがGoogleで認可
  3. /api/channels/{channel_id}/youtube/callback で `code` をトークンに交換
  4. SQLite に Fernet で暗号化して保存

Client ID / Client Secret もチャンネル別に保存。

レガシー（id=1 固定の旧テーブル）は起動時に DEFAULT_CHANNEL_ID へ自動移行。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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

# 既存の id=1 グローバルトークンを移行する先のチャンネルID
DEFAULT_CHANNEL_ID = "daily-science"


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

    # ── oauth_tokens: 旧スキーマ（id INTEGER PK）を新スキーマ（channel_id TEXT PK）に移行 ──
    cols = _table_columns(conn, "oauth_tokens")
    if cols and "channel_id" not in cols and "id" in cols:
        # 旧データを退避
        legacy_rows: List[tuple] = []
        try:
            legacy_rows = conn.execute(
                "SELECT id, account_email, token_data, expires_at, updated_at "
                "FROM oauth_tokens"
            ).fetchall()
        except Exception:
            legacy_rows = []
        conn.execute("DROP TABLE oauth_tokens")
        conn.execute(
            """
            CREATE TABLE oauth_tokens (
                channel_id TEXT PRIMARY KEY,
                account_email TEXT,
                youtube_channel_id TEXT,
                youtube_channel_name TEXT,
                token_data TEXT NOT NULL,
                expires_at INTEGER,
                updated_at INTEGER NOT NULL
            )
            """
        )
        # id=1 の行は DEFAULT_CHANNEL_ID に紐付けて移行
        for old_id, email, token_data, expires_at, updated_at in legacy_rows:
            target_channel = DEFAULT_CHANNEL_ID if old_id == 1 else f"legacy-{old_id}"
            conn.execute(
                "INSERT OR REPLACE INTO oauth_tokens "
                "(channel_id, account_email, token_data, expires_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (target_channel, email, token_data, expires_at, updated_at),
            )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                channel_id TEXT PRIMARY KEY,
                account_email TEXT,
                youtube_channel_id TEXT,
                youtube_channel_name TEXT,
                token_data TEXT NOT NULL,
                expires_at INTEGER,
                updated_at INTEGER NOT NULL
            )
            """
        )
        # 既存テーブルでも youtube_channel_* カラムが無ければ追加
        cols = _table_columns(conn, "oauth_tokens")
        if "youtube_channel_id" not in cols:
            try:
                conn.execute("ALTER TABLE oauth_tokens ADD COLUMN youtube_channel_id TEXT")
            except Exception:
                pass
        if "youtube_channel_name" not in cols:
            try:
                conn.execute("ALTER TABLE oauth_tokens ADD COLUMN youtube_channel_name TEXT")
            except Exception:
                pass

    # ── oauth_state: channel_id / code_verifier を追加 ──
    state_cols = _table_columns(conn, "oauth_state")
    if not state_cols:
        conn.execute(
            """
            CREATE TABLE oauth_state (
                state TEXT PRIMARY KEY,
                channel_id TEXT,
                redirect_uri TEXT NOT NULL,
                code_verifier TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
    else:
        if "channel_id" not in state_cols:
            try:
                conn.execute("ALTER TABLE oauth_state ADD COLUMN channel_id TEXT")
            except Exception:
                pass
        if "code_verifier" not in state_cols:
            try:
                conn.execute("ALTER TABLE oauth_state ADD COLUMN code_verifier TEXT")
            except Exception:
                pass

    # ── oauth_clients: チャンネル別 client_id/secret ──
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_clients (
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

def save_credentials_for(
    channel_id: str,
    creds_dict: Dict[str, Any],
    account_email: Optional[str] = None,
    youtube_channel_id: Optional[str] = None,
    youtube_channel_name: Optional[str] = None,
) -> None:
    """指定チャンネルの Credentials を暗号化保存。"""
    if not channel_id:
        raise ValueError("channel_id is required")
    payload = json.dumps(creds_dict)
    enc = _encrypt(payload)
    expires_at = int(creds_dict.get("expiry", 0)) if creds_dict.get("expiry") else None
    conn = _ensure_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens "
            "(channel_id, account_email, youtube_channel_id, youtube_channel_name, "
            " token_data, expires_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                channel_id,
                account_email,
                youtube_channel_id,
                youtube_channel_name,
                enc,
                expires_at,
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_credentials_dict_for(channel_id: str) -> Optional[Dict[str, Any]]:
    if not DB_PATH.exists() or not channel_id:
        return None
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT token_data, account_email, youtube_channel_id, youtube_channel_name "
            "FROM oauth_tokens WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        plaintext = _decrypt(row[0])
        d = json.loads(plaintext)
        d["_account_email"] = row[1]
        d["_youtube_channel_id"] = row[2]
        d["_youtube_channel_name"] = row[3]
        return d
    except Exception:
        return None


def clear_credentials_for(channel_id: str) -> None:
    if not DB_PATH.exists() or not channel_id:
        return
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM oauth_tokens WHERE channel_id = ?", (channel_id,))
        conn.commit()
    finally:
        conn.close()


def list_connected_channels() -> List[Dict[str, Any]]:
    """連携済み全チャンネルの簡易情報を返す。"""
    if not DB_PATH.exists():
        return []
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT channel_id, account_email, youtube_channel_id, youtube_channel_name, updated_at "
            "FROM oauth_tokens"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "channel_id": r[0],
            "account_email": r[1],
            "youtube_channel_id": r[2],
            "youtube_channel_name": r[3],
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
            "DELETE FROM oauth_state WHERE created_at < ?",
            (int(time.time()) - 600,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO oauth_state "
            "(state, channel_id, redirect_uri, code_verifier, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (state, channel_id, redirect_uri, code_verifier, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def consume_state(state: str) -> Optional[Dict[str, Optional[str]]]:
    """state を検証して (redirect_uri, channel_id, code_verifier) を返す（消費）。"""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT redirect_uri, channel_id, code_verifier FROM oauth_state "
            "WHERE state = ? AND created_at >= ?",
            (state, int(time.time()) - 600),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM oauth_state WHERE state = ?", (state,))
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

def _load_legacy_settings() -> Dict[str, Any]:
    """旧 api_settings.json のクライアント情報（後方互換）。"""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_legacy_settings(s: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(s, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_oauth_client_for(channel_id: str) -> Optional[Dict[str, str]]:
    """チャンネル別 client_id/client_secret を取得。
    未設定時はレガシー（環境変数 / 設定ファイル）にフォールバック。"""
    if channel_id:
        conn = _ensure_db()
        try:
            row = conn.execute(
                "SELECT client_data FROM oauth_clients WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        finally:
            conn.close()
        if row:
            try:
                d = json.loads(_decrypt(row[0]))
                if d.get("client_id") and d.get("client_secret"):
                    return {
                        "client_id": d["client_id"],
                        "client_secret": d["client_secret"],
                    }
            except Exception:
                pass
    # レガシー（環境変数 / 設定ファイル）
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    if cid and csec:
        return {"client_id": cid, "client_secret": csec}
    s = _load_legacy_settings()
    cid = s.get("youtube_client_id", "")
    csec = s.get("youtube_client_secret", "")
    if cid and csec:
        return {"client_id": cid, "client_secret": csec}
    return None


def set_oauth_client_for(channel_id: str, client_id: str, client_secret: str) -> None:
    if not channel_id:
        raise ValueError("channel_id is required")
    payload = json.dumps({"client_id": client_id, "client_secret": client_secret})
    enc = _encrypt(payload)
    conn = _ensure_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_clients "
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
        conn.execute("DELETE FROM oauth_clients WHERE channel_id = ?", (channel_id,))
        conn.commit()
    finally:
        conn.close()


# =====================================================================
# Flow / Credentials（チャンネル別）
# =====================================================================

def _build_flow_for(channel_id: str, redirect_uri: str) -> "Flow":
    if not HAS_GOOGLE:
        raise RuntimeError(
            "google-auth-oauthlib がインストールされていません: "
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )
    cfg = get_oauth_client_for(channel_id)
    if not cfg:
        raise RuntimeError(
            "YouTube OAuth クライアント (client_id / client_secret) が未設定です。"
            "チャンネル設定画面から登録してください。"
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


def build_auth_url_for(channel_id: str, redirect_uri: str) -> Dict[str, str]:
    """指定チャンネル用の認可URLを生成（PKCE 対応）。"""
    flow = _build_flow_for(channel_id, redirect_uri)
    flow.autogenerate_code_verifier = True
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    save_state(
        state,
        redirect_uri,
        channel_id=channel_id,
        code_verifier=getattr(flow, "code_verifier", None),
    )
    return {"auth_url": auth_url, "state": state}


def _fetch_account_info(creds) -> Dict[str, Optional[str]]:
    info: Dict[str, Optional[str]] = {
        "email": None,
        "youtube_channel_id": None,
        "youtube_channel_name": None,
    }
    try:
        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        u = svc.userinfo().get().execute()
        info["email"] = u.get("email")
    except Exception:
        pass
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        ch = yt.channels().list(part="snippet", mine=True).execute()
        items = ch.get("items", [])
        if items:
            info["youtube_channel_id"] = items[0]["id"]
            info["youtube_channel_name"] = items[0].get("snippet", {}).get("title")
    except Exception:
        pass
    return info


def exchange_code_for(channel_id: str, state: str, code: str) -> Dict[str, Any]:
    """state を検証し、code をトークン化して指定チャンネルに保存。
    state には認証開始時の channel_id が紐付いており、引数 channel_id と一致しない場合はエラー。"""
    info = consume_state(state)
    if not info:
        raise RuntimeError("Invalid or expired state")
    redirect_uri = info["redirect_uri"]
    state_channel = info.get("channel_id")
    if state_channel and channel_id and state_channel != channel_id:
        raise RuntimeError(
            f"state の channel_id ({state_channel}) と要求 ({channel_id}) が一致しません"
        )
    target_channel = channel_id or state_channel
    if not target_channel:
        raise RuntimeError("channel_id を解決できませんでした")

    flow = _build_flow_for(target_channel, redirect_uri)
    code_verifier = info.get("code_verifier")
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials

    acc = _fetch_account_info(creds)
    creds_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
    }
    save_credentials_for(
        target_channel,
        creds_dict,
        account_email=acc.get("email"),
        youtube_channel_id=acc.get("youtube_channel_id"),
        youtube_channel_name=acc.get("youtube_channel_name"),
    )
    return {
        "connected": True,
        "channel_id": target_channel,
        "account_email": acc.get("email"),
        "youtube_channel_id": acc.get("youtube_channel_id"),
        "youtube_channel_name": acc.get("youtube_channel_name"),
    }


def get_credentials_for(channel_id: str) -> Optional["Credentials"]:
    """指定チャンネルの Credentials。期限切れなら自動リフレッシュ。"""
    if not HAS_GOOGLE or not channel_id:
        return None
    d = load_credentials_dict_for(channel_id)
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
            save_credentials_for(
                channel_id,
                {k: v for k, v in d.items() if not k.startswith("_")},
                account_email=d.get("_account_email"),
                youtube_channel_id=d.get("_youtube_channel_id"),
                youtube_channel_name=d.get("_youtube_channel_name"),
            )
        except Exception:
            return None
    return creds


def is_connected_for(channel_id: str) -> bool:
    return get_credentials_for(channel_id) is not None


def get_status_for(channel_id: str) -> Dict[str, Any]:
    """指定チャンネルの接続状態。"""
    d = load_credentials_dict_for(channel_id) if channel_id else None
    cfg = get_oauth_client_for(channel_id) if channel_id else None
    return {
        "channel_id": channel_id,
        "connected": is_connected_for(channel_id) if d else False,
        "account_email": d.get("_account_email") if d else None,
        "youtube_channel_id": d.get("_youtube_channel_id") if d else None,
        "youtube_channel_name": d.get("_youtube_channel_name") if d else None,
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


# =====================================================================
# レガシー API（既存 Settings 画面用 — DEFAULT_CHANNEL_ID で動作）
# =====================================================================

def save_credentials(creds_dict: Dict[str, Any], account_email: Optional[str] = None) -> None:
    """レガシー: DEFAULT_CHANNEL_ID 配下に保存。"""
    save_credentials_for(DEFAULT_CHANNEL_ID, creds_dict, account_email=account_email)


def load_credentials_dict() -> Optional[Dict[str, Any]]:
    """レガシー: 連携済みチャンネルのうち先頭、もしくは DEFAULT_CHANNEL_ID。"""
    d = load_credentials_dict_for(DEFAULT_CHANNEL_ID)
    if d:
        return d
    rows = list_connected_channels()
    if rows:
        return load_credentials_dict_for(rows[0]["channel_id"])
    return None


def clear_credentials() -> None:
    """レガシー: DEFAULT_CHANNEL_ID のみ解除（全削除はしない）。"""
    clear_credentials_for(DEFAULT_CHANNEL_ID)


def get_credentials() -> Optional["Credentials"]:
    creds = get_credentials_for(DEFAULT_CHANNEL_ID)
    if creds:
        return creds
    rows = list_connected_channels()
    for r in rows:
        c = get_credentials_for(r["channel_id"])
        if c:
            return c
    return None


def is_connected() -> bool:
    return get_credentials() is not None


def get_oauth_client() -> Optional[Dict[str, str]]:
    """レガシー: DEFAULT_CHANNEL_ID の client、無ければ環境変数/設定ファイル。"""
    return get_oauth_client_for(DEFAULT_CHANNEL_ID)


def set_oauth_client(client_id: str, client_secret: str) -> None:
    """レガシー: DEFAULT_CHANNEL_ID と settings ファイルの両方に保存（後方互換）。"""
    set_oauth_client_for(DEFAULT_CHANNEL_ID, client_id, client_secret)
    s = _load_legacy_settings()
    s["youtube_client_id"] = client_id
    s["youtube_client_secret"] = client_secret
    _save_legacy_settings(s)


def build_auth_url(redirect_uri: str) -> Dict[str, str]:
    """レガシー: DEFAULT_CHANNEL_ID 用に発行。"""
    return build_auth_url_for(DEFAULT_CHANNEL_ID, redirect_uri)


def exchange_code(state: str, code: str) -> Dict[str, Any]:
    """レガシー: state に紐付くチャンネル（or DEFAULT_CHANNEL_ID）に保存。"""
    info = consume_state(state)
    if not info:
        raise RuntimeError("Invalid or expired state")
    target = info.get("channel_id") or DEFAULT_CHANNEL_ID
    redirect_uri = info["redirect_uri"]

    flow = _build_flow_for(target, redirect_uri)
    code_verifier = info.get("code_verifier")
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    acc = _fetch_account_info(creds)

    creds_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": int(creds.expiry.timestamp()) if creds.expiry else None,
    }
    save_credentials_for(
        target,
        creds_dict,
        account_email=acc.get("email"),
        youtube_channel_id=acc.get("youtube_channel_id"),
        youtube_channel_name=acc.get("youtube_channel_name"),
    )
    return {
        "connected": True,
        "channel_id": target,
        "account_email": acc.get("email"),
        "youtube_channel_id": acc.get("youtube_channel_id"),
        "youtube_channel_name": acc.get("youtube_channel_name"),
    }


def get_status() -> Dict[str, Any]:
    """レガシー: DEFAULT_CHANNEL_ID の状態を返す（後方互換）。"""
    return get_status_for(DEFAULT_CHANNEL_ID)
