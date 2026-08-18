"""HTML+CSS+Playwright サムネイル生成モジュール.

Pipeline:
  1) GPT-5.6-terra で動画タイトルから「3行構成」のデザインブリーフをJSON生成
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

from pipeline import openai_compat

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "assets"

# デザインブリーフ生成モデル（画像入力ありのJSON生成）。
BRIEF_MODEL = "gpt-5.6-terra"

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
    style_hint = channel_meta.get("style_hint") or ""

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
    competitor_thumb_paths: List[str] = []
    if channel_id:
        try:
            from pipeline.analytics.competitor_intelligence import (
                build_thumbnail_competitor_block,
                get_competitor_thumbnail_samples,
            )
            competitor_block = build_thumbnail_competitor_block(channel_id) or ""
            competitor_thumb_paths = get_competitor_thumbnail_samples(
                channel_id, max_images=6
            ) or []
        except Exception as e:
            print(f"  ⚠️ thumbnail competitor block failed: {e}")
        if competitor_block:
            competitor_block = "\n\n" + competitor_block + "\n"

    vision_intro = ""
    if competitor_thumb_paths:
        vision_intro = (
            "\n以下に競合チャンネルの人気動画サムネイル画像 "
            f"{len(competitor_thumb_paths)} 枚を添付します。"
            "実際のビジュアル傾向（色使い・構図・文字配置・キャラ表情・密度）を分析し、"
            "効果的な要素は取り入れつつ、競合と一目で見分けがつく独自デザインを提案してください。"
            "丸パクリは禁止です。\n"
        )

    has_vision = bool(competitor_thumb_paths)
    system = (
        "あなたはYouTubeで何百万再生も叩き出すサムネイルを設計する一流のアートディレクターです。"
        "日本語のゆっくり解説／知識系チャンネル向けに、思わずクリックしたくなる"
        "サムネイル案を厳密なJSONで返します。"
        + (
            " 競合チャンネル分析の知見が提供された場合、その効果的な要素は積極的に取り入れつつ、"
            "丸パクリは避け、自チャンネルの個性を必ず重ねます。"
            if competitor_block else ""
        )
        + (
            " 添付された競合サムネイル画像が提供された場合は、視覚的傾向を読み取り、"
            "差別化しつつ強い要素は活かす方向で設計します。"
            if has_vision else ""
        )
    )
    style_hint_block = ""
    if style_hint:
        style_hint_block = (
            "\n【チャンネル固有のサムネ・スタイル方針 — 最優先で従う】\n"
            + style_hint.strip()
            + "\n"
        )

    user = (
        f"動画タイトル: 「{title}」\n"
        + (f"チャンネル: 「{channel_name}」 — {concept}\n" if channel_name else "")
        + style_hint_block
        + feedback_block
        + competitor_block
        + vision_intro
        + "\n"
        "サムネイルは固定レイアウトです。次のフィールドを必ず含むJSONだけを返してください"
        "（コードフェンス禁止、純JSON）:\n"
        "{\n"
        # 2026-08-18: サムネは「説明」ではなく「衝動」。スマホの一覧では 1 行が長いほど
        # 文字が縮んで読めなくなるので、上限を 14/12 → 11/9 文字へ詰めて大きく見せる。
        '  "line1": "1行目（白文字、状況/前振り。最大11文字。短いほど大きく表示される）",\n'
        '  "line2": "2行目（黄色強調、核となる驚き/疑問。最大9文字、!?推奨。ここが一番大きい）",\n'
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
        "- 文字は「短く・大きく」。説明文にせず、単語で言い切る"
        "（✅「実は逆だった」/ ❌「実は逆だったという事実」)\n"
        "- 各行は別々の事実/煽り（同じことを言わない)\n"
        "- DALL-E 3 は文字を綺麗に描けないので背景プロンプトは必ず『no text/letters/numbers』を明記"
    )

    if competitor_thumb_paths:
        user_content: Any = [{"type": "text", "text": user}]
        for img_path in competitor_thumb_paths:
            try:
                p = Path(img_path)
                if not p.exists() or p.stat().st_size == 0:
                    continue
                mime, _ = mimetypes.guess_type(str(p))
                if not mime:
                    mime = "image/jpeg"
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{b64}",
                        "detail": "low",
                    },
                })
            except Exception as e:
                print(f"  ⚠️ skipped competitor thumbnail image {img_path}: {e}")
    else:
        user_content = user

    resp = _call_openai(
        "https://api.openai.com/v1/chat/completions",
        openai_compat.build_chat_payload(
            BRIEF_MODEL,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.9,
            response_format={"type": "json_object"},
        ),
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
def generate_background(
    brief: Dict[str, Any],
    api_key: str,
    out_path: Path,
    channel_config: Optional[Dict[str, Any]] = None,
) -> Path:
    """Call gpt-image-1 and save a 1280x720 PNG to `out_path`.

    `channel_config.thumbnail_template.background_style_suffix` — if set,
    overrides the default "Style: …" sentence appended to the bg prompt. Use
    this to push toward bright/cheerful for daylight channels, or keep the
    default dark-cinematic look for dark/horror channels.
    """
    bg_concept = brief.get("background_concept", "")
    tmpl = ((channel_config or {}).get("thumbnail_template") or {})
    style_suffix = (tmpl.get("background_style_suffix") or "").strip() or (
        "Style: bold, eye-catching YouTube thumbnail aesthetic, high contrast, "
        "saturated colors, dramatic lighting, shallow depth of field, "
        "cinematic, photo-realistic close-up."
    )
    prompt = (
        f"{bg_concept}\n"
        f"{style_suffix} "
        "STRICT: absolutely no text, no letters, no numbers, no Japanese characters, "
        "no captions, no logos anywhere in the image. "
        "Composition: wide 16:9 horizontal, leave the bottom ~25% visually simpler "
        "(soft gradient or out-of-focus background) so big Japanese title text can be overlaid later."
    )
    resp = _call_openai(
        "https://api.openai.com/v1/images/generations",
        {
            "model": "gpt-image-1",
            "prompt": prompt,
            "n": 1,
            "size": "1536x1024",
            "quality": "high",
        },
        api_key,
        timeout=240,
    )
    img_b64 = resp["data"][0]["b64_json"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(img_b64))

    # gpt-image-1 returns 1536x1024 (3:2); crop center to 16:9 then resize to 1280x720
    try:
        from PIL import Image
        img = Image.open(out_path).convert("RGB")
        target_ratio = 1280 / 720
        w, h = img.size
        src_ratio = w / h
        if src_ratio > target_ratio:
            new_w = int(round(h * target_ratio))
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        elif src_ratio < target_ratio:
            new_h = int(round(w / target_ratio))
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))
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
.top-gradient {{ position: absolute; top: 0; left: 0; right: 0; height: {top_h}%;
  background: linear-gradient(to bottom, rgba(0,0,0,{top_o1}) 0%, rgba(0,0,0,{top_o2}) 60%, transparent 100%); }}
.bottom-gradient {{ position: absolute; bottom: 0; left: 0; right: 0; height: {bot_h}%;
  background: linear-gradient(to top, rgba(0,0,0,{bot_o1}) 0%, rgba(0,0,0,{bot_o2}) 50%, transparent 100%); }}
.text-line {{ position: absolute; left: 0; right: 0; text-align: center;
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 900; letter-spacing: 0.04em;
  /* 背景写真から文字を浮かせる影。縁取り(text-shadow)だけだと、背景が
     明るい/ごちゃついた写真のときにエッジが埋もれて可読性が落ちる。 */
  filter: drop-shadow(0 5px 12px rgba(0,0,0,0.80)); }}
.line1 {{ top: 18px; font-size: {line1_px}px; color: {c_line1};
  text-shadow:
    -4px -4px 0 {c_line1_edge}, 4px -4px 0 {c_line1_edge}, -4px 4px 0 {c_line1_edge}, 4px 4px 0 {c_line1_edge},
    -6px 0 0 {c_line1_edge}, 6px 0 0 {c_line1_edge}, 0 -6px 0 {c_line1_edge}, 0 6px 0 {c_line1_edge},
    -3px -5px 0 {c_line1_edge}, 3px -5px 0 {c_line1_edge}, -3px 5px 0 {c_line1_edge}, 3px 5px 0 {c_line1_edge},
    -5px -3px 0 {c_line1_edge}, 5px -3px 0 {c_line1_edge}, -5px 3px 0 {c_line1_edge}, 5px 3px 0 {c_line1_edge}; }}
.line2 {{ top: 135px; font-size: {line2_px}px; color: {c_line2};
  text-shadow:
    -5px -5px 0 {c_line2_edge}, 5px -5px 0 {c_line2_edge}, -5px 5px 0 {c_line2_edge}, 5px 5px 0 {c_line2_edge},
    -7px 0 0 {c_line2_edge}, 7px 0 0 {c_line2_edge}, 0 -7px 0 {c_line2_edge}, 0 7px 0 {c_line2_edge},
    -4px -6px 0 {c_line2_edge}, 4px -6px 0 {c_line2_edge}, -4px 6px 0 {c_line2_edge}, 4px 6px 0 {c_line2_edge},
    -6px -4px 0 {c_line2_edge}, 6px -4px 0 {c_line2_edge}, -6px 4px 0 {c_line2_edge}, 6px 4px 0 {c_line2_edge}; }}
.line3-wrap {{ position: absolute; top: 296px; left: 0; right: 0; text-align: center; }}
.line3-badge {{ display: inline-block; background: {c_badge_bg};
  border: 4px solid {c_badge_border}; border-radius: 14px; padding: 8px 36px;
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 900; font-size: {line3_px}px; color: {c_badge_text}; letter-spacing: 0.05em;
  filter: drop-shadow(0 5px 12px rgba(0,0,0,0.80));
  text-shadow:
    -3px -3px 0 {c_badge_edge}, 3px -3px 0 {c_badge_edge},
    -3px 3px 0 {c_badge_edge}, 3px 3px 0 {c_badge_edge},
    -5px 0 0 {c_badge_edge}, 5px 0 0 {c_badge_edge},
    0 -5px 0 {c_badge_edge}, 0 5px 0 {c_badge_edge}; }}
.sub-text {{ position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
  font-size: {sub_px}px; color: {c_sub};
  font-family: "Noto Sans JP", "Hiragino Kaku Gothic Std", "Hiragino Sans", "Yu Gothic", sans-serif;
  font-weight: 700;
  filter: drop-shadow(0 4px 10px rgba(0,0,0,0.80));
  text-shadow:
    -3px -3px 0 {c_sub_edge}, 3px -3px 0 {c_sub_edge}, -3px 3px 0 {c_sub_edge}, 3px 3px 0 {c_sub_edge},
    -4px 0 0 {c_sub_edge}, 4px 0 0 {c_sub_edge}, 0 -4px 0 {c_sub_edge}, 0 4px 0 {c_sub_edge};
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


_DEFAULT_OVERLAY = {
    "top_height_pct": 60,
    "top_opacity_start": 0.75,
    "top_opacity_mid": 0.30,
    "bottom_height_pct": 45,
    "bottom_opacity_start": 0.70,
    "bottom_opacity_mid": 0.30,
}


# サムネの配色。全チャンネルが同じ配色だと、ブラウズ面や検索結果で自社の動画
# 同士が見分けられず、サムネがチャンネルの記号として機能しない。
# チャンネル JSON には既に `thumbnail_template.badge_color / hook_color /
# subtitle_color`（RGB三値、clip_factory のレンダラが使用）があるので、
# 新しいキーを増やさずそれをこの HTML テンプレートにも流し込む。
# 縁取り色はバッジ色を暗く落として作るため、1チャンネル1アクセント色で揃う。
_FALLBACK_BADGE_RGB = (220, 40, 40)
_FALLBACK_HOOK_RGB = (255, 235, 60)
_FALLBACK_SUB_RGB = (255, 240, 100)


def _as_rgb(value: Any, fallback: tuple) -> tuple:
    """`[r, g, b]` を (r, g, b) に正規化する。不正値は fallback。"""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(c))) for c in value[:3])
        except (TypeError, ValueError):
            return fallback
    return fallback


def _darken(rgb: tuple, factor: float) -> tuple:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def _css(rgb: tuple, alpha: Optional[float] = None) -> str:
    r, g, b = rgb
    if alpha is None:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r}, {g}, {b}, {alpha})"


def _resolve_palette(channel_config: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """チャンネルのアクセント色からサムネ配色を組み立てる。

    `thumbnail_template.palette` に CSS 色文字列を置けば個別に上書きできる
    （キーは戻り値の各キー）。上書きが無ければバッジ/フック/サブの RGB から導出する。
    """
    tmpl = ((channel_config or {}).get("thumbnail_template") or {})
    badge = _as_rgb(tmpl.get("badge_color"), _FALLBACK_BADGE_RGB)
    hook = _as_rgb(tmpl.get("hook_color"), _FALLBACK_HOOK_RGB)
    sub = _as_rgb(tmpl.get("subtitle_color"), _FALLBACK_SUB_RGB)

    out = {
        "line1": "#FFFFFF",                      # 上段の見出しは常に白（背景を選ばない）
        "line1_edge": "#000000",
        "line2": _css(hook),                     # 中央の主役行 = チャンネルのフック色
        "line2_edge": _css(_darken(badge, 0.45)),
        "badge_bg": _css(badge, 0.93),
        "badge_border": "rgba(255,255,255,0.9)",
        "badge_text": "#FFFFFF",
        "badge_edge": _css(_darken(badge, 0.35), 0.9),
        "sub": _css(sub),
        "sub_edge": _css(_darken(badge, 0.22)),
    }
    overrides = tmpl.get("palette") or {}
    for k in out:
        v = overrides.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def _resolve_overlay(channel_config: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Merge per-channel `thumbnail_template.gradient_overlay` over the defaults."""
    tmpl = ((channel_config or {}).get("thumbnail_template") or {})
    overlay = tmpl.get("gradient_overlay") or {}
    out = dict(_DEFAULT_OVERLAY)
    for k in out:
        if k in overlay:
            out[k] = overlay[k]
    return out


