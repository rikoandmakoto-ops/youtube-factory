#!/usr/bin/env python3
"""
チャンネルアイコン（トプ画）生成 — 全チャンネル分

2段構え:
  Step 1  チャンネル背景（name / concept）＋ 実際に出した動画タイトル群を GPT に渡し、
          「そのチャンネルらしいアイコン」の設計ブリーフ（英語のimage prompt込み）を書かせる
  Step 2  ブリーフの image prompt を gpt-image-1 に投げて 1024x1024 を生成 → 800x800 に縮小して保存

タイトルの取得元は
  1. data/analytics/analytics.db の video_metrics（実際に公開された動画のタイトル）
  2. data/scenarios/<channel>/*.json の title（1がないチャンネルの補完）
の順。切り抜き系は投稿実績が薄いので config の clip 設定（切り抜き元タレント名）も渡す。

Step 1 のブリーフは output/channel-icons/briefs/<id>.json にキャッシュされるので、
Step 2 だけ落ちた（クレジット切れ等）場合の再実行では GPT を呼び直さない。

使い方:
    python3 gen_channel_icons.py                    # 全チャンネル（既存PNGはスキップ）
    python3 gen_channel_icons.py scp-lab fake-paper # 指定チャンネルだけ
    python3 gen_channel_icons.py --force            # 既存PNGも作り直す
    python3 gen_channel_icons.py --dry-run          # API を叩かず、渡す材料とプロンプトだけ確認
    python3 gen_channel_icons.py --brief-only       # Step 1 だけ（画像は生成しない）
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

ROOT = Path(__file__).resolve().parent

# ── 画像生成は ChatGPT のブラウザスレッド経由（OpenAI API 直叩きはしない） ──
# 手順: docs/CHATGPT_IMAGE_BRIDGE.md
sys.path.insert(0, str(ROOT / "backend"))
from pipeline import chatgpt_image_bridge as _bridge  # noqa: E402

ENV_PATH = ROOT / "backend" / ".env"
CHANNELS_DIR = ROOT / "data" / "channels"
SCENARIOS_DIR = ROOT / "data" / "scenarios"
ANALYTICS_DB = ROOT / "data" / "analytics" / "analytics.db"

OUT_DIR = ROOT / "output" / "channel-icons"
BRIEF_DIR = OUT_DIR / "briefs"

CHAT_URL = "https://api.openai.com/v1/chat/completions"
BRIEF_MODEL = "gpt-5.6-terra"
IMAGE_MODEL = "gpt-image-1"
GEN_SIZE = "1024x1024"
FINAL_SIZE = (800, 800)
MAX_TITLES = 25
TIMEOUT = 600
MAX_RETRIES = 3

# 生成対象。data/channels/<id>.json が存在するものだけを扱う。
CHANNEL_IDS = [
    "scp-lab",
    "daily-science",
    "pokemon-lab",
    "yokai-watch",
    "2ch-matome",
    "company-facts",
    "clip-lab",
    "fake-paper",
    "akashic-librarian",
    "clip-fukada",
    "clip-kaneko",
]


# ──────────────────────────────────────────────────────────────────────────
# 素材集め
# ──────────────────────────────────────────────────────────────────────────
def load_channel_config(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"channel config が無い: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def published_titles(channel_id: str, limit: int = MAX_TITLES) -> List[str]:
    """実際に公開された動画のタイトル（再生数の多い順）。"""
    if not ANALYTICS_DB.exists():
        return []
    con = sqlite3.connect(f"file:{ANALYTICS_DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """
            SELECT title, MAX(views) AS v
              FROM video_metrics
             WHERE channel_id = ? AND title IS NOT NULL AND title <> ''
             GROUP BY video_id
             ORDER BY v DESC
             LIMIT ?
            """,
            (channel_id, limit),
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def scenario_titles(channel_id: str, limit: int = MAX_TITLES) -> List[str]:
    """台本から拾ったタイトル（公開実績が取れないチャンネルの補完）。"""
    d = SCENARIOS_DIR / channel_id
    if not d.is_dir():
        return []
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[str] = []
    for f in files:
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        title = data.get("title") or (data.get("theme") or {}).get("title")
        if title:
            out.append(str(title))
        if len(out) >= limit:
            break
    return out


def clip_sources(cfg: Dict[str, Any]) -> List[str]:
    """切り抜きチャンネルの切り抜き元（タレント名）。"""
    names: List[str] = []
    allow = ((cfg.get("clip") or {}).get("external_sources") or {}).get(
        "allowlist_channels"
    ) or []
    for entry in allow:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("channel_title") or entry.get("label")
            if name:
                names.append(str(name))
    return names


def collect_material(channel_id: str) -> Dict[str, Any]:
    cfg = load_channel_config(channel_id)
    real = published_titles(channel_id)
    fallback = scenario_titles(channel_id)
    titles = real or fallback
    return {
        "channel_id": channel_id,
        "name": cfg.get("name", channel_id),
        "concept": cfg.get("concept", ""),
        "style": cfg.get("style", ""),
        "series_name": cfg.get("short_series_name") or cfg.get("main_title_prefix") or "",
        "titles": titles,
        "titles_source": "published" if real else ("scenarios" if fallback else "none"),
        "clip_sources": clip_sources(cfg),
    }


# ──────────────────────────────────────────────────────────────────────────
# OpenAI
# ──────────────────────────────────────────────────────────────────────────
def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENAI_API_KEY が環境変数にも backend/.env にも見つからない")


def _post(url: str, payload: dict, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {e.code}: {detail}"
            # クレジット切れ・入力不正はリトライしても同じ
            if 400 <= e.code < 500 and e.code != 429:
                break
            if e.code == 429 and "insufficient_quota" in detail:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < MAX_RETRIES:
            wait = 10 * attempt
            print(f"    リトライ {attempt}/{MAX_RETRIES - 1} ({last}) — {wait}s 待機", flush=True)
            time.sleep(wait)
    raise RuntimeError(last or "unknown error")


# ──────────────────────────────────────────────────────────────────────────
# Step 1 — 設計ブリーフ
# ──────────────────────────────────────────────────────────────────────────
BRIEF_SYSTEM = """\
You are an art director designing YouTube channel profile pictures (avatars).

