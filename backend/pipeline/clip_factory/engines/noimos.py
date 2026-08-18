"""NoimosAI（SaaS）のクリエイティブエージェントに切り抜きを任せるエンジン。

経路は2つ。`clip.noimos.mode` で選ぶ（既定 "browser"）。

  browser : Playwright で app.noimosai.com を自動操作する（本命）
  cli     : `@agos-labs/noimosai-cli` の chat を叩く（旧実装・残置）

■ 調査結果1：公開 REST API は無い（2026-08-04）

docs.noimosai.com が公開している OpenAPI 仕様（/api-reference/openapi.json）は
Mintlify のサンプル（Plant Store）のままで、実体が無い。プログラムから触れる口は
CLI `@agos-labs/noimosai-cli` と MCP `@agos-labs/noimosai-mcp` だけで、どちらも
公開ツールは `chat` / `list_workspaces` / `list_integrations` / `post` の4つのみ。
**素材動画をアップロードするAPI・切り抜きジョブを起動するAPI・完成MP4をダウンロード
するAPI は無い**（CLI 0.0.9 の内部クライアントにも media upload エンドポイントが無く、
チャット要求の `mediaPaths` は CLI から常に空で送られる）。

■ 調査結果2：Web UI 自動操作に切り替えたが、成功は保証できない（2026-08-04）

API が無いなら UI を操作すればよい、という方針でこのファイルを書き換えた。
ただし **NoimosAI 側に動画をレンダリングする機能が確認できていない**。
公開情報上の動画能力は次の3つだけで、いずれもMP4を書き出さない:

  - 台本生成   "Generates video scripts, storyboard ideas, and visual references"
  - 投稿代行   "Uploads video media, adds captions/hashtags, and schedules posts"
               ＝ 既に手元にある動画ファイルを配信するだけ
  - 実績分析   "Analyzes video performance …"

最も近いテンプレート auto-product-video-gen も出力はタイムスタンプ付き台本と編集指示。
そのため **エージェントが動画を返さない可能性が高い**。返らなかった場合このエンジンは
NoimosUnavailable を投げ、呼び出し側が clip.fallback_engine（既定 local）へ落とす。
切り抜きの実生成は local エンジンが担当する、という前提は崩さないこと。

■ 再調査（2026-08-09）：一部は変わった。ただし切り抜きが出来る保証は依然無い

  * app.noimosai.com へブラウザで到達できるようになった（08-04 は遮断されていた）
  * ヘルプに「画像・動画・音声を作成／編集する」が追加され、動画能力の記述が
    台本止まりではなくなった。「既存の画像や動画をもとに構図・色・アスペクト比・
    文字を調整する」「字幕付き動画」も対象と書かれている
  * Chat に **ファイル添付（1メッセージ5件まで）** がある

  それでも **長尺→縦型ショートの切り出し** は依然どこにも documented されていない。
  かつ本エンジンは元動画を **YouTube URL のテキストで渡すだけ** で、添付は実装して
  いない。NoimosAI 側に URL から動画を取得する機能は確認できていないので、
  現状のプロンプトでは高確率で MP4 が返らない。返らなければ NoimosUnavailable を
  投げて clip.fallback_engine（既定 local）へ落ちる。
  **切り抜きの実生成は local エンジンが担当する、という前提は崩さないこと。**

■ 実装方針：DOM に依存しすぎない

ログイン画面は 2026-08-09 に再実測した。08-04 の記録と違い、UI は **日本語がデフォルト**、
**Google OAuth ボタンがある**、そして **reCAPTCHA Enterprise（render=explicit）が
載っている**。メール欄は type="text" で name / placeholder / autocomplete がすべて空、
id は React 生成のランダム値なので、属性ではなく「フォーム内の非パスワードテキスト
入力」でしか特定できない（_login 参照）。

reCAPTCHA があるため **headless の自動ログインは弾かれる可能性がある**。その場合は
人間が一度ログインして storage_state（既定 ~/.youtube-factory/noimos_session.json）を
作り、以後はそれを使い回すこと。CAPTCHA の突破は実装しない。

ログイン後のチャットUIの DOM は **未確認**。そこで成果物の回収は「ページ内 DOM 走査」
ではなく **ネットワーク応答の傍受** を主経路にしている（Content-Type が video/* か、
URL が .mp4/.mov/.webm）。DOM 走査は補助。セレクタは全て clip.noimos.selectors で
上書きできる。

■ アカウント作成は自動化しない

サインアップとメール認証は **意図的に実装していない**。アカウントは人間が作ること
（/signup は 利用規約への同意チェック必須。Google ログインも可）。API キー発行には
有料プラン Pro $99/月〜が必要。認証情報が無ければ preflight が理由を返して止まる。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..sources import SourceVideo

DEFAULT_BASE_URL = "https://app.noimosai.com"

#: 動画とみなす拡張子
_VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")

#: チャット入力欄の候補（DOM 未確認のため広めに）
_COMPOSER_CANDIDATES = [
    "textarea",
    "[contenteditable='true']",
    "input[type='text'][placeholder]",
]

#: 送信ボタンの候補
_SEND_CANDIDATES = [
    "button[type='submit']",
    "button[aria-label*='end' i]",
    "button[aria-label*='送信']",
    "button:has-text('Send')",
    "button:has-text('送信')",
]


class NoimosUnavailable(RuntimeError):
    """NoimosAI を無人実行できない（認証情報未設定 / 依存未導入 / 動画が公開されていない）。"""


# ---------------------------------------------------------------------
# 設定・認証情報
# ---------------------------------------------------------------------

def _cfg(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return clip_cfg.get("noimos") or {}


def _mode(clip_cfg: Dict[str, Any]) -> str:
    return str(_cfg(clip_cfg).get("mode") or "browser").strip().lower()


def _base_url(clip_cfg: Dict[str, Any]) -> str:
    return str(_cfg(clip_cfg).get("base_url") or DEFAULT_BASE_URL).rstrip("/")


def _credentials() -> tuple[str, str]:
    return (
        (os.environ.get("NOIMOS_EMAIL") or "").strip(),
        os.environ.get("NOIMOS_PASSWORD") or "",
    )


def _storage_state_path(clip_cfg: Dict[str, Any]) -> Path:
    raw = (_cfg(clip_cfg).get("storage_state")
           or os.environ.get("NOIMOS_STORAGE_STATE")
           or "~/.youtube-factory/noimos_session.json")
    return Path(str(raw)).expanduser()


def _cli_bin(clip_cfg: Dict[str, Any]) -> Optional[str]:
    return shutil.which(str(_cfg(clip_cfg).get("cli_bin") or "noimosai"))


def _api_key() -> str:
    return (os.environ.get("NOIMOS_API_KEY") or "").strip()


def _selectors(clip_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """DOM が変わったら channel JSON 側で上書きできるようにしておく。"""
    return _cfg(clip_cfg).get("selectors") or {}


def preflight(clip_cfg: Dict[str, Any]) -> Optional[str]:
    """使えない理由を返す。使えるなら None。"""
    mode = _mode(clip_cfg)

    if mode == "cli":
        if not _api_key():
            return ("NOIMOS_API_KEY が未設定です（mode=cli）。有料プラン $99/月〜が必要。")
        if not _cli_bin(clip_cfg):
            return "noimosai CLI が見つかりません。`npm i -g @agos-labs/noimosai-cli` を実行してください。"
        return None

    # --- browser モード ---
    try:
        import playwright  # noqa: F401
    except Exception:
        return ("playwright が導入されていません。"
                "`pip install playwright && python -m playwright install chromium` を実行してください。")

    email, password = _credentials()
    if not (email and password) and not _storage_state_path(clip_cfg).exists():
        return ("NoimosAI のログイン情報がありません。backend/.env に NOIMOS_EMAIL と "
                "NOIMOS_PASSWORD を設定してください（アカウント作成とメール認証は "
                "人手で済ませておくこと。このエンジンはサインアップを自動化しません）。")
    return None


# ---------------------------------------------------------------------
# プロンプト組み立て
# ---------------------------------------------------------------------

def _build_prompt(source: SourceVideo, clip_cfg: Dict[str, Any], count: int) -> str:
    template = str(_cfg(clip_cfg).get("prompt_template") or
                   "{source_url} から縦型ショートを{clips}本切り抜いてください。")
    return template.format(
        source_url=source.source_url(),
        source_title=source.video_title,
        clips=count,
        target_sec=int(clip_cfg.get("target_duration_sec") or 50),
    )


# ---------------------------------------------------------------------
# ブラウザ経路
# ---------------------------------------------------------------------

def _looks_like_video_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(_VIDEO_EXT)


def _first_locator(page, candidates: List[str], *, timeout_ms: int = 4000):
    """候補セレクタを順に試して最初に見つかった要素を返す（無ければ None）。"""
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=timeout_ms):
                return el
        except Exception:
            continue
    return None


def _is_logged_in(page, base_url: str) -> bool:
    """/login にリダイレクトされていなければログイン済みとみなす。"""
    try:
        return "/login" not in page.url and "/signup" not in page.url
    except Exception:
        return False


def _login(page, base_url: str, clip_cfg: Dict[str, Any], *, timeout_ms: int) -> None:
    """実測済みのログイン画面（Email / Password / "Log in"）を埋めて送信する。

    サインアップは実装しない。アカウントが無ければここで失敗させる。
    """
    email, password = _credentials()
    if not (email and password):
        raise NoimosUnavailable(
            "セッションが切れていますが NOIMOS_EMAIL / NOIMOS_PASSWORD が未設定のため"
            "再ログインできません。"
        )

    sel = _selectors(clip_cfg)
    page.goto(f"{base_url}/login", timeout=timeout_ms, wait_until="domcontentloaded")

    # 実測（2026-08-09）: メール欄は type="text"、name も placeholder も autocomplete も
    # 空で、id は React 生成のランダム値。属性から特定できないのでフォーム内で
    # 「パスワードでないテキスト入力」を拾うのが唯一安定する。
    # reCAPTCHA が末尾に隠しテキスト入力を挿すが form の外なので巻き込まない。
    email_el = _first_locator(page, [
        str(sel.get("email") or "input[type='email']"),
        "input[name='email']",
        "input[autocomplete='username']",
        "input[placeholder*='mail' i]",
        "form input[type='text']",
        "form input:not([type='password']):not([type='hidden']):not([type='checkbox'])",
    ])
    pw_el = _first_locator(page, [
        str(sel.get("password") or "input[type='password']"),
        "input[name='password']",
        "form input[type='password']",
    ])
    if email_el is None or pw_el is None:
        raise NoimosUnavailable(
            "ログインフォームを特定できませんでした。DOM が変わった可能性があります"
            "（clip.noimos.selectors.email / .password で上書きできます）。"
        )

    email_el.fill(email, timeout=timeout_ms)
    pw_el.fill(password, timeout=timeout_ms)

    # UI は日本語がデフォルト（2026-08-09 実測）。JA を先に試す。
    submit = _first_locator(page, [
        str(sel.get("login_button") or "form button[type='submit']"),
        "button:has-text('ログイン')",
        "button:has-text('Log in')",
        "button:has-text('Login')",
        "button[type='submit']",
    ])
    if submit is None:
        pw_el.press("Enter")
    else:
        submit.click(timeout=timeout_ms)

    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=timeout_ms)
    except Exception:
        raise NoimosUnavailable(
            "ログインに失敗しました（認証情報が誤っているか、メール認証・2要素認証が"
            "未完了の可能性）。ブラウザで一度手動ログインしてから再実行してください。"
        )


def _submit_prompt(page, prompt: str, clip_cfg: Dict[str, Any], *, timeout_ms: int) -> None:
    sel = _selectors(clip_cfg)
    composer = _first_locator(page, (
        [str(sel["composer"])] if sel.get("composer") else []) + _COMPOSER_CANDIDATES)
    if composer is None:
        raise NoimosUnavailable(
            "チャット入力欄を特定できませんでした（clip.noimos.selectors.composer で"
            "上書きできます）。"
        )
    composer.click(timeout=timeout_ms)
    composer.fill(prompt, timeout=timeout_ms)

    send = _first_locator(page, (
        [str(sel["send"])] if sel.get("send") else []) + _SEND_CANDIDATES)
    if send is not None:
        send.click(timeout=timeout_ms)
    else:
        composer.press("Enter")


def _scan_dom_for_media(page) -> List[str]:
    """DOM から動画URLを拾う（ネットワーク傍受の補助）。"""
    try:
        found = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('video[src], video source[src]')
                    .forEach(v => out.push(v.src || v.getAttribute('src')));
                document.querySelectorAll('a[href]').forEach(a => out.push(a.href));
                return out.filter(Boolean);
            }"""
        ) or []
    except Exception:
        return []
    return [u for u in found if _looks_like_video_url(str(u))]


