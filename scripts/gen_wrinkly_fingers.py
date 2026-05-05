"""Generate a single DALL-E 3 illustration for the 'why fingers wrinkle in water' theme.

Uses illustration_style settings from data/channels/daily-science.json.
"""
import os
import sys
import json
import base64
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"
CHANNEL_JSON = ROOT / "data" / "channels" / "daily-science.json"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not found in backend/.env", file=sys.stderr)
    sys.exit(1)

channel = json.loads(CHANNEL_JSON.read_text())
ill = channel["video_format"]["illustration_style"]
ART_STYLE = ill["art_style"]
BACKGROUND = ill["background"]
EXTRA = ill["extra_prompt"]

OUT_PATH = ROOT / "sample_wrinkly_fingers.png"

THEME_DESCRIPTION = (
    "Theme: Why do fingers wrinkle when soaked in water (お風呂で指がシワシワになる理由). "
    "Scientific content to convey: it is NOT passive osmosis swelling the skin, but an "
    "ACTIVE response controlled by the sympathetic nervous system. The brain sends a "
    "signal that constricts blood vessels in the fingertips, causing the skin to wrinkle. "
    "Purpose: increases grip on wet surfaces — same principle as tire treads channeling "
    "away water. It was evolutionarily advantageous."
)

COMPOSITION = (
    "Composition: split into clearly separated comic-panel sections inside one wide "
    "landscape frame. "
    "(1) On the left: a cartoon hand soaking in a bathtub with bubbles, fingertips "
    "visibly wrinkled with exaggerated soft ridges, with a small Japanese label "
    "'お風呂で指がシワシワ！'. "
    "(2) In the center: an anthropomorphized cross-section of fingertip skin — the "
    "skin layer has small calm dot-and-curve eyes and a determined expression. A "
    "tiny cartoon nerve fiber (also gently anthropomorphized) is shouting an order "
    "with a speech bubble saying 'シワにしろ！' and a lightning bolt icon. Blue "
    "arrows show blood vessels constricting. Japanese labels: '交感神経の指令！', "
    "'血管が収縮', '皮膚がシワに'. "
    "(3) On the right: a side-by-side comparison panel showing a car tire with deep "
    "treads next to a wrinkled fingertip, with a label '同じ原理！' and arrows "
    "showing water being channeled away. Add a small label 'グリップ力UP！'. "
    "Include a small evolution icon (a tiny footprint or DNA helix) with the label "
    "'進化的に有利だった' tucked in a corner. "
    "Keep all text and labels in clear, legible Japanese."
)

PROMPT = (
    f"{ART_STYLE} "
    f"{THEME_DESCRIPTION} "
    f"{COMPOSITION} "
    f"Background: {BACKGROUND}. "
    f"{EXTRA} "
    "Wide horizontal landscape composition (16:9). All text and labels in clear Japanese."
)

print("Calling DALL-E 3 (size=1792x1024, style=vivid)...")
payload = json.dumps({
    "model": "dall-e-3",
    "prompt": PROMPT,
    "n": 1,
    "size": "1792x1024",
    "style": "vivid",
    "response_format": "b64_json",
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.openai.com/v1/images/generations",
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    },
)

try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"HTTPError {e.code}: {body}", file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(2)

img_b64 = data["data"][0]["b64_json"]
OUT_PATH.write_bytes(base64.b64decode(img_b64))
revised = data["data"][0].get("revised_prompt", "")
print(f"OK: saved {OUT_PATH}")
print(f"revised_prompt:\n{revised}")
