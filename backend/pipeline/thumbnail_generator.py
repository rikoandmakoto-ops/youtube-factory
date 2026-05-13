"""HTML+CSS+Playwright サムネイル生成モジュール.

Pipeline:
  1) GPT-4o で動画タイトルから「3行構成」のデザインブリーフをJSON生成
  2) DALL-E 3 で背景画像 (1792x1024 → 1280x720) を生成
  3) thumbnail_selfcontained.html のレイアウトをベースに自己完結HTMLを組み立て
     (背景画像とキャラ画像はすべて data URI に埋め込む — file:// で読み込み可)
  4) Playwright (Chromium headless) でスクリーンショットして PNG 保存

`assets/characters/<slug>/<expression>.png` を期待する。channel_config の
`thumbnail_template.characters.{left|right}` で {dir, expression} を上書き可能。
"""
from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "assets"

# ────────────────────────────────────────────────────────────────────────
# Default channel-name → asset slug fallback. Only consulted when
# channel_config does not supply explicit thumbnail character mapping.
# ────────────────────────────────────────────────────────────────────────
DEFAULT_NAME_TO_SLUG: Dict[str, str] = {
    "理子": "riko",
    "リコ": "riko",
    "riko": "riko",
    "真": "makoto",
    "マコト": "makoto",
    "makoto": "makoto",
}

DEFAULT_EXPRESSION = "surprise"


# ────────────────────────────────────────────────────────────────────────
# OpenAI helpers (urllib for parity with the rest of the codebase — no
# extra dependency required)
# ────────────────────────────────────────────────────────────────────────
def _call_openai(url: str, payload: dict, api_key: str, timeout: int = 240) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e


