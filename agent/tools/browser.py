"""ブラウザ操作ツール（Playwright / headless Chromium）。

エージェントが YouTube Factory のフロント（Next.js, 既定 localhost:3000）を
人間と同じように操作するための手。ページ遷移・クリック・フォーム入力・スクショに
加え、高レベルの操作として「アプリへのログイン」「YouTube OAuth 再認証」を提供する。

設計の肝:
- **永続プロファイル**: launch_persistent_context で user_data_dir を固定する。
  これによりアプリのログインCookieと **Googleアカウントのセッション** がプロセスを
  跨いで残る。一度 Google にログインしておけば、以後の再認証はログイン/同意画面を
  再入力せずに進められる（headless でも完了しやすくなる）。
- **シングルトン**: 1 回の run の中でブラウザを 1 つだけ起動して使い回す。

環境変数:
- AGENT_APP_BASE_URL   : フロントのベースURL（既定 http://localhost:3000）
- AGENT_BROWSER_HEADLESS: "0" で画面ありモード（初回の Google ログインに使う）。既定 headless。
- APP_PASSWORD         : アプリのログインパスワード（backend/.env から bootstrap で読まれる）
- GOOGLE_ACCOUNT_EMAIL : 任意。OAuth のアカウント選択で優先的に選ぶメール。

注意: Playwright が未導入なら各ツールはインストール方法を案内して失敗する。
    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import atexit
import os
import time
from datetime import datetime

from ..config import STATE_DIR
from .base import Tool

_DEFAULT_BASE = "http://localhost:3000"
_PROFILE_DIR = STATE_DIR / "browser_profile"
_SHOTS_DIR = STATE_DIR / "screenshots"

_INSTALL_HINT = (
    "Playwright が未導入です。次を実行してください: "
    "`pip install playwright && playwright install chromium`"
)


def _base_url() -> str:
    return os.environ.get("AGENT_APP_BASE_URL", _DEFAULT_BASE).rstrip("/")


def _headless() -> bool:
    return os.environ.get("AGENT_BROWSER_HEADLESS", "1") != "0"


def _resolve_url(target: str) -> str:
    """フルURLならそのまま、そうでなければベースURLからの相対パスとして解決する。"""
    if target.startswith(("http://", "https://")):
        return target
    if not target.startswith("/"):
        target = "/" + target
    return _base_url() + target


# --- ブラウザ・セッション（シングルトン） -------------------------------
class _Browser:
    def __init__(self) -> None:
        self._pw = None
        self._ctx = None
        self._page = None

    def page(self):
        if self._page is None:
            self._start()
        return self._page

    @property
    def context(self):
        if self._ctx is None:
            self._start()
        return self._ctx

    def _start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError(_INSTALL_HINT) from e

        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _SHOTS_DIR.mkdir(parents=True, exist_ok=True)

        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            headless=_headless(),
            viewport={"width": 1280, "height": 900},
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        self._ctx.set_default_timeout(20_000)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def close(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._pw = self._ctx = self._page = None


_BROWSER = _Browser()
atexit.register(_BROWSER.close)


# --- 共通ユーティリティ -------------------------------------------------
def _shot(prefix: str = "shot") -> str:
    """現在ページのスクショを撮って保存パスを返す。失敗しても例外にしない。"""
    page = _BROWSER.page()
    _SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = _SHOTS_DIR / name
    try:
        page.screenshot(path=str(path))
        return str(path)
    except Exception:  # noqa: BLE001
        return ""


def _visible_text(page, max_chars: int) -> str:
    try:
        txt = page.inner_text("body")
    except Exception:  # noqa: BLE001
        txt = ""
    txt = "\n".join(line.rstrip() for line in txt.splitlines() if line.strip())
    if len(txt) > max_chars:
        txt = txt[:max_chars] + "\n…(以下省略)…"
    return txt


# --- 低レベルツール -----------------------------------------------------
def _browser_goto(url: str, wait_until: str = "load") -> dict:
    page = _BROWSER.page()
    full = _resolve_url(url)
    try:
        page.goto(full, wait_until=wait_until)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "url": full, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "url": page.url, "title": page.title()}


def _browser_observe(url: str | None = None, max_chars: int = 3000) -> dict:
    page = _BROWSER.page()
    if url:
        r = _browser_goto(url)
        if not r.get("ok"):
            return r
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "url": page.url,
        "title": page.title(),
        "visible_text": _visible_text(page, max_chars),
        "screenshot": _shot("observe"),
    }


def _browser_click(text: str | None = None, selector: str | None = None,
                   nth: int = 0) -> dict:
    page = _BROWSER.page()
    try:
        if selector:
            loc = page.locator(selector)
        elif text:
            # ボタン/リンク/任意要素の可視テキストで探す
            loc = page.get_by_text(text, exact=False)
        else:
            return {"ok": False, "error": "text または selector のどちらかが必要"}
        loc = loc.nth(nth)
        loc.scroll_into_view_if_needed(timeout=5000)
        loc.click(timeout=10_000)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "screenshot": _shot("click_fail")}
    return {"ok": True, "clicked": selector or text, "url": page.url}


def _browser_fill(selector: str, value: str) -> dict:
    page = _BROWSER.page()
    try:
        page.fill(selector, value, timeout=10_000)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "screenshot": _shot("fill_fail")}
    return {"ok": True, "filled": selector}


def _browser_screenshot(name: str | None = None, full_page: bool = False) -> dict:
    page = _BROWSER.page()
    _SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = (name or f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    if not fname.endswith(".png"):
        fname += ".png"
    path = _SHOTS_DIR / fname
    try:
        page.screenshot(path=str(path), full_page=full_page)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "path": str(path), "url": page.url}


# --- 高レベル: アプリへのログイン ---------------------------------------
def _app_login(password: str | None = None) -> dict:
    """YouTube Factory アプリにログインする（必要な場合のみ）。

    永続プロファイルのCookieが生きていれば何もせず already_logged_in を返す。
    """
    page = _BROWSER.page()
    pw = password or os.environ.get("APP_PASSWORD", "")
    # まずトップへ。未ログインなら /login にリダイレクトされる。
    r = _browser_goto("/")
    if not r.get("ok"):
        return r

    if "/login" not in page.url:
        return {"ok": True, "already_logged_in": True, "url": page.url}

    if not pw:
        return {"ok": False, "needs_human": True,
                "error": "ログインが必要だが APP_PASSWORD が未設定。"}

    try:
        page.fill("input#password, input[type=password]", pw, timeout=10_000)
        page.click("button[type=submit]", timeout=10_000)
        # /login から離れるのを待つ
        page.wait_for_function(
            "() => !location.pathname.startsWith('/login')", timeout=15_000)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"ログイン失敗: {type(e).__name__}: {e}",
                "screenshot": _shot("login_fail")}
    return {"ok": True, "logged_in": True, "url": page.url}


# --- 高レベル: Google 同意画面の自動前進（ベストエフォート） -------------
_GOOGLE_ADVANCE_TEXTS = ["続行", "Continue", "許可", "Allow", "次へ", "Next", "同意"]


def _advance_google(popup, rounds: int = 8) -> str:
    """Google のアカウント選択／同意画面を可能な範囲で自動で前に進める。

    自分の Google アカウントへの再認可を、人間と同じ操作で代行するだけ。
    戻り値: 到達した最終状態の説明文字列。
    """
    email = os.environ.get("GOOGLE_ACCOUNT_EMAIL", "").strip()
    for _ in range(rounds):
        try:
            url = popup.url
        except Exception:  # noqa: BLE001
            return "popup_closed"
        if "accounts.google.com" not in url and "oauth" not in url.lower():
            return "left_google"

        # アカウント選択: メール一致 or 唯一の候補をクリック
        try:
            if email:
                acct = popup.get_by_text(email, exact=False)
                if acct.count() > 0:
                    acct.first.click(timeout=4000)
                    popup.wait_for_timeout(1200)
                    continue
        except Exception:  # noqa: BLE001
            pass

        # 「続行 / 許可 / 次へ」などのボタンを押す
        advanced = False
        for label in _GOOGLE_ADVANCE_TEXTS:
            try:
                btn = popup.get_by_role("button", name=label)
                if btn.count() == 0:
                    btn = popup.get_by_text(label, exact=False)
                if btn.count() > 0:
                    btn.first.click(timeout=4000)
                    popup.wait_for_timeout(1200)
                    advanced = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if not advanced:
            # これ以上は自動で進めない（ログイン入力・2FA・パスワード等）
            return "stuck_needs_human"
    return "max_rounds"


# --- 高レベル: YouTube OAuth 再認証 -------------------------------------
def _youtube_reauth(channel_id: str, wait_seconds: int = 120) -> dict:
    """チャンネル設定画面から YouTube OAuth 連携をやり直す。

    フロントは window.open のポップアップで Google 認証を開き、コールバックを
    postMessage で受け取って /api/.../youtube/callback を叩く。ここではその一連を
    Playwright のポップアップ捕捉で自動化する。

    自動で完了できない場合（Google のログイン入力や 2FA が必要）は
    needs_human=True とスクショパスを返すので、エージェントは notify_user で人に上げる。
    headless だと入力系は触れないため、初回ログインは AGENT_BROWSER_HEADLESS=0 で
    一度通しておくと、以後は永続プロファイルで自動完了しやすくなる。
    """
    login = _app_login()
    if not login.get("ok"):
        return {"ok": False, "stage": "app_login", **login}

    page = _BROWSER.page()
    r = _browser_goto(f"/channels/{channel_id}/config")
    if not r.get("ok"):
        return {"ok": False, "stage": "open_config", **r}

    # 連携UIの描画待ち（接続/解除ボタンはどちらも「連携」を含む）
    try:
        page.wait_for_selector("button:has-text('連携')", timeout=10_000)
    except Exception:  # noqa: BLE001
        pass

    # 既に接続済み表示（ボタンが「連携を解除」）の場合
    try:
        if page.get_by_text("連携を解除", exact=False).count() > 0 and \
           page.get_by_text("YouTube と連携する", exact=False).count() == 0:
            return {
                "ok": True, "already_connected": True, "channel_id": channel_id,
                "note": ("UI上は接続済み表示。トークンが実際に失効している場合は、"
                         "このボタンからは再認証できない（解除すると client_id/secret も消える）。"
                         "observe_post_status で実際の有効性を確認し、失効なら手動の解除→再連携が必要。"),
                "screenshot": _shot("reauth_connected"),
            }
    except Exception:  # noqa: BLE001
        pass

    # 「YouTube と連携する」ボタンを押し、開くポップアップを捕捉
    try:
        connect = page.get_by_text("YouTube と連携する", exact=False).first
        with _BROWSER.context.expect_page(timeout=15_000) as pop_info:
            connect.click(timeout=10_000)
        popup = pop_info.value
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "click_connect",
                "error": f"{type(e).__name__}: {e}",
                "hint": "client_id/secret 未設定だとボタンが無効。先にUIでクライアント情報を保存する必要があるかも。",
                "screenshot": _shot("reauth_noclick")}

    try:
        popup.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:  # noqa: BLE001
        pass

    # Google 側を可能な範囲で前進させる
    google_state = _advance_google(popup)

    # 親ページが「接続済」に変わる or 「連携完了」が出るのを待つ
    deadline = time.time() + wait_seconds
    last_popup_url = ""
    while time.time() < deadline:
        try:
            if page.get_by_text("接続済", exact=False).count() > 0 or \
               page.get_by_text("連携完了", exact=False).count() > 0:
                return {"ok": True, "channel_id": channel_id, "reauthorized": True,
                        "google_state": google_state, "url": page.url,
                        "screenshot": _shot("reauth_ok")}
        except Exception:  # noqa: BLE001
            pass

        popup_closed = False
        try:
            last_popup_url = popup.url
        except Exception:  # noqa: BLE001
            popup_closed = True

        if popup_closed:
            # ポップアップが閉じた＝コールバック完了の可能性。状態を再取得。
            try:
                page.reload()
                page.wait_for_timeout(1500)
                if page.get_by_text("接続済", exact=False).count() > 0:
                    return {"ok": True, "channel_id": channel_id, "reauthorized": True,
                            "google_state": google_state, "screenshot": _shot("reauth_ok")}
            except Exception:  # noqa: BLE001
                pass
            break

        # Google でログイン入力等が必要で止まっている
        if google_state == "stuck_needs_human":
            break
        time.sleep(2)

    # ここに来たら自動完了できなかった
    popup_shot = ""
    try:
        popup_shot = str(_SHOTS_DIR / f"reauth_popup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        popup.screenshot(path=popup_shot)
    except Exception:  # noqa: BLE001
        popup_shot = ""

    return {
        "ok": False, "needs_human": True, "channel_id": channel_id,
        "google_state": google_state, "popup_url": last_popup_url,
        "error": ("Google 認証を自動完了できなかった（ログイン入力/2FA/同意が必要）。"
                  "AGENT_BROWSER_HEADLESS=0 で一度手動ログインを通すか、UIで再認証してください。"),
        "popup_screenshot": popup_shot,
        "page_screenshot": _shot("reauth_stuck"),
    }


# ======================================================================
# Tool 定義
# ======================================================================
_CHANNEL_ENUM = {"type": "string", "enum": ["scp-lab", "daily-science"]}

BROWSER_GOTO_TOOL = Tool(
    name="browser_goto",
    description=(
        "ブラウザでページを開く。url はアプリ内パス（例 '/settings', '/channels/scp-lab/config'）でも"
        "フルURL（例 'https://studio.youtube.com'）でもよい。開いた後の url と title を返す。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "アプリ内パス or フルURL"},
            "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"]},
        },
        "required": ["url"],
    },
    func=_browser_goto,
    safe_in_dry_run=True,
)

BROWSER_OBSERVE_TOOL = Tool(
    name="browser_observe",
    description=(
        "現在（または url 指定時はそのページ）の状態を観測する。url・title・可視テキスト・"
        "スクリーンショットの保存パスを返す。ページの状態確認はまずこれを使う。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "省略可。指定すると先に遷移してから観測する"},
            "max_chars": {"type": "integer", "description": "可視テキストの最大文字数（既定3000）"},
        },
    },
    func=_browser_observe,
    safe_in_dry_run=True,
)

BROWSER_CLICK_TOOL = Tool(
    name="browser_click",
    description=(
        "要素をクリックする。可視テキスト（text）かCSSセレクタ（selector）のどちらかで指定。"
        "同じ条件に複数該当するときは nth（0始まり）で選ぶ。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "ボタン/リンク等の可視テキスト（部分一致）"},
            "selector": {"type": "string", "description": "CSSセレクタ（text より優先）"},
            "nth": {"type": "integer", "description": "複数該当時のインデックス（既定0）"},
        },
    },
    func=_browser_click,
)

BROWSER_FILL_TOOL = Tool(
    name="browser_fill",
    description="入力欄（CSSセレクタで指定）にテキストを入力する。",
    input_schema={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "入力欄のCSSセレクタ"},
            "value": {"type": "string"},
        },
        "required": ["selector", "value"],
    },
    func=_browser_fill,
)

BROWSER_SCREENSHOT_TOOL = Tool(
    name="browser_screenshot",
    description="現在ページのスクリーンショットを保存し、パスを返す。full_page で全体を撮る。",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "ファイル名（省略時は自動）"},
            "full_page": {"type": "boolean"},
        },
    },
    func=_browser_screenshot,
    safe_in_dry_run=True,
)

APP_LOGIN_TOOL = Tool(
    name="app_login",
    description=(
        "YouTube Factory アプリにログインする（必要な場合のみ／APP_PASSWORD を使用）。"
        "永続プロファイルにセッションが残っていれば already_logged_in を返す。"
        "他のブラウザ操作の前に呼んでおくとよい。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "password": {"type": "string", "description": "省略時は環境変数 APP_PASSWORD"},
        },
    },
    func=_app_login,
    safe_in_dry_run=True,
)

YOUTUBE_REAUTH_TOOL = Tool(
    name="youtube_reauth",
    description=(
        "ブラウザでチャンネル設定画面を開き、YouTube OAuth 連携をやり直す（最重要ユースケース）。"
        "Google セッションが永続プロファイルに残っていれば自動完了する。ログイン入力や2FAが必要な"
        "場合は needs_human=True とスクショを返すので notify_user で人に上げること。"
        "refresh_youtube_token が失敗したとき（refresh_token 失効）にこれを試す。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "channel_id": _CHANNEL_ENUM,
            "wait_seconds": {"type": "integer", "description": "認証完了を待つ秒数（既定120）"},
        },
        "required": ["channel_id"],
    },
    func=_youtube_reauth,
)

# objective から import しやすいようにまとめておく
BROWSER_TOOLS = [
    BROWSER_GOTO_TOOL,
    BROWSER_OBSERVE_TOOL,
    BROWSER_CLICK_TOOL,
    BROWSER_FILL_TOOL,
    BROWSER_SCREENSHOT_TOOL,
    APP_LOGIN_TOOL,
    YOUTUBE_REAUTH_TOOL,
]
