"""thumb_style — `thumbnail_template.style_hint` をショートサムネ（Pillow 描画）に効かせる。

背景（2026-09-14）:
    style_hint は長尺サムネ（HTML+デザインブリーフ）のプロンプトにしか渡っておらず、
    ショートサムネ（`video_generator.generate_short_thumbnail`）は配色キー
    （short_bg_gradient / hook_color …）しか見ていなかった。company-facts の
    「実店舗写真を背景に」、2ch-matome の「お題そのものが写った明るい写真」、
    socio-rx の「ティール〜ネイビーに白い明朝体」は 1 本も反映されず、
    全チャンネルが同じ「グラデ＋光る玉」の構図で出ていた。

設計:
    style_hint（自然文）を、Pillow で決定論的に描ける **パラメータ** に翻訳する。
        {
          "background": "gradient" | "photo",
          "bg_query":   写真検索クエリ。{subject} / {title} を差し込める,
          "overlay":    {"rgb": [r,g,b], "alpha": 0-255}   写真の上に敷く色（文字の可読性）,
          "palette":    {"top","bottom","orb","dot"} 各 [r,g,b]  グラデ配色,
          "font":       "gothic" | "mincho",
          "mood":       "dark" | "bright" | "neutral"
        }
    翻訳は 1 チャンネルにつき 1 回だけ LLM に頼み（style_hint のハッシュでキャッシュ）、
    LLM が使えなければ語句ヒューリスティックで組む。明示設定
    `thumbnail_template.short_style` があればそれが最優先（LLM を呼ばない）。

    配色は「明示キー（short_bg_gradient 等）＞ style から導いた palette」の順。
    既存チャンネルの見た目を勝手に変えないため、明示キーがある項目は触らない。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_CACHE_PATH = (Path(__file__).resolve().parent.parent.parent
               / "data" / "thumbnails" / "short_style_cache.json")

_VALID_BG = ("gradient", "photo")
_VALID_FONT = ("gothic", "mincho")
_VALID_MOOD = ("dark", "bright", "neutral")

# 語句ヒューリスティック（LLM が使えないとき／翻訳に失敗したとき）
_PHOTO_WORDS = ("写真", "実写", "実店舗", "フレーム", "photo", "photograph")
_MINCHO_WORDS = ("明朝", "箔押し", "セリフ", "serif", "古文書", "羊皮紙")
_DARK_WORDS = ("暗い", "ダーク", "闇", "黒", "濃紺", "ネイビー", "血", "霧", "陰", "不気味", "ホラー", "暗がり")
_BRIGHT_WORDS = ("明るい", "明るく", "カラフル", "ポップ", "楽しい", "パステル", "白背景")

_COLOR_WORDS = {
    "ティール": (16, 84, 84), "teal": (16, 84, 84), "ネイビー": (12, 24, 56), "navy": (12, 24, 56),
    "濃紺": (12, 24, 56), "藍": (26, 30, 88), "紫": (70, 30, 110), "パープル": (70, 30, 110),
    "赤": (150, 20, 24), "血": (110, 10, 14), "黒": (10, 10, 12), "緑": (20, 90, 50),
    "エメラルド": (20, 140, 100), "金": (212, 175, 95), "オレンジ": (220, 120, 30),
    "黄": (230, 200, 40), "青": (30, 70, 160), "水色": (90, 170, 230), "ピンク": (220, 90, 160),
    "白": (240, 240, 240), "茶": (90, 60, 30), "セピア": (110, 85, 55),
}


def _clamp_rgb(v: Any, fallback: Optional[List[int]] = None) -> Optional[List[int]]:
    try:
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            return [max(0, min(255, int(x))) for x in v[:3]]
    except (TypeError, ValueError):
        pass
    return fallback


def _normalize(spec: Any) -> Optional[Dict[str, Any]]:
    """LLM / 設定 / ヒューリスティックの出力を安全な形に揃える。駄目なら None。"""
    if not isinstance(spec, dict):
        return None
    out: Dict[str, Any] = {}
    bg = str(spec.get("background") or "gradient").strip().lower()
    out["background"] = bg if bg in _VALID_BG else "gradient"
    q = spec.get("bg_query")
    out["bg_query"] = str(q).strip()[:160] if isinstance(q, str) and q.strip() else None
    ov = spec.get("overlay")
    if isinstance(ov, dict):
        rgb = _clamp_rgb(ov.get("rgb"))
        try:
            alpha = max(0, min(255, int(ov.get("alpha", 120))))
        except (TypeError, ValueError):
            alpha = 120
        out["overlay"] = {"rgb": rgb or [0, 0, 0], "alpha": alpha}
    else:
        out["overlay"] = None
    pal = spec.get("palette")
    if isinstance(pal, dict):
        p2 = {k: _clamp_rgb(pal.get(k)) for k in ("top", "bottom", "orb", "dot")}
        out["palette"] = {k: v for k, v in p2.items() if v} or None
    else:
        out["palette"] = None
    font = str(spec.get("font") or "gothic").strip().lower()
    out["font"] = font if font in _VALID_FONT else "gothic"
    mood = str(spec.get("mood") or "neutral").strip().lower()
    out["mood"] = mood if mood in _VALID_MOOD else "neutral"
    out["notes"] = str(spec.get("notes") or "")[:200]
    return out


# ---------------------------------------------------------------------
# ヒューリスティック翻訳
# ---------------------------------------------------------------------

def heuristic_style(style_hint: str) -> Dict[str, Any]:
    """style_hint の語句から機械的にパラメータを組む（LLM 不要）。"""
    h = style_hint or ""
    # 「暗いホラー調にはしない」「派手な赤は使わない」のような**禁止文**は、
    # その色・トーンを採用しない根拠なので、語の数え上げから外す。
    _NEG = ("しない", "使わない", "禁止", "避け", "NG", "ない", "不可", "厳禁")
    positive = "\n".join(
        seg for seg in re.split(r"[。\n]", h)
        if seg.strip() and not any(n in seg for n in _NEG))
    low = positive.lower()
    photo = any(w in low for w in _PHOTO_WORDS)
    mincho = any(w in low for w in _MINCHO_WORDS)
    dark_n = sum(low.count(w) for w in _DARK_WORDS)
    bright_n = sum(low.count(w) for w in _BRIGHT_WORDS)
    mood = "dark" if dark_n > bright_n else ("bright" if bright_n > dark_n else "neutral")

    # 出現順で最初の2色をグラデに使う
    found: List[tuple] = []
    for word, rgb in _COLOR_WORDS.items():
        i = positive.find(word)
        if i >= 0:
            found.append((i, word, rgb))
    found.sort()
    colors = [rgb for _, _, rgb in found if rgb not in ((240, 240, 240),)]
    palette = None
    if colors:
        top = colors[0]
        bottom = colors[1] if len(colors) > 1 else tuple(max(0, int(c * 0.35)) for c in top)
        orb = colors[2] if len(colors) > 2 else tuple(min(255, int(c * 1.6) + 30) for c in top)
        dot = next((rgb for _, w, rgb in found if w in ("金", "オレンジ", "黄", "エメラルド", "ピンク")), None) \
            or tuple(min(255, c + 90) for c in orb)
        palette = {"top": list(top), "bottom": list(bottom), "orb": list(orb), "dot": list(dot)}

    overlay = None
    if photo:
        overlay = ({"rgb": [0, 0, 0], "alpha": 150} if mood == "dark"
                   else {"rgb": [255, 180, 80], "alpha": 90} if "暖色" in h
                   else {"rgb": [0, 0, 0], "alpha": 110})
    return _normalize({
        "background": "photo" if photo else "gradient",
        "bg_query": "{subject}" if photo else None,
        "overlay": overlay,
        "palette": palette,
        "font": "mincho" if mincho else "gothic",
        "mood": mood,
        "notes": "heuristic",
    }) or {}


# ---------------------------------------------------------------------
# LLM 翻訳（チャンネルごとに 1 回・キャッシュ）
# ---------------------------------------------------------------------

_PROMPT_SYSTEM = (
    "あなたは YouTube ショートのサムネイルを Pillow（プログラム描画）で作る設計者です。"
    "自然文のスタイル方針を、描画パラメータの JSON に翻訳します。JSON 以外は出力しません。"
)


def _prompt_user(style_hint: str, channel_name: str, concept: str) -> str:
    return (
        f"チャンネル: {channel_name} — {concept}\n\n"
        f"スタイル方針:\n{style_hint}\n\n"
        "縦 1080x1920 のショートサムネです。描けるのは次の要素だけです:\n"
        "  - 背景: グラデーション（top→bottom の2色＋光る玉 orb・散らし dot）か、"
        "写真（検索クエリで取得。上に半透明の色を敷いて文字を読めるようにする）\n"
        "  - 見出し・サブ見出しのフォント: ゴシック or 明朝\n"
        "次の JSON だけを返してください:\n"
        "{\n"
        '  "background": "gradient" | "photo",\n'
        '  "bg_query": "写真のとき: 英語の検索クエリ。題材を入れる位置に {subject} と書く（例: \\"{subject} storefront exterior\\"）。グラデのとき null",\n'
        '  "overlay": {"rgb": [r,g,b], "alpha": 0-255} | null   （写真の上に敷く色。暗いトーンなら黒系、明るく暖かい方針なら暖色の薄い層）,\n'
        '  "palette": {"top": [r,g,b], "bottom": [r,g,b], "orb": [r,g,b], "dot": [r,g,b]}   （方針の色を必ず反映）,\n'
        '  "font": "gothic" | "mincho",\n'
        '  "mood": "dark" | "bright" | "neutral",\n'
        '  "notes": "20字以内の要約"\n'
        "}\n"
        "方針に写真・実写・実店舗・フレームとあれば background は photo。"
        "方針が禁じている色（例: 派手な赤）は palette に入れない。"
    )


def _llm_translate(style_hint: str, channel_name: str, concept: str,
                   api_key: Optional[str]) -> Optional[Dict[str, Any]]:
    user = _prompt_user(style_hint, channel_name, concept)
    # Claude が使えれば Claude（→ claude_client。無効キーは has_api_key が False を返す）
    try:
        from pipeline import claude_client
        if claude_client.has_api_key():
            got = claude_client.call_claude_json(
                system=_PROMPT_SYSTEM, user=user, temperature=0.3, purpose="thumb_style")
            spec = _normalize(got)
            if spec:
                return spec
    except Exception as e:
        print(f"  ⚠️ thumb_style: Claude 翻訳に失敗: {e}")
    # OpenAI（退避口）
    try:
        from pipeline import openai_compat, openai_policy
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if key and openai_policy.direct_text_api_allowed():
            from pipeline.thumbnail_generator import _call_openai
            model = os.environ.get("THUMB_STYLE_MODEL", "gpt-5.6-luna")
            resp = _call_openai(
                "https://api.openai.com/v1/chat/completions",
                openai_compat.build_chat_payload(
                    model,
                    [{"role": "system", "content": _PROMPT_SYSTEM},
                     {"role": "user", "content": user}],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                ),
                key,
            )
            spec = _normalize(json.loads(resp["choices"][0]["message"]["content"]))
            if spec:
                return spec
    except Exception as e:
        print(f"  ⚠️ thumb_style: GPT 翻訳に失敗: {e}")
    return None


def _load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"  ⚠️ thumb_style: キャッシュを読めないので作り直します: {e}")
        return {}


def _save_cache(data: Dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_PATH.with_name(_CACHE_PATH.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _CACHE_PATH)
    except Exception as e:
        print(f"  ⚠️ thumb_style: キャッシュを保存できません: {e}")


def resolve(channel_dict: Optional[Dict[str, Any]], *, api_key: Optional[str] = None,
            use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """チャンネル設定からショートサムネのスタイルパラメータを返す。方針が無ければ None。"""
    raw = channel_dict or {}
    tt = raw.get("thumbnail_template") or {}
    explicit = _normalize(tt.get("short_style"))
    if explicit:
        explicit["source"] = "short_style"
        return explicit
    hint = str(tt.get("style_hint") or "").strip()
    if not hint:
        return None
    cid = str(raw.get("id") or "?")
    key = f"{cid}:{hashlib.sha1(hint.encode('utf-8')).hexdigest()[:12]}"
    cache = _load_cache()
    hit = _normalize(cache.get(key))
    if hit:
        hit["source"] = "cache"
        return hit
    spec = None
    if use_llm:
        spec = _llm_translate(hint, str(raw.get("name") or cid), str(raw.get("concept") or ""), api_key)
        if spec:
            spec["source"] = "llm"
    if not spec:
        spec = heuristic_style(hint)
        spec["source"] = "heuristic"
    cache[key] = {k: v for k, v in spec.items() if k != "source"}
    _save_cache(cache)
    print(f"  🎨 thumb_style[{cid}]: {spec['background']} / font={spec['font']} / "
          f"mood={spec['mood']} ({spec['source']}: {spec.get('notes', '')})")
    return spec


_SUBJECT_TOKEN_RE = re.compile(r"[一-龥々ァ-ヶーA-Za-z0-9]{2,}")


def bg_query_for(spec: Dict[str, Any], title: str, channel_dict: Optional[Dict[str, Any]] = None,
                 subject: Optional[str] = None) -> Optional[str]:
    """写真背景の検索クエリを組む。{subject} / {title} を差し込む。"""
    q = (spec or {}).get("bg_query")
    if not q:
        return None
    subj = (subject or "").strip()
    if not subj:
        try:
            from pipeline.auto_scenario import theme_dedup as _td
            toks = _td._content_tokens(title or "")
        except Exception:
            toks = _SUBJECT_TOKEN_RE.findall(title or "")
        subj = toks[0] if toks else (title or "")[:12]
    return q.replace("{subject}", subj).replace("{title}", (title or "")[:60]).strip()