def build_html(
    brief: Dict[str, Any],
    bg_path: Path,
    char_left: Optional[Path],
    char_right: Optional[Path],
    channel_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Compose a self-contained HTML string (all images as data URIs).

    `channel_config.thumbnail_template.gradient_overlay` — optional overrides
    for top/bottom darkening overlays. Keys: top_height_pct, top_opacity_start,
    top_opacity_mid, bottom_height_pct, bottom_opacity_start, bottom_opacity_mid.
    Lower opacities preserve more of the original background brightness.

    `channel_config.thumbnail_template.palette` — optional per-channel colors
    (see `_DEFAULT_PALETTE` for the keys). Used to keep each channel's
    thumbnails visually distinct from the others in browse/search.
    """
    line1 = (brief.get("line1") or "").strip()
    line2 = (brief.get("line2") or "").strip()
    line3 = (brief.get("line3_badge") or "").strip()
    sub = (brief.get("sub_text") or "").strip()

    # 基準文字数を詰めた分、同じ幅に対して 1 文字あたりを大きく取れる
    # （11 文字までは 100px、9 文字までは 124px でフル表示）。
    line1_px = _scaled_font_px(line1, 100, 11, 56)
    line2_px = _scaled_font_px(line2, 124, 9, 64)
    line3_px = _scaled_font_px(line3, 82, 10, 52)
    sub_px = _scaled_font_px(sub, 38, 22, 26)

    overlay = _resolve_overlay(channel_config)
    palette = _resolve_palette(channel_config)

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
        top_h=overlay["top_height_pct"],
        top_o1=overlay["top_opacity_start"],
        top_o2=overlay["top_opacity_mid"],
        bot_h=overlay["bottom_height_pct"],
        bot_o1=overlay["bottom_opacity_start"],
        bot_o2=overlay["bottom_opacity_mid"],
        c_line1=palette["line1"],
        c_line1_edge=palette["line1_edge"],
        c_line2=palette["line2"],
        c_line2_edge=palette["line2_edge"],
        c_badge_bg=palette["badge_bg"],
        c_badge_border=palette["badge_border"],
        c_badge_text=palette["badge_text"],
        c_badge_edge=palette["badge_edge"],
        c_sub=palette["sub"],
        c_sub_edge=palette["sub_edge"],
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
            "style_hint": (channel_config.get("thumbnail_template") or {}).get("style_hint"),
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
        generate_background(brief, api_key, bg_path, channel_config=channel_config)

    char_left, char_right = resolve_character_paths(channel_config)
    html = build_html(brief, bg_path, char_left, char_right, channel_config=channel_config)
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
                "style_hint": (channel_config.get("thumbnail_template") or {}).get("style_hint"),
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
        await loop.run_in_executor(
            None,
            lambda: generate_background(brief, api_key, bg_path, channel_config=channel_config),
        )

    char_left, char_right = resolve_character_paths(channel_config)
    html = build_html(brief, bg_path, char_left, char_right, channel_config=channel_config)
    await render_html_to_png_async(html, output_path)

    return {
        "thumbnail_path": str(output_path),
        "background_path": str(bg_path),
        "brief": brief,
    }