You will be given one Japanese YouTube channel: its name, its concept, and the titles of
videos it has actually published. Infer what the channel really is about from the titles —
not just from the concept text — and design an avatar that a viewer would instantly
associate with that content.

Hard constraints for the artwork you describe:
- Square 1:1, and it will be displayed as a SMALL CIRCLE (as small as 48px). Everything
  important must sit inside the safe central circle; nothing important in the corners.
- ONE clear focal subject. No busy scenes, no collages, no multiple competing elements.
- Bold, high-contrast, saturated colors that pop against both white and dark UI.
- Flat / vector-ish illustration or a clean stylized mascot bust. No photorealism.
- At most 3-4 characters of Japanese or Latin text, and only if it genuinely helps.
  Long text is unreadable at avatar size — prefer no text at all. Never write a sentence.
  EXCEPTION: if the channel is a clip channel built around one named talent, design a
  LOGOTYPE — the talent's name (up to 6 Japanese characters) as bold typography on a
  strong flat background, optionally with one simple graphic accent. Never depict the
  real person's face or likeness; the name itself is the design.
- No YouTube logo, no likeness of any real person, no copyrighted game/anime characters
  (Pokémon, Yo-kai Watch etc. must be evoked by generic original shapes only), no watermarks.

Return STRICT JSON with these keys:
{
  "concept_summary": "<1 sentence, Japanese — what this channel is, judging from the titles>",
  "focal_subject": "<the single subject of the icon, Japanese, 1 line>",
  "palette": "<3-4 colors with hex, Japanese, 1 line>",
  "text_on_icon": "<0-4 chars to bake in, or empty string>",
  "image_prompt": "<ONE English paragraph, 120-200 words, ready to send to an image model.
      Describe the subject, composition (centered, fills the frame, safe circular crop),
      the palette with hex codes, lighting, the flat vector style, and any baked-in text
      spelled out character by character. End by stating it is a YouTube channel avatar
      that must stay readable at 48x48 pixels.>"
}
"""


def build_brief_user_content(mat: Dict[str, Any]) -> str:
    lines = [
        f"チャンネル名: {mat['name']}",
        f"チャンネルID: {mat['channel_id']}",
        f"形式: {mat['style']}",
    ]
    if mat["series_name"]:
        lines.append(f"シリーズ名/接頭辞: {mat['series_name']}")
    lines.append(f"チャンネル概要（背景）: {mat['concept']}")
    if mat["clip_sources"]:
        lines.append("切り抜き元（このチャンネルの主役）: " + " / ".join(mat["clip_sources"]))
    if mat["titles"]:
        label = "実際に公開した動画タイトル" if mat["titles_source"] == "published" else "制作した動画タイトル"
        lines.append(f"\n{label}（{len(mat['titles'])}本）:")
        lines.extend(f"- {t}" for t in mat["titles"])
    else:
        lines.append("\n（このチャンネルはまだ公開実績が無い。概要から設計すること）")
    return "\n".join(lines)


def _fallback_brief(mat: Dict[str, Any]) -> Dict[str, Any]:
    """GPT が使えないときの決め打ちブリーフ（材料は同じものを使う）。"""
    if mat["clip_sources"]:
        # タレント切り抜きは似顔絵ではなく名前ロゴにする（実在人物の肖像を作らない）
        talent = mat["clip_sources"][0].split("/")[0].split("（")[0].strip()
        prompt = (
            f"A YouTube channel avatar that is a bold logotype for a Japanese clip "
            f"channel. Centered on the square canvas, the Japanese name "
            f"{talent} is set in heavy rounded gothic lettering, pure white with a "
            "thick dark outline, filling most of the central safe circle over a "
            "vivid two-tone radial-gradient background with one simple graphic accent "
            "such as a play triangle or a film-strip arc behind the letters. "
            "Flat vector style, high contrast, no photograph, no depiction of any real "
            "person, no face, no watermark, no YouTube logo. "
            "Square 1:1 YouTube channel avatar that stays readable at 48x48 pixels."
        )
        return {
            "concept_summary": mat["concept"][:120],
            "focal_subject": f"{talent} の名前ロゴ",
            "palette": "channel default",
            "text_on_icon": talent,
            "image_prompt": prompt,
            "_fallback": True,
        }

    subject = mat["name"]
    prompt = (
        f"A YouTube channel avatar for a Japanese channel called {mat['name']}. "
        f"Channel concept: {mat['concept'][:300]}. "
        f"Design one single bold centered emblem that symbolizes {subject}, "
        "drawn as a flat vector illustration with thick clean outlines, "
        "strong saturated colors and high contrast against a simple two-tone "
        "radial-gradient background. The subject fills the frame and sits entirely "
        "inside the central safe circle, with empty margins in the corners. "
        "No text, no logos, no watermark, no real-person likeness, no copyrighted "
        "characters. Simple silhouette, readable at 48x48 pixels. "
        "Square 1:1 YouTube channel avatar."
    )
    return {
        "concept_summary": mat["concept"][:120],
        "focal_subject": subject,
        "palette": "channel default",
        "text_on_icon": "",
        "image_prompt": prompt,
        "_fallback": True,
    }


def make_brief(mat: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    payload = {
        "model": BRIEF_MODEL,
        "messages": [
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": build_brief_user_content(mat)},
        ],
        "max_completion_tokens": 2000,
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
    }
    resp = _post(CHAT_URL, payload, api_key)
    brief = json.loads(resp["choices"][0]["message"]["content"])
    if not brief.get("image_prompt"):
        raise RuntimeError("brief に image_prompt が無い")
    return brief


# ──────────────────────────────────────────────────────────────────────────
# Step 2 — 画像
# ──────────────────────────────────────────────────────────────────────────
def generate_image(prompt: str, api_key: str) -> bytes:
    """ChatGPT スレッド経由でアイコンを1枚生成する。

    未納品なら `_bridge.Queued` を投げる。`api_key` は互換のため残しているが
    画像生成には使わない（OpenAI Images API は叩かない）。
    """
    return _bridge.generate_or_queue(
        prompt, size=GEN_SIZE, purpose="channel_icon",
    )


def to_icon(raw: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.size != FINAL_SIZE:
        img = img.resize(FINAL_SIZE, Image.LANCZOS)
    return img


# ──────────────────────────────────────────────────────────────────────────
def run(channel_ids: List[str], *, force: bool, dry_run: bool, brief_only: bool) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)

    api_key: Optional[str] = None if dry_run else load_api_key()
    failures = 0

    for i, cid in enumerate(channel_ids, 1):
        out_path = OUT_DIR / f"{cid}.png"
        print(f"\n[{i}/{len(channel_ids)}] {cid}", flush=True)

        if out_path.exists() and not force and not brief_only:
            print(f"    スキップ（既存: {out_path.relative_to(ROOT)}）", flush=True)
            continue

        try:
            mat = collect_material(cid)
        except FileNotFoundError as e:
            print(f"    NG: {e}", flush=True)
            failures += 1
            continue
        print(f"    材料: タイトル{len(mat['titles'])}本 ({mat['titles_source']})", flush=True)

        brief_path = BRIEF_DIR / f"{cid}.json"
        brief: Optional[Dict[str, Any]] = None
        if brief_path.exists() and not force:
            cached = json.loads(brief_path.read_text(encoding="utf-8"))
            if not cached.get("_fallback"):
                brief = cached
                print("    ブリーフ: キャッシュ再利用", flush=True)

        if brief is None:
            if dry_run:
                brief = _fallback_brief(mat)
                print("    --- GPT に渡す材料 ---")
                print(build_brief_user_content(mat))
                print("    --- フォールバック image_prompt ---")
                print(brief["image_prompt"])
                continue
            try:
                brief = make_brief(mat, api_key)
                print(f"    ブリーフ: {brief.get('focal_subject', '')}", flush=True)
            except (RuntimeError, KeyError, json.JSONDecodeError) as e:
                print(f"    ブリーフ生成失敗 → フォールバック使用: {e}", flush=True)
                brief = _fallback_brief(mat)
            brief["_material"] = mat
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        if brief_only:
            continue

        try:
            img = to_icon(generate_image(brief["image_prompt"], api_key))
        except RuntimeError as e:
            print(f"    NG（画像生成）: {e}", flush=True)
            failures += 1
            continue
        img.save(out_path, "PNG")
        print(f"    OK: {out_path.relative_to(ROOT)}  {img.size}", flush=True)

    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description="全チャンネルのトプ画（アイコン）を生成する")
    ap.add_argument("channels", nargs="*", help="対象チャンネルID（省略時は全部）")
    ap.add_argument("--force", action="store_true", help="既存の PNG / ブリーフも作り直す")
    ap.add_argument("--dry-run", action="store_true", help="API を叩かず材料とプロンプトを表示")
    ap.add_argument("--brief-only", action="store_true", help="Step 1（ブリーフ）だけ実行")
    args = ap.parse_args()

    targets = args.channels or CHANNEL_IDS
    unknown = [c for c in targets if not (CHANNELS_DIR / f"{c}.json").exists()]
    if unknown:
        raise SystemExit(f"不明なチャンネルID: {', '.join(unknown)}")

    failures = run(
        targets, force=args.force, dry_run=args.dry_run, brief_only=args.brief_only
    )
    print(f"\n完了: {len(targets) - failures}/{len(targets)} 成功", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