def _download_via_context(context, url: str, dest: Path, *, timeout_ms: int) -> Path:
    """ブラウザのセッション（Cookie）を保ったままダウンロードする。

    成果物URLがアプリの認証配下にある場合、素の urllib では 401/403 になるため
    APIRequestContext を使う。取れなければ urllib にフォールバック。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = context.request.get(url, timeout=timeout_ms)
        if resp.ok:
            dest.write_bytes(resp.body())
        else:
            raise RuntimeError(f"HTTP {resp.status}")
    except Exception:
        req = urllib.request.Request(
            url, headers={"User-Agent": "youtube-factory/clip_factory"})
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as r, open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)

    size = dest.stat().st_size if dest.exists() else 0
    if size < 10_000:
        raise RuntimeError(f"ダウンロードしたファイルが小さすぎます: {dest} ({size} bytes)")
    return dest


def _generate_browser(
    *,
    source: SourceVideo,
    clip_cfg: Dict[str, Any],
    out_dir: Path,
    count: int,
) -> List[Dict[str, Any]]:
    from playwright.sync_api import sync_playwright  # type: ignore

    cfg = _cfg(clip_cfg)
    base_url = _base_url(clip_cfg)
    headless = bool(cfg.get("headless", True))
    # timeout_sec は CLI 経路のジョブ全体待ち（既定900s）なので流用しない。
    # ページ遷移・要素待ちはこちらの短いタイムアウトを使う。
    nav_timeout_ms = int(cfg.get("nav_timeout_sec") or 120) * 1000
    agent_wait_sec = int(cfg.get("agent_wait_sec") or 900)
    poll_sec = int(cfg.get("poll_interval_sec") or 5)
    state_path = _storage_state_path(clip_cfg)
    prompt = _build_prompt(source, clip_cfg, count)

    #: ネットワーク応答から拾った動画URL（DOM に出ないケースを拾うため）
    media_urls: List[str] = []

    def _on_response(resp) -> None:
        try:
            url = resp.url
            ctype = (resp.headers or {}).get("content-type", "")
            if ctype.startswith("video/") or _looks_like_video_url(url):
                if url not in media_urls:
                    media_urls.append(url)
        except Exception:
            pass

    results: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx_kwargs: Dict[str, Any] = {"locale": "ja-JP"}
            if state_path.exists():
                ctx_kwargs["storage_state"] = str(state_path)
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            page.on("response", _on_response)

            # --- ログイン ---
            page.goto(base_url, timeout=nav_timeout_ms, wait_until="domcontentloaded")
            if not _is_logged_in(page, base_url):
                print("  🔑 NoimosAI にログイン中…")
                _login(page, base_url, clip_cfg, timeout_ms=nav_timeout_ms)
            # セッションを保存して次回のログインを省く
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_path))
            except Exception as e:
                print(f"  ⚠️ セッション保存に失敗（無視して継続）: {e}")

            # --- 依頼 ---
            workspace_url = str(cfg.get("workspace_url") or "").strip()
            if workspace_url:
                page.goto(workspace_url, timeout=nav_timeout_ms, wait_until="domcontentloaded")

            print(f"  ☁️ NoimosAI に切り抜きを依頼中（最大 {agent_wait_sec}s 待機）…")
            _submit_prompt(page, prompt, clip_cfg, timeout_ms=nav_timeout_ms)

            # --- 成果物待ち ---
            deadline = time.time() + agent_wait_sec
            while time.time() < deadline and not media_urls:
                page.wait_for_timeout(poll_sec * 1000)
                for u in _scan_dom_for_media(page):
                    if u not in media_urls:
                        media_urls.append(u)

            if not media_urls:
                raise NoimosUnavailable(
                    f"NoimosAI が {agent_wait_sec}s 以内に動画を返しませんでした。"
                    "NoimosAI は台本生成と投稿代行が中心で、動画をレンダリングする機能が"
                    "確認できていません（このファイルの docstring 参照）。"
                    "local エンジンへフォールバックします。"
                )

            # --- 取り込み ---
            for n, url in enumerate(media_urls[:count]):
                clip_id = f"noimos_{source.source_channel_id}_{int(time.time())}_{n}"
                dest = out_dir / f"{clip_id}.mp4"
                _download_via_context(context, url, dest, timeout_ms=nav_timeout_ms)
                results.append({
                    "clip_id": clip_id,
                    "engine": "noimos",
                    "video_path": str(dest),
                    "thumbnail_path": None,
                    "hook": "",
                    "source_media_url": url,
                    # NoimosAI 側は元動画のどこを切ったか返さないので区間は不明。
                    # 0 埋めだと sources.record_clip の区間重複チェックが効かない点に注意。
                    "segment": {"start": 0.0, "end": 0.0, "duration": 0.0},
                })
        finally:
            browser.close()

    print(f"  ☁️ NoimosAI から {len(results)} 本取り込み完了")
    return results


# ---------------------------------------------------------------------
# CLI 経路（旧実装・残置）
# ---------------------------------------------------------------------

def _run_cli(args: List[str], *, timeout: int) -> Dict[str, Any]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"noimosai CLI failed ({proc.returncode}): {proc.stderr[-800:]}")
    try:
        return json.loads(proc.stdout)
    except Exception as e:
        raise RuntimeError(f"noimosai CLI の JSON 出力を解釈できません: {e}\n{proc.stdout[:500]}")


def _collect_media_urls(payload: Dict[str, Any]) -> List[str]:
    """NoimosPostJson から動画とみなせる media URL を拾う。"""
    urls: List[str] = []
    for post in payload.get("posts") or []:
        for media in post.get("media") or []:
            url = str(media.get("url") or "").strip()
            mime = str(media.get("mimeType") or "")
            if not url:
                continue
            if mime.startswith("video/") or _looks_like_video_url(url):
                urls.append(url)
    return urls


def _download(url: str, dest: Path, *, timeout: int = 600) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "youtube-factory/clip_factory"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    if dest.stat().st_size < 10_000:
        raise RuntimeError(f"ダウンロードしたファイルが小さすぎます: {dest} ({dest.stat().st_size} bytes)")
    return dest


def _generate_cli(
    *,
    source: SourceVideo,
    clip_cfg: Dict[str, Any],
    out_dir: Path,
    count: int,
) -> List[Dict[str, Any]]:
    cfg = _cfg(clip_cfg)
    timeout = int(cfg.get("timeout_sec") or 900)
    prompt = _build_prompt(source, clip_cfg, count)

    args = [_cli_bin(clip_cfg), "chat", "-p", prompt, "-o", "json"]
    workspace = str(cfg.get("workspace_id") or os.environ.get("NOIMOS_WORKSPACE_ID") or "")
    if workspace:
        args += ["-w", workspace]

    print(f"  ☁️ NoimosAI に切り抜きを依頼中（CLI / timeout {timeout}s）…")
    payload = _run_cli(args, timeout=timeout)
    urls = _collect_media_urls(payload)
    if not urls:
        raise NoimosUnavailable(
            "NoimosAI から動画メディアが返りませんでした"
            f"（応答: {str(payload.get('output'))[:300]}）"
        )

    results: List[Dict[str, Any]] = []
    for n, url in enumerate(urls[:count]):
        clip_id = f"noimos_{source.source_channel_id}_{int(time.time())}_{n}"
        dest = out_dir / f"{clip_id}.mp4"
        _download(url, dest)
        results.append({
            "clip_id": clip_id,
            "engine": "noimos",
            "video_path": str(dest),
            "thumbnail_path": None,
            "hook": "",
            "source_media_url": url,
            "segment": {"start": 0.0, "end": 0.0, "duration": 0.0},
        })
    print(f"  ☁️ NoimosAI から {len(results)} 本取り込み完了")
    return results


# ---------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------

def generate(
    *,
    source: SourceVideo,
    clip_cfg: Dict[str, Any],
    channel_raw: Dict[str, Any],
    source_channel_raw: Dict[str, Any],
    out_dir: Path,
    count: int = 1,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """NoimosAI に切り抜きを依頼し、返ってきた MP4 を取り込む。"""
    reason = preflight(clip_cfg)
    if reason:
        raise NoimosUnavailable(reason)

    if not source.source_url():
        raise NoimosUnavailable(
            f"元動画の YouTube URL が特定できません（{source.title}）。"
            "NoimosAI はローカルファイルを受け取れないため、公開済み動画のみ依頼できます。"
        )

    if dry_run:
        return [{
            "clip_id": f"noimos_dryrun_{int(time.time())}",
            "engine": "noimos",
            "mode": _mode(clip_cfg),
            "prompt": _build_prompt(source, clip_cfg, count),
            "video_path": None,
            "hook": "",
            "segment": {"start": 0, "end": 0},
        }]

    if _mode(clip_cfg) == "cli":
        return _generate_cli(source=source, clip_cfg=clip_cfg, out_dir=out_dir, count=count)
    return _generate_browser(source=source, clip_cfg=clip_cfg, out_dir=out_dir, count=count)
