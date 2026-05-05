"""Regenerate the YouTube thumbnail for the wrinkly fingers video.

Pipeline:
  1) GPT-4o brainstorms a viral-style thumbnail design from the title.
  2) DALL-E 3 renders the background image (1280x720).
  3) Pillow overlays the Japanese catch copy on top.
"""
import os
import sys
import json
import base64
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"

TITLE = "【ゆっくり解説】お風呂で指がシワシワになるのはなぜ？水を吸ってるんじゃない衝撃の真実"

DESKTOP_OUT = Path(
    "/Users/ayukiyamazaki/Desktop/動画出力用/お風呂で指がシワシワになる本当の理由/wrinkly_fingers_サムネイル.png"
)
ICLOUD_OUT = Path(
    "/Users/ayukiyamazaki/Library/Mobile Documents/com~apple~CloudDocs/macmini iphone共有用/動画出力/お風呂で指がシワシワになる本当の理由/wrinkly_fingers_サムネイル.png"
)

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
]


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def call_openai(url: str, payload: dict, api_key: str, timeout: int = 180) -> dict:
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


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def step1_design_brief(api_key: str) -> dict:
    """Have GPT-4o produce a structured thumbnail design brief."""
    print("[1/3] GPT-4o にデザイン案を生成させます...")
    system = (
        "あなたはYouTubeで何百万再生も叩き出すサムネイルを設計する一流のアートディレクターです。"
        "ゆっくり解説系の科学チャンネル向けに、思わずクリックしたくなるサムネイル案をJSONで返します。"
    )
    user = (
        f"動画タイトル: 「{TITLE}」\n\n"
        "このタイトルでバズる、クリックしたくなるようなサムネイルにしてください。\n"
        "YouTubeで伸びている科学系・ゆっくり解説チャンネルのサムネイルスタイルを参考にして、"
        "以下のテイストを必ず取り入れてください:\n"
        "- 大きな文字でインパクトのあるキャッチコピー（画面の半分近くを占めるくらい大きく）\n"
        "- 驚き・疑問を煽る表情や「!?」マーク、矢印、丸囲みなどの煽り要素\n"
        "- 赤・黄色・白を中心とした目立つ色使い（背景は青系で文字色とコントラストを出す）\n"
        "- 左右分割（ビフォーアフター的な構図／『普通の指』vs『シワシワ指』、『水を吸う？』vs『神経の仕業！』など）\n"
        "- 人気科学系チャンネル（『ゆっくり科学』『放課後ゆっくり化学部』『カラパイア』『サイエンスドリーム』等）"
        "でよく使われる派手なレイアウトを真似する\n\n"
        "以下のJSON形式で1案だけ提案してください（コードブロックは不要、純粋なJSONのみ）:\n"
        "{\n"
        '  "catch_copy_main": "メイン大文字テキスト（10〜14文字、強烈・煽り。!?マーク必須）",\n'
        '  "catch_copy_sub": "サブテキスト（短く、答えを匂わせる）",\n'
        '  "highlight_word": "メインの中で特に赤や黄で強調したい1単語（4〜7文字）",\n'
        '  "background_concept": "DALL-E 3 に渡す英語のサムネ背景プロンプト。左右分割のビフォーアフター構図を必ず含める。'
        "左側に『普通の/乾いた手の指のアップ』、右側に『水に浸かってシワシワになった指のアップ』、両者を中央で縦に分割。"
        "ドラマチックなライティング、青系の水しぶきや泡の背景、被写体は鮮やかでハイコントラスト。"
        "右側の指の周りには赤い丸囲みや矢印で『シワ』を強調するような視覚効果。"
        "文字は一切描かせない『absolutely no text, no letters, no numbers』を必ず明記。"
        '1280x720 16:9を想定。",\n'
        '  "color_palette": "色使いの説明（例: 赤×黄×白×水色）",\n'
        '  "impact_elements": ["!?マーク", "赤丸囲み", "矢印", "ビフォーアフター分割線" など具体要素を列挙]\n'
        "}\n"
        "重要なポイント:\n"
        "- 「シワシワ指」と「水を吸ってるんじゃない」というギャップで驚きを煽る\n"
        "- メインコピーには必ず !? や ？ などの記号を含めてクリック欲を刺激\n"
        "- DALL-E 3は文字を綺麗に描けないので、背景プロンプトでは『no text, no letters』を必ず指定"
    )

    resp = call_openai(
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
    print("--- GPT-4o デザイン案 ---")
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return brief


def step2_generate_background(api_key: str, brief: dict, raw_path: Path) -> None:
    """Generate the DALL-E 3 background and save to raw_path (resized to 1280x720)."""
    print("[2/3] DALL-E 3 で背景画像を生成します (1792x1024 → 1280x720 にリサイズ)...")
    bg_concept = brief["background_concept"]
    prompt = (
        f"{bg_concept}\n"
        "Style: bold, eye-catching YouTube thumbnail aesthetic, high contrast, "
        "saturated colors, dramatic lighting, shallow depth of field, "
        "cinematic, photo-realistic close-up. "
        "STRICT: absolutely no text, no letters, no numbers, no Japanese characters, "
        "no captions, no logos anywhere in the image. "
        "Composition: wide 16:9 horizontal, leave the right ~40% visually simpler "
        "(soft gradient or out-of-focus background) so big Japanese title text can be overlaid later. "
        "Subject sits on the left side."
    )
    resp = call_openai(
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
    raw_path.write_bytes(base64.b64decode(img_b64))
    img = Image.open(raw_path).convert("RGB")
    img = img.resize((1280, 720), Image.LANCZOS)
    img.save(raw_path, "PNG")
    revised = resp["data"][0].get("revised_prompt", "")
    print(f"  saved background: {raw_path}")
    print(f"  revised_prompt: {revised[:200]}...")


def fit_text_to_width(draw, text, max_width, start_size, min_size=40):
    size = start_size
    while size >= min_size:
        font = get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            return font
        size -= 4
    return get_font(min_size)


def draw_text_with_outline(draw, xy, text, font, fill, outline, outline_w=6):
    x, y = xy
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def step3_compose_text(brief: dict, raw_path: Path, out_path: Path) -> None:
    """Overlay Japanese catch copy on the DALL-E background using Pillow.

    Layout: ビフォーアフター背景の上に
      - 上部: メインキャッチコピー（中央2行、強調語は赤背景の黄色文字）
      - 下部右: サブキャッチコピー
      - 左下: 「衝撃の真実」バッジ
    """
    print("[3/3] Pillow で日本語キャッチコピーを合成します...")
    main_text = brief["catch_copy_main"]
    sub_text = brief.get("catch_copy_sub", "")
    highlight = brief.get("highlight_word", "")

    img = Image.open(raw_path).convert("RGBA")
    W, H = img.size

    # 上部に黒の半透明グラデーション帯（テキスト視認性UP）
    top_band_h = int(H * 0.55)
    top_band = Image.new("RGBA", (W, top_band_h), (0, 0, 0, 0))
    tbd = ImageDraw.Draw(top_band)
    for y in range(top_band_h):
        a = int(180 * (1 - y / top_band_h) ** 1.4)
        tbd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img.alpha_composite(top_band, (0, 0))

    # 下部にも軽く暗い帯
    bot_h = int(H * 0.25)
    bot_band = Image.new("RGBA", (W, bot_h), (0, 0, 0, 0))
    bbd = ImageDraw.Draw(bot_band)
    for y in range(bot_h):
        a = int(140 * (y / bot_h) ** 1.4)
        bbd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img.alpha_composite(bot_band, (0, H - bot_h))

    draw = ImageDraw.Draw(img)
    text_area_w = W - 80  # 左右40pxマージン

    # 強調語で2行に分割（前半 / 強調語+残り）
    if highlight and highlight in main_text:
        idx = main_text.find(highlight)
        line1 = main_text[:idx].strip()
        line2 = main_text[idx:].strip()
        if not line1:
            # highlight が先頭にある場合は、残りの長さで再判断
            mid = len(main_text) // 2
            line1, line2 = main_text[:mid].strip(), main_text[mid:].strip()
        lines = [(line1, "white"), (line2, "highlight_inline", highlight)]
    else:
        if len(main_text) >= 9:
            mid = len(main_text) // 2
            for i in range(mid - 2, mid + 3):
                if 0 < i < len(main_text) and main_text[i] in "、。！？!?・":
                    mid = i + 1
                    break
            lines = [(main_text[:mid].strip(), "white"), (main_text[mid:].strip(), "white")]
        else:
            lines = [(main_text, "white")]

    # 行ごとにフォントを決定
    rendered = []
    for entry in lines:
        if len(entry) == 2:
            text, kind = entry
            extra = None
        else:
            text, kind, extra = entry[0], entry[1], entry[2]
        font = fit_text_to_width(draw, text, text_area_w, start_size=140, min_size=70)
        bbox = draw.textbbox((0, 0), text, font=font)
        rendered.append((text, kind, font, bbox[2] - bbox[0], bbox[3] - bbox[1], extra))

    line_gap = 14
    y = 30
    # トップに寄せる
    for text, kind, font, w, h, extra in rendered:
        x = (W - w) // 2
        if kind == "highlight_inline" and extra:
            highlight_word = extra
            # highlight_word が text に含まれていれば、その部分だけ色変え
            if highlight_word in text:
                hi_idx = text.find(highlight_word)
                before = text[:hi_idx]
                hi = highlight_word
                after = text[hi_idx + len(hi):]
                # 各セグメントの幅を計測しながら描画
                cx = x
                for seg, seg_color, seg_outline, seg_ow in [
                    (before, (255, 255, 255, 255), (0, 0, 0, 255), 7),
                    (hi, (255, 235, 60, 255), (200, 0, 0, 255), 9),
                    (after, (255, 255, 255, 255), (0, 0, 0, 255), 7),
                ]:
                    if not seg:
                        continue
                    draw_text_with_outline(draw, (cx, y), seg, font, seg_color, seg_outline, seg_ow)
                    seg_w = draw.textbbox((0, 0), seg, font=font)[2]
                    cx += seg_w
            else:
                draw_text_with_outline(draw, (x, y), text, font, (255, 235, 60, 255), (200, 0, 0, 255), 9)
        elif kind == "highlight":
            draw_text_with_outline(draw, (x, y), text, font, (255, 235, 60, 255), (200, 0, 0, 255), 9)
        else:
            draw_text_with_outline(draw, (x, y), text, font, (255, 255, 255, 255), (0, 0, 0, 255), 7)
        y += h + line_gap

    # サブテキストを下部右に
    if sub_text:
        sub_font = fit_text_to_width(draw, sub_text, int(W * 0.65), start_size=64, min_size=42)
        sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
        sw, sh = sub_bbox[2] - sub_bbox[0], sub_bbox[3] - sub_bbox[1]
        sx = (W - sw) // 2
        sy = H - sh - 50
        draw_text_with_outline(
            draw, (sx, sy), sub_text, sub_font,
            (255, 240, 100, 255), (60, 0, 0, 255), 6,
        )

    # 左下に「衝撃の真実」バッジ
    badge_text = "衝撃の真実"
    badge_font = get_font(54)
    bw = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw_w, bw_h = bw[2] - bw[0], bw[3] - bw[1]
    pad_x, pad_y = 26, 18
    badge_w, badge_h = bw_w + pad_x * 2, bw_h + pad_y * 2
    bx, by = 24, H - badge_h - 24
    badge_layer = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(badge_layer)
    bdraw.rounded_rectangle(
        [(0, 0), (badge_w - 1, badge_h - 1)],
        radius=18,
        fill=(220, 30, 30, 240),
        outline=(255, 255, 255, 255),
        width=5,
    )
    bdraw.text((pad_x, pad_y - 8), badge_text, font=badge_font, fill=(255, 255, 255, 255))
    img.alpha_composite(badge_layer, (bx, by))

    img.convert("RGB").save(out_path, "PNG", optimize=True)
    print(f"  saved thumbnail: {out_path}")


def main():
    load_env()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY missing", file=sys.stderr)
        sys.exit(1)

    brief = step1_design_brief(api_key)

    raw_path = ROOT / "sample_wrinkly_fingers_thumb_bg.png"
    step2_generate_background(api_key, brief, raw_path)

    DESKTOP_OUT.parent.mkdir(parents=True, exist_ok=True)
    step3_compose_text(brief, raw_path, DESKTOP_OUT)

    ICLOUD_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DESKTOP_OUT, ICLOUD_OUT)
    print(f"  copied to iCloud: {ICLOUD_OUT}")
    print("DONE")


if __name__ == "__main__":
    main()