# ────────────────────────────────────────────────────────────────────────
# Step 1 — design brief
# ────────────────────────────────────────────────────────────────────────
def design_brief(
    title: str,
    api_key: str,
    channel_meta: Optional[Dict[str, Any]] = None,
    feedback: Optional[List[str]] = None,
    channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask GPT-4o for a 3-line thumbnail design brief tailored to `title`.

    `feedback` — ordered list of free-text revision instructions from the user
    accumulated across previous regenerations. When provided, GPT-4o is told to
    apply these revisions on top of its baseline design.

    `channel_id` — when provided, competitor_analyses-derived thumbnail patterns
    and improvement suggestions are pulled via competitor_intelligence and
    injected into the prompt so the brief learns from observed competitor
    behavior (without losing the channel's own voice).
    """
    channel_meta = channel_meta or {}
    channel_name = channel_meta.get("name") or ""
    concept = channel_meta.get("concept") or ""

    feedback_block = ""
    if feedback:
        cleaned = [f.strip() for f in feedback if f and f.strip()]
        if cleaned:
            bullets = "\n".join(f"- {f}" for f in cleaned)
            feedback_block = (
                "\n\nユーザーからの修正指示（古い→新しい順、ALLを必ず反映する。"
                "矛盾する場合は新しい指示を優先する):\n" + bullets + "\n"
            )

    competitor_block = ""
    if channel_id:
        try:
            from pipeline.analytics.competitor_intelligence import (
                build_thumbnail_competitor_block,
            )
            competitor_block = build_thumbnail_competitor_block(channel_id) or ""
        except Exception as e:
            print(f"  ⚠️ thumbnail competitor block failed: {e}")
        if competitor_block:
            competitor_block = "\n\n" + competitor_block + "\n"

    system = (
        "あなたはYouTubeで何百万再生も叩き出すサムネイルを設計する一流のアートディレクターです。"
        "日本語のゆっくり解説／知識系チャンネル向けに、思わずクリックしたくなる"
        "サムネイル案を厳密なJSONで返します。"
        + (
            " 競合チャンネル分析の知見が提供された場合、その効果的な要素は積極的に取り入れつつ、"
            "丸パクリは避け、自チャンネルの個性を必ず重ねます。"
            if competitor_block else ""
        )
    )
    user = (
        f"動画タイトル: 「{title}」\n"
        + (f"チャンネル: 「{channel_name}」 — {concept}\n" if channel_name else "")
        + feedback_block
        + competitor_block
        + "\n"
        "サムネイルは固定レイアウトです。次のフィールドを必ず含むJSONだけを返してください"
        "（コードフェンス禁止、純JSON）:\n"
        "{\n"
        '  "line1": "1行目（白文字、状況/前振り。最大14文字、句読点OK）",\n'
        '  "line2": "2行目（黄色強調、核となる驚き/疑問。最大12文字、!?推奨）",\n'
        '  "line3_badge": "3行目の赤バッジ内テキスト（5〜10文字、「衝撃の真実」「○○の正体」など)",\n'
        '  "sub_text": "下部の小さな黄色サブコピー（10〜20文字、答えを匂わせる)",\n'
        '  "highlight_word": "line2の中で特に強調したい単語（4〜7文字)",\n'
        '  "background_concept": "DALL-E 3 に渡す英語の背景プロンプト。'
        "ドラマチックなライティング、ハイコントラスト、被写体クローズアップ。"
        "「absolutely no text, no letters, no numbers, no captions, no logos」を必ず明記。"
        '1280x720 16:9 想定。中央〜上部に主役を置き、下部は構図を空ける。",\n'
        '  "color_palette": "色使いの説明（例: 赤×黄×白×青)"\n'
        "}\n\n"
        "重要:\n"
        "- 文字数は厳守（HTMLの固定レイアウトに収まらないと崩れる)\n"
        "- 各行は別々の事実/煽り（同じことを言わない)\n"
        "- DALL-E 3 は文字を綺麗に描けないので背景プロンプトは必ず『no text/letters/numbers』を明記"
    )

    resp = _call_openai(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
        },
        api_key,
    )
    content = resp["choices"][0]["message"]["content"]
    brief = json.loads(content)

    # Defensive defaults so downstream rendering never crashes on missing keys.
    brief.setdefault("line1", title[: min(14, len(title))])
    brief.setdefault("line2", "驚きの真実！？")
    brief.setdefault("line3_badge", "衝撃の事実")
    brief.setdefault("sub_text", "")
    brief.setdefault("highlight_word", "")
    brief.setdefault("background_concept", f"Cinematic illustration related to: {title}")
    return brief


# ────────────────────────────────────────────────────────────────────────
# Step 2 — DALL-E 3 background
# ────────────────────────────────────────────────────────────────────────
def generate_background(brief: Dict[str, Any], api_key: str, out_path: Path) -> Path:
    """Call DALL-E 3 and save a 1280x720 PNG to `out_path`."""
    bg_concept = brief.get("background_concept", "")
    prompt = (
        f"{bg_concept}\n"
        "Style: bold, eye-catching YouTube thumbnail aesthetic, high contrast, "
        "saturated colors, dramatic lighting, shallow depth of field, "
        "cinematic, photo-realistic close-up. "
        "STRICT: absolutely no text, no letters, no numbers, no Japanese characters, "
        "no captions, no logos anywhere in the image. "
        "Composition: wide 16:9 horizontal, leave the bottom ~25% visually simpler "
        "(soft gradient or out-of-focus background) so big Japanese title text can be overlaid later."
    )
    resp = _call_openai(
        "https://api.openai.com/v1/images/generations",
        {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1792x1024",
            "style": "vivid",
            "quality": "hd",
            "response_format": "b64_json",
        },
        api_key,
        timeout=240,
    )
    img_b64 = resp["data"][0]["b64_json"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(img_b64))

    # Resize 1792x1024 → 1280x720
    try:
        from PIL import Image
        img = Image.open(out_path).convert("RGB")
        img = img.resize((1280, 720), Image.LANCZOS)
        img.save(out_path, "PNG")
    except Exception as e:
        # If Pillow fails, leave the original (HTML <img> will scale via object-fit)
        print(f"  ⚠️ background resize skipped: {e}")
    return out_path


# ────────────────────────────────────────────────────────────────────────
# Step 3 — character resolution
# ────────────────────────────────────────────────────────────────────────
def _find_character_path(slug: str, expression: str) -> Optional[Path]:
    base = ASSETS_DIR / "characters" / slug
    if not base.exists():
        return None
    candidates = [
        base / f"{expression}.png",
        base / f"{DEFAULT_EXPRESSION}.png",
        base / "normal.png",
    ]
    for c in candidates:
        if c.exists():
            return c
    # fall back to any .png in the directory
    for png in sorted(base.glob("*.png")):
        return png
    return None


def resolve_character_paths(
    channel_config: Dict[str, Any]
) -> Tuple[Optional[Path], Optional[Path]]:
    """Pick (left_char_path, right_char_path) from channel config.

    Resolution order:
      1) `thumbnail_template.characters.{left|right}` = {dir, expression}
      2) `characters` dict — match each entry's `side`, derive slug from
         `thumb_dir`, lowercase name, or the DEFAULT_NAME_TO_SLUG table.
    """
    tmpl = (channel_config.get("thumbnail_template") or {})
    explicit = tmpl.get("characters") or {}

    def _resolve_explicit(side: str) -> Optional[Path]:
        spec = explicit.get(side)
        if not spec:
            return None
        slug = spec.get("dir") or spec.get("slug")
        if not slug:
            return None
        return _find_character_path(slug, spec.get("expression", DEFAULT_EXPRESSION))

    left = _resolve_explicit("left")
    right = _resolve_explicit("right")

    if left and right:
        return left, right

    # Fall back: scan `characters` dict for side=left/right entries.
    chars = channel_config.get("characters") or {}
    for name, cfg in chars.items():
        if not isinstance(cfg, dict):
            continue
        side = cfg.get("side")
        if side not in ("left", "right"):
            continue
        slug = (
            cfg.get("thumb_dir")
            or cfg.get("slug")
            or DEFAULT_NAME_TO_SLUG.get(name)
            or DEFAULT_NAME_TO_SLUG.get(name.lower())
            or name.lower()
        )
        expression = cfg.get("thumb_expression", DEFAULT_EXPRESSION)
        path = _find_character_path(slug, expression)
        if side == "left" and not left:
            left = path
        elif side == "right" and not right:
            right = path

    return left, right


# ────────────────────────────────────────────────────────────────────────
# Step 4 — HTML composition
# ────────────────────────────────────────────────────────────────────────
def _data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _scaled_font_px(text: str, base_px: int, base_chars: int, min_px: int) -> int:
    """Shrink font when text is longer than the base width."""
    n = max(1, len(text))
    if n <= base_chars:
        return base_px
    scaled = int(base_px * base_chars / n)
    return max(min_px, scaled)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@700;900&display=swap" rel="stylesheet">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #000; display: flex; justify-content: center; align-items: center;
       min-height: 100vh; overflow: hidden; }}
.thumbnail {{ position: relative; width: 1280px; height: 720px; overflow: hidden; }}
.thumbnail .bg {{ width: 100%; height: 100%; object-fit: cover; }}
.top-gradient {{ position: absolute; top: 0; left: 0; right: 0; height: 60%;
  background: linear-gradient(to bottom, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0.3) 60%, transparent 100%); }}
.bottom-gradient {{ position: absolute; bottom: 0; left: 0; right: 0; height: 45%;
  background: linear-gradient(to top, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 50%, transparent 100%); }}
.text-line {{ position: absolute; left: 0; right: 0; text-align: center;
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 900; letter-spacing: 0.04em; }}
.line1 {{ top: 18px; font-size: {line1_px}px; color: #fff;
  text-shadow:
    -4px -4px 0 #000, 4px -4px 0 #000, -4px 4px 0 #000, 4px 4px 0 #000,
    -6px 0 0 #000, 6px 0 0 #000, 0 -6px 0 #000, 0 6px 0 #000,
    -3px -5px 0 #000, 3px -5px 0 #000, -3px 5px 0 #000, 3px 5px 0 #000,
    -5px -3px 0 #000, 5px -3px 0 #000, -5px 3px 0 #000, 5px 3px 0 #000; }}
.line2 {{ top: 135px; font-size: {line2_px}px; color: #FFEB3C;
  text-shadow:
    -5px -5px 0 #A00, 5px -5px 0 #A00, -5px 5px 0 #A00, 5px 5px 0 #A00,
    -7px 0 0 #A00, 7px 0 0 #A00, 0 -7px 0 #A00, 0 7px 0 #A00,
    -4px -6px 0 #A00, 4px -6px 0 #A00, -4px 6px 0 #A00, 4px 6px 0 #A00,
    -6px -4px 0 #A00, 6px -4px 0 #A00, -6px 4px 0 #A00, 6px 4px 0 #A00; }}
.line3-wrap {{ position: absolute; top: 278px; left: 0; right: 0; text-align: center; }}
.line3-badge {{ display: inline-block; background: rgba(220, 20, 20, 0.93);
  border: 4px solid rgba(255,255,255,0.9); border-radius: 14px; padding: 8px 36px;
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 900; font-size: {line3_px}px; color: #fff; letter-spacing: 0.05em;
  text-shadow:
    -3px -3px 0 rgba(80,0,0,0.9), 3px -3px 0 rgba(80,0,0,0.9),
    -3px 3px 0 rgba(80,0,0,0.9), 3px 3px 0 rgba(80,0,0,0.9),
    -5px 0 0 rgba(80,0,0,0.9), 5px 0 0 rgba(80,0,0,0.9),
    0 -5px 0 rgba(80,0,0,0.9), 0 5px 0 rgba(80,0,0,0.9); }}
.sub-text {{ position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
  font-size: {sub_px}px; color: #FFF064;
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 700;
  text-shadow:
    -3px -3px 0 #300, 3px -3px 0 #300, -3px 3px 0 #300, 3px 3px 0 #300,
    -4px 0 0 #300, 4px 0 0 #300, 0 -4px 0 #300, 0 4px 0 #300;
  white-space: nowrap; }}
.char-left {{ position: absolute; bottom: -20px; left: 10px; height: 280px; width: auto; z-index: 10; }}
.char-right {{ position: absolute; bottom: -20px; right: 10px; height: 280px; width: auto; z-index: 10; }}
</style></head>
<body>
<div class="thumbnail" id="thumb">
  <img class="bg" src="{bg_uri}">
  <div class="top-gradient"></div>
  <div class="bottom-gradient"></div>
  <div class="text-line line1">{line1}</div>
  <div class="text-line line2">{line2}</div>
  <div class="line3-wrap"><span class="line3-badge">{line3_badge}</span></div>
  {sub_html}
  {char_left_html}
  {char_right_html}
</div>
</body></html>
"""


