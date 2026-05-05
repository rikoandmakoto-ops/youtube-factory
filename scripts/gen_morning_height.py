"""Generate a single DALL-E 3 illustration for the 'morning height' theme."""
import os
import sys
import json
import base64
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"

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

OUT_PATH = ROOT / "sample_morning_height.png"

PROMPT = (
    "A colorful hand-drawn educational illustration in a slightly more refined, "
    "textbook-diagram-leaning manga style — still pop and friendly, but a touch "
    "more serious and structured than typical kawaii art. "
    "Main subject: an anatomically clearer cartoon human spine standing upright "
    "in the center, drawn with confident, slightly thinner and more precise "
    "outlines (like a science textbook figure with cartoon warmth). "
    "The intervertebral discs (cushions between vertebrae) are gently "
    "anthropomorphized — round friendly characters with simple oval eyes "
    "(NOT big sparkly anime eyes, more like calm dot-and-curve eyes), small "
    "modest smiles. They look puffed up and pleased after absorbing water "
    "overnight, with one small speech bubble saying 'やったー！'. "
    "Show small water droplet icons being absorbed INTO the discs with clear "
    "blue arrows. Add neat Japanese labels and pointer lines (more like a "
    "scientific diagram, less like handwritten doodles) pointing to: "
    "'椎間板（クッション）', '水分吸収！', '膨張！', '朝は背が高い！'. "
    "Include a small moon icon in one corner indicating nighttime absorption. "
    "Comic-panel layout with a thick red border frame around the whole "
    "illustration. Flat-color shading with subtle gradients, restrained sparkle "
    "decorations (use sparingly), soft pastel cream background. The overall "
    "feel: educational science explainer that is still cute and approachable "
    "but leans slightly toward textbook clarity rather than full kawaii. "
    "Wide horizontal landscape composition (16:9), all text and labels in "
    "clear Japanese."
)

print(f"Calling DALL-E 3 (size=1792x1024, style=vivid)...")
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
    with urllib.request.urlopen(req, timeout=120) as resp:
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