def build_html(
    brief: Dict[str, Any],
    bg_path: Path,
    char_left: Optional[Path],
    char_right: Optional[Path],
) -> str:
    """Compose a self-contained HTML string (all images as data URIs)."""
    line1 = (brief.get("line1") or "").strip()
    line2 = (brief.get("line2") or "").strip()
    line3 = (brief.get("line3_badge") or "").strip()
    sub = (brief.get("sub_text") or "").strip()

    line1_px = _scaled_font_px(line1, 88, 14, 56)
    line2_px = _scaled_font_px(line2, 105, 12, 64)
    line3_px = _scaled_font_px(line3, 82, 10, 52)
    sub_px = _scaled_font_px(sub, 38, 22, 26)

    bg_uri = _data_uri(bg_path)
    char_left_html = (
        f'<img class="char-left" src="{_data_uri(char_left)}">' if char_left else ""
    )
    char_right_html = (
        f'<img class="char-right" src="{_data_uri(char_right)}">' if char_right else ""
    )
    sub_html = f'<div class="sub-text">{_esc(sub)}</div>' if sub else ""

    return _HTML_TEMPLATE.format(
        line1_px=line1_px,
        line2_px=line2_px,
        line3_px=line3_px,
        sub_px=sub_px,
        bg_uri=bg_uri,
        line1=_esc(line1),
        line2=_esc(line2),
        line3_badge=_esc(line3),
        sub_html=sub_html,
        char_left_html=char_left_html,
        char_right_html=char_right_html,
    )


# ────────────────────────────────────────────────────────────────────────
# Step 5 — Playwright render
# ────────────────────────────────────────────────────────────────────────
async def render_html_to_png_async(html: str, output_path: Path) -> Path:
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright がインストールされていません。"
            "`pip install playwright && python -m playwright install chromium` を実行してください"
        ) from e

    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
            )
            await page.set_content(html, wait_until="networkidle")
            # Give Google Fonts time to fully apply.
            await page.wait_for_timeout(2000)
            thumb = page.locator("#thumb")
            await thumb.screenshot(path=str(output_path))
        finally:
            await browser.close()
    return output_path


def render_html_to_png(html: str, output_path: Path) -> Path:
    """Sync wrapper. Safe to call from worker threads (no event loop)."""
    return asyncio.run(render_html_to_png_async(html, output_path))


# ────────────────────────────────────────────────────────────────────────
# Public entry points
# ────────────────────────────────────────────────────────────────────────
def _resolve_api_key(provided: Optional[str]) -> str:
    key = provided or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY が設定されていません")
    return key


def _default_bg_path(output_path: Path) -> Path:
    return output_path.with_name(output_path.stem + "_bg.png")


def generate_thumbnail(
    title: str,
    channel_config: Dict[str, Any],
    output_path,
    *,
    openai_api_key: Optional[str] = None,
    reuse_background_path=None,
    background_save_path=None,
    brief_override: Optional[Dict[str, Any]] = None,
    feedback: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a YouTube thumbnail PNG. Synchronous facade.

    `feedback` — optional list of free-text revision instructions accumulated
    across previous regenerations. Forwarded to `design_brief` so GPT-4o adjusts
    the brief based on what the user asked to change.

    Returns:
        {"thumbnail_path", "background_path", "brief"}
    """
    api_key = _resolve_api_key(openai_api_key)
    output_path = Path(output_path)

    brief = brief_override or design_brief(
        title, api_key, channel_meta={
            "name": channel_config.get("name"),
            "concept": channel_config.get("concept"),
        },
        feedback=feedback,
        channel_id=channel_config.get("id"),
    )

    if reuse_background_path:
        bg_path = Path(reuse_background_path)
        if not bg_path.exists():
            raise FileNotFoundError(f"reuse_background_path not found: {bg_path}")
    else:
        bg_path = Path(background_save_path) if background_save_path else _default_bg_path(output_path)
        generate_background(brief, api_key, bg_path)

    char_left, char_right = resolve_character_paths(channel_config)
    html = build_html(brief, bg_path, char_left, char_right)
    render_html_to_png(html, output_path)

    return {
        "thumbnail_path": str(output_path),
        "background_path": str(bg_path),
        "brief": brief,
    }


async def generate_thumbnail_async(
    title: str,
    channel_config: Dict[str, Any],
    output_path,
    *,
    openai_api_key: Optional[str] = None,
    reuse_background_path=None,
    background_save_path=None,
    brief_override: Optional[Dict[str, Any]] = None,
    feedback: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Async variant — for use from FastAPI handlers (which already have a loop).

    The OpenAI calls are blocking (urllib); they run in a thread executor so
    we don't stall the event loop.

    `feedback` — see `generate_thumbnail` docstring.
    """
    loop = asyncio.get_running_loop()
    api_key = _resolve_api_key(openai_api_key)
    output_path = Path(output_path)

    brief = brief_override or await loop.run_in_executor(
        None,
        lambda: design_brief(
            title,
            api_key,
            channel_meta={
                "name": channel_config.get("name"),
                "concept": channel_config.get("concept"),
            },
            feedback=feedback,
            channel_id=channel_config.get("id"),
        ),
    )

    if reuse_background_path:
        bg_path = Path(reuse_background_path)
        if not bg_path.exists():
            raise FileNotFoundError(f"reuse_background_path not found: {bg_path}")
    else:
        bg_path = Path(background_save_path) if background_save_path else _default_bg_path(output_path)
        await loop.run_in_executor(None, lambda: generate_background(brief, api_key, bg_path))

    char_left, char_right = resolve_character_paths(channel_config)
    html = build_html(brief, bg_path, char_left, char_right)
    await render_html_to_png_async(html, output_path)

    return {
        "thumbnail_path": str(output_path),
        "background_path": str(bg_path),
        "brief": brief,
    }
