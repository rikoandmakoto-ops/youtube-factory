#!/usr/bin/env python3
"""
ゆっくり動画生成パイプライン (VOICEVOX対応)
フル動画 + ショート動画 + サムネイル + 説明文を一括生成

Usage:
    python3 -m backend.pipeline.video_generator --scenario earworm
    python3 -m backend.pipeline.video_generator --scenario canon
"""

import os, sys, json, random, tempfile, math, subprocess, argparse, time, shutil
import urllib.request, urllib.parse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import base64, io

try:
    from moviepy import VideoClip, VideoFileClip, AudioFileClip, concatenate_videoclips
except ImportError:
    from moviepy.editor import VideoClip, VideoFileClip, AudioFileClip, concatenate_videoclips

import numpy as np

# ============================================================
# Auto-detect paths
# ============================================================
SCRIPT_DIR = Path(__file__).parent
APP_DIR = SCRIPT_DIR.parent.parent  # auto-yukkuri-source/
# Assets: look in app/assets first, then sibling folder
ASSETS_DIR = APP_DIR / "assets"
if not ASSETS_DIR.exists():
    ASSETS_DIR = APP_DIR.parent / "assets"
    if not ASSETS_DIR.exists():
        ASSETS_DIR = Path.home() / "Desktop" / "BAT用" / "yukkuri_engine"

# Output: ~/Desktop/動画出力用/
OUTPUT_BASE = Path.home() / "Desktop" / "動画出力用"

# iCloud sync destination. Set to None (or env ICLOUD_SYNC=0) to disable.
ICLOUD_BASE = (
    Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    / "macmini iphone共有用" / "動画出力"
)


def get_output_dir(theme_name):
    """Create and return output dir: 動画出力用/<theme_name>/"""
    out = OUTPUT_BASE / theme_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def copy_to_icloud(out_dir, theme_name):
    """Copy generated mp4/png/txt under out_dir into ICLOUD_BASE/<theme_name>/.

    Returns the destination Path on success, or None when skipped/disabled.
    """
    if os.environ.get("ICLOUD_SYNC", "1") == "0":
        return None
    if ICLOUD_BASE is None:
        return None
    src_dir = Path(out_dir)
    if not src_dir.is_dir():
        print(f"⚠️ iCloud同期スキップ: 出力フォルダが見つかりません {src_dir}")
        return None
    try:
        dest_dir = ICLOUD_BASE / theme_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in src_dir.iterdir():
            if not src.is_file():
                continue
            if src.suffix.lower() not in (".mp4", ".png", ".txt"):
                continue
            shutil.copy2(str(src), str(dest_dir / src.name))
            copied += 1
        print(f"☁️  iCloud同期完了: {dest_dir} ({copied}ファイル)")
        return dest_dir
    except Exception as e:
        print(f"⚠️ iCloud同期失敗: {e}")
        return None

# ============================================================
# Config
# ============================================================
WIDTH, HEIGHT = 1920, 1080
SHORT_W, SHORT_H = 1080, 1920
FPS = 24
VOICEVOX_URL = "http://localhost:50021"

CHAR_CANVAS_W_RATIO = 0.418
TEXT_BOX_HEIGHT_RATIO = 0.20

# Font detection (macOS → Linux fallback)
_FONT_SEARCH_JP = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]
_FONT_SEARCH_EN = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

JP_FONT_PATH = next((f for f in _FONT_SEARCH_JP if os.path.exists(f)), None)
EN_FONT_PATH = next((f for f in _FONT_SEARCH_EN if os.path.exists(f)), None)

CHAR_CONFIG = {
    "理子": {
        "side": "left", "speaker_id": 2,
        "text_color": (255, 255, 0),
        "expressions": ["normal", "laugh", "sad", "surprise", "think"],
    },
    "真": {
        "side": "right", "speaker_id": 3,
        "text_color": (100, 230, 255),
        "expressions": ["normal", "laugh", "surprise", "happy", "sad"],
    },
}

# ============================================================
# Font helpers
# ============================================================
def get_font(size):
    if JP_FONT_PATH:
        return ImageFont.truetype(JP_FONT_PATH, size)
    return ImageFont.load_default()

def get_en_font(size):
    if EN_FONT_PATH:
        return ImageFont.truetype(EN_FONT_PATH, size)
    return get_font(size)

def draw_composite_text(draw, pos, text, size, fill, stroke_fill=None, stroke_width=0):
    jp_font = get_font(size)
    en_font = get_en_font(size)
    x, y = pos
    for ch in text:
        font = en_font if ord(ch) < 256 else jp_font
        bbox = draw.textbbox((0, 0), ch, font=font)
        char_w = bbox[2] - bbox[0] + 1
        if stroke_fill and stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx * dx + dy * dy <= stroke_width * stroke_width:
                        draw.text((x + dx, y + dy), ch, font=font, fill=stroke_fill)
        draw.text((x, y), ch, font=font, fill=fill)
        x += char_w
    return x - pos[0]

def measure_composite_text(draw, text, size):
    jp_font = get_font(size)
    en_font = get_en_font(size)
    total_w = 0
    for ch in text:
        font = en_font if ord(ch) < 256 else jp_font
        bbox = draw.textbbox((0, 0), ch, font=font)
        total_w += bbox[2] - bbox[0] + 1
    return total_w

_BREAK_PREFERRED = "。！？!?」』）)】"
_BREAK_SECONDARY = "、,・ "


def _wrap_segment(text, size, max_width, draw):
    """Wrap a single segment (no \\n inside) by width, preferring sentence boundaries."""
    lines, current = [], ""
    last_break = -1  # index in `current` just AFTER a preferred break char
    for ch in text:
        test = current + ch
        if measure_composite_text(draw, test, size) > max_width and current:
            # Prefer breaking after sentence-end punctuation if it's not too far back
            if last_break > 0 and last_break >= len(current) // 2:
                lines.append(current[:last_break])
                current = current[last_break:] + ch
                # Recompute last_break for the carried-over fragment
                last_break = -1
                for i, c in enumerate(current[:-1], start=1):
                    if c in _BREAK_PREFERRED:
                        last_break = i
            else:
                lines.append(current)
                current = ch
                last_break = -1
        else:
            current = test
            if ch in _BREAK_PREFERRED:
                last_break = len(current)
    if current:
        lines.append(current)
    return lines


def wrap_text(text, size, max_width, draw):
    """Wrap text into lines that fit max_width.

    - Treats explicit \\n in `text` as hard line breaks.
    - When wrapping by width, prefers breaking after Japanese sentence-ending
      punctuation (。！？」 etc.) so subtitles split at natural boundaries.
    """
    if not text:
        return []
    result = []
    for segment in text.split("\n"):
        if segment == "":
            continue
        result.extend(_wrap_segment(segment, size, max_width, draw))
    return result if result else [""]

# ============================================================
# TTS
# ============================================================
def check_voicevox():
    try:
        urllib.request.urlopen(f"{VOICEVOX_URL}/speakers", timeout=2)
        return True
    except:
        return False

VOICEVOX_SPEED = 1.3  # デフォルト話速倍率


# 名前のかな読み修正（VOICEVOXは「理子」を「さとこ」、「真/誠」を「シン/マコト」と
# 揺らいで読むので、TTSに渡す前に確定読みへ置換する）
# 真/誠 は熟語（真実・誠実・真夜中・真ん中・真っ赤 など）に巻き込まれないよう、
# 直後が漢字/っ/ん の場合は置換しない。理子 は2文字熟語が事実上ないので無条件置換。
_TTS_NAME_KANJI_NEXT_SKIP = "っんッン"


def _tts_force_name_readings(text):
    if not text:
        return text
    text = text.replace("理子", "りこ")
    out = []
    for i, ch in enumerate(text):
        if ch in ("真", "誠"):
            nxt = text[i + 1] if i + 1 < len(text) else ""
            is_kanji = "一" <= nxt <= "鿿"
            if is_kanji or nxt in _TTS_NAME_KANJI_NEXT_SKIP:
                out.append(ch)
            else:
                out.append("まこと")
        else:
            out.append(ch)
    return "".join(out)


def _tts_normalize(text):
    """Strip subtitle-only line breaks and force correct name readings before TTS."""
    if not text:
        return text
    out = []
    for i, ch in enumerate(text):
        if ch == "\n":
            prev = out[-1] if out else ""
            if prev and prev not in "。！？、,.!?":
                out.append("、")
        else:
            out.append(ch)
    return _tts_force_name_readings("".join(out))


def synthesize_voicevox(text, speaker_id, wav_path, speed=None):
    text = _tts_normalize(text)
    query_url = f"{VOICEVOX_URL}/audio_query?text={urllib.parse.quote(text)}&speaker={speaker_id}"
    req = urllib.request.Request(query_url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        query = json.loads(resp.read())
    # 話速設定
    query["speedScale"] = speed if speed is not None else VOICEVOX_SPEED
    synth_url = f"{VOICEVOX_URL}/synthesis?speaker={speaker_id}"
    req2 = urllib.request.Request(synth_url, data=json.dumps(query).encode(), method="POST",
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req2, timeout=60) as resp2:
        with open(wav_path, "wb") as f:
            f.write(resp2.read())

def synthesize_mock(text, speaker_id, wav_path):
    text = _tts_normalize(text)
    try:
        voice = "Kyoko" if speaker_id == 2 else "Otoya"
        tmp_aiff = wav_path.replace(".wav", ".aiff")
        subprocess.run(["say", "-v", voice, "-o", tmp_aiff, text],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(["ffmpeg", "-y", "-i", tmp_aiff, "-ar", "24000", "-ac", "1", wav_path],
                       check=True, capture_output=True, timeout=30)
        os.remove(tmp_aiff)
    except Exception:
        duration = max(1.0, len(text) * 0.15)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", str(duration), wav_path],
                       check=True, capture_output=True, timeout=30)

def synthesize(text, speaker_id, wav_path, use_voicevox, speed=None):
    if use_voicevox:
        synthesize_voicevox(text, speaker_id, wav_path, speed=speed)
    else:
        synthesize_mock(text, speaker_id, wav_path)

def get_audio_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except:
        return 2.0


# ============================================================
# BGM mixing
# ============================================================
_BGM_AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".ogg")
VALID_MOODS = ("calm", "bright", "tense", "emotional", "funny", "mysterious")
_DEFAULT_MOOD = "calm"
_BGM_CROSSFADE_DEFAULT = 1.5  # seconds


def _normalize_mood(mood):
    """Coerce arbitrary input into one of VALID_MOODS, defaulting to calm."""
    if not mood:
        return _DEFAULT_MOOD
    m = str(mood).strip().lower()
    return m if m in VALID_MOODS else _DEFAULT_MOOD


def _list_audio_files(directory: Path):
    """Return sorted list of audio files in `directory` (non-recursive)."""
    if not directory.exists() or not directory.is_dir():
        return []
    files = []
    for ext in _BGM_AUDIO_EXTS:
        files.extend(directory.glob(f"*{ext}"))
    return sorted(files)


def _load_bgm_mapping(channel_id):
    """Load `bgm_mapping.json` from `data/channels_assets/<channel_id>/bgm/` if present.

    Format: {"calm": ["path/a.mp3", "path/b.mp3"], "tense": [...], ...}
    Paths can be absolute or relative to APP_DIR or to the bgm/ folder itself.
    Returns dict[str, list[Path]] (only existing files), or {} if not found.
    """
    if not channel_id:
        return {}
    bgm_dir = APP_DIR / "data" / "channels_assets" / channel_id / "bgm"
    mapping_path = bgm_dir / "bgm_mapping.json"
    if not mapping_path.exists():
        return {}
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"⚠️ bgm_mapping.json 読み込み失敗: {e}")
        return {}
    out = {}
    for mood, paths in (raw or {}).items():
        if not isinstance(paths, list):
            continue
        resolved = []
        for p in paths:
            cand = Path(p)
            for base in (cand, bgm_dir / p, APP_DIR / p):
                if base.exists() and base.is_file():
                    resolved.append(base)
                    break
        if resolved:
            out[mood.lower()] = resolved
    return out


def _resolve_bgm_for_mood(mood, channel_id, mapping_cache=None):
    """Find a BGM file matching `mood` for the given channel.

    Lookup order:
      1. `bgm_mapping.json` mood → random pick from list
      2. `data/channels_assets/<channel>/bgm/<mood>/*` → random pick
      3. `<ASSETS_DIR>/bgm/<mood>/*` → random pick
      4. Fallback to `_resolve_bgm_file(None, channel_id)` (legacy single file)
    Returns a Path or None.
    """
    mood = _normalize_mood(mood)

    # 1. bgm_mapping.json
    mapping = mapping_cache if mapping_cache is not None else _load_bgm_mapping(channel_id)
    if mood in mapping and mapping[mood]:
        return random.choice(mapping[mood])

    # 2. Per-channel mood folder
    if channel_id:
        ch_mood_dir = APP_DIR / "data" / "channels_assets" / channel_id / "bgm" / mood
        files = _list_audio_files(ch_mood_dir)
        if files:
            return random.choice(files)

    # 3. Global mood folder
    global_mood_dir = ASSETS_DIR / "bgm" / mood
    files = _list_audio_files(global_mood_dir)
    if files:
        return random.choice(files)

    # 4. Legacy fallback (single channel-level file)
    return _resolve_bgm_file(None, channel_id)


def _resolve_bgm_file(bgm_path, channel_id):
    """Resolve a BGM source path (legacy single-file lookup).

    Order:
      1. Explicit `bgm_path` from channel config — absolute, or relative to APP_DIR.
      2. Auto-discover the first audio file in
         `<APP_DIR>/data/channels_assets/<channel_id>/bgm/`.
      3. Auto-discover the first audio file in `<ASSETS_DIR>/bgm/`.

    Returns a `Path` if found, otherwise `None` (caller should silently skip).
    """
    if bgm_path:
        p = Path(bgm_path)
        if not p.is_absolute():
            p = APP_DIR / bgm_path
        if p.exists() and p.is_file():
            return p
        return None

    if channel_id:
        ch_dir = APP_DIR / "data" / "channels_assets" / channel_id / "bgm"
        files = _list_audio_files(ch_dir)
        if files:
            return files[0]

    fallback_dir = ASSETS_DIR / "bgm"
    files = _list_audio_files(fallback_dir)
    if files:
        return files[0]

    return None


def _group_mood_scenes(mood_timeline):
    """Merge consecutive same-mood entries into scenes.

    Args:
        mood_timeline: list of (start, end, mood) per line.
    Returns:
        list of (scene_start, scene_end, mood).
    """
    scenes = []
    for start, end, mood in mood_timeline:
        if end <= start:
            continue
        m = _normalize_mood(mood)
        if scenes and scenes[-1][2] == m and abs(scenes[-1][1] - start) < 1e-3:
            scenes[-1] = (scenes[-1][0], end, m)
        else:
            scenes.append((start, end, m))
    return scenes


def _build_bgm_track_per_scene(scenes, total_duration, channel_id, bgm_volume,
                               crossfade=_BGM_CROSSFADE_DEFAULT):
    """Build a list of AudioClip segments (with set start time, fades, volume)
    that together form a per-scene BGM track. Returns (segments, info_lines).

    Segments overlap by `crossfade` seconds at scene boundaries.
    """
    try:
        from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
    except ImportError:
        AudioFadeIn = AudioFadeOut = None
    try:
        from moviepy.audio.AudioClip import concatenate_audioclips
    except ImportError:
        from moviepy.editor import concatenate_audioclips

    mapping_cache = _load_bgm_mapping(channel_id)
    segments = []
    info = []
    n = len(scenes)
    last_file_per_mood = {}  # cache resolved file per scene mood for logging

    for i, (start, end, mood) in enumerate(scenes):
        bgm_file = _resolve_bgm_for_mood(mood, channel_id, mapping_cache=mapping_cache)
        if bgm_file is None:
            info.append(f"  scene {i+1} [{mood}] {start:.1f}-{end:.1f}s: BGM未設定 → 無音")
            continue

        # Extend each segment by crossfade/2 on each interior side so they overlap with neighbors.
        seg_start = max(0.0, start - crossfade / 2.0) if i > 0 else 0.0
        seg_end = min(total_duration, end + crossfade / 2.0) if i < n - 1 else total_duration
        seg_dur = seg_end - seg_start
        if seg_dur <= 0:
            continue

        try:
            base = AudioFileClip(str(bgm_file))
            src_dur = float(base.duration or 0)
            if src_dur <= 0:
                base.close()
                continue

            if src_dur < seg_dur:
                n_loops = int(seg_dur // src_dur) + 1
                base.close()
                base = concatenate_audioclips(
                    [AudioFileClip(str(bgm_file)) for _ in range(n_loops)]
                )

            try:
                clip = base.subclipped(0, seg_dur)
            except AttributeError:
                clip = base.subclip(0, seg_dur)

            try:
                clip = clip.with_volume_scaled(bgm_volume)
            except AttributeError:
                clip = clip.volumex(bgm_volume)

            effects = []
            if i > 0 and AudioFadeIn is not None:
                effects.append(AudioFadeIn(crossfade))
            if i < n - 1 and AudioFadeOut is not None:
                effects.append(AudioFadeOut(crossfade))
            if effects and hasattr(clip, "with_effects"):
                clip = clip.with_effects(effects)
            elif AudioFadeIn is None:
                # v1 fallback
                if i > 0 and hasattr(clip, "audio_fadein"):
                    clip = clip.audio_fadein(crossfade)
                if i < n - 1 and hasattr(clip, "audio_fadeout"):
                    clip = clip.audio_fadeout(crossfade)

            try:
                clip = clip.with_start(seg_start)
            except AttributeError:
                clip = clip.set_start(seg_start)

            segments.append(clip)
            last_file_per_mood[mood] = bgm_file.name
            info.append(f"  scene {i+1} [{mood}] {start:.1f}-{end:.1f}s → {bgm_file.name}")
        except Exception as e:
            info.append(f"  scene {i+1} [{mood}] 失敗: {e}")
            continue

    return segments, info


def _mix_bgm(final_clip, channel_format, channel_id=None, bgm_volume=None,
             mood_timeline=None):
    """Layer BGM under the existing narration audio of `final_clip`.

    Reads `bgm_path` and (when `bgm_volume` is not given) `bgm_volume` from
    `channel_format["audio"]`. The explicit `bgm_volume` argument (0..1, set
    by the /generate form's slider or its preview) takes precedence over the
    channel's stored value.

    Two modes:
      - Per-scene mix: when `mood_timeline` is provided AND no explicit
        `bgm_path` override is set. Groups consecutive same-mood lines into
        scenes and switches BGM at boundaries with a crossfade.
      - Single-track mix: legacy behavior. Loops one BGM over the whole clip.

    Falls back to single-track if per-scene fails or yields no segments, and
    returns the clip unchanged when the resolved volume is <= 0 or no BGM
    asset is found. Never raises.
    """
    audio_cfg = (channel_format or {}).get("audio") or {}
    if bgm_volume is None:
        if not channel_format:
            return final_clip
        try:
            bgm_volume = float(audio_cfg.get("bgm_volume", 0.30) or 0)
        except (TypeError, ValueError):
            bgm_volume = 0.0
    else:
        try:
            bgm_volume = float(bgm_volume)
        except (TypeError, ValueError):
            bgm_volume = 0.0
    if bgm_volume <= 0:
        return final_clip

    try:
        from moviepy import CompositeAudioClip
    except ImportError:
        from moviepy.editor import CompositeAudioClip
    try:
        from moviepy.audio.AudioClip import concatenate_audioclips
    except ImportError:
        from moviepy.editor import concatenate_audioclips

    target_duration = float(final_clip.duration or 0)
    if target_duration <= 0:
        return final_clip

    explicit_bgm_path = audio_cfg.get("bgm_path")
    per_scene_enabled = audio_cfg.get("bgm_per_scene", True)

    # ── Per-scene mix branch ──
    if (per_scene_enabled and mood_timeline and not explicit_bgm_path
            and any(_normalize_mood(m) for _, _, m in mood_timeline)):
        try:
            scenes = _group_mood_scenes(mood_timeline)
            if scenes:
                try:
                    crossfade = float(audio_cfg.get("bgm_crossfade", _BGM_CROSSFADE_DEFAULT) or 0)
                except (TypeError, ValueError):
                    crossfade = _BGM_CROSSFADE_DEFAULT
                crossfade = max(0.0, min(crossfade, 4.0))

                segments, info = _build_bgm_track_per_scene(
                    scenes, target_duration, channel_id, bgm_volume,
                    crossfade=crossfade,
                )
                if segments:
                    narration = final_clip.audio
                    audio_layers = ([narration] if narration is not None else []) + segments
                    new_audio = CompositeAudioClip(audio_layers)
                    try:
                        mixed = final_clip.with_audio(new_audio)
                    except AttributeError:
                        mixed = final_clip.set_audio(new_audio)
                    print(f"🎵 BGM per-scene mix: {len(scenes)}シーン, "
                          f"crossfade={crossfade:.1f}s, volume={bgm_volume:.2f}")
                    for line in info:
                        print(line)
                    return mixed
                else:
                    print("🎵 BGM per-scene: 全シーンの音源未発見 → シングル曲モードへフォールバック")
        except Exception as e:
            print(f"⚠️ BGM per-scene mix失敗 → シングル曲モードへフォールバック: {e}")

    # ── Legacy single-track branch ──
    bgm_file = _resolve_bgm_file(explicit_bgm_path, channel_id)
    if bgm_file is None:
        print("🎵 BGM: 音源が見つからないためスキップ "
              "(data/channels_assets/<channel>/bgm/ にアップロード可)")
        return final_clip

    try:
        bgm = AudioFileClip(str(bgm_file))
        src_dur = float(bgm.duration or 0)
        if src_dur <= 0:
            bgm.close()
            return final_clip

        if src_dur < target_duration:
            n_loops = int(target_duration // src_dur) + 1
            bgm.close()
            bgm = concatenate_audioclips(
                [AudioFileClip(str(bgm_file)) for _ in range(n_loops)]
            )

        try:
            bgm = bgm.subclipped(0, target_duration)
        except AttributeError:
            bgm = bgm.subclip(0, target_duration)

        try:
            bgm = bgm.with_volume_scaled(bgm_volume)
        except AttributeError:
            bgm = bgm.volumex(bgm_volume)

        narration = final_clip.audio
        new_audio = bgm if narration is None else CompositeAudioClip([narration, bgm])

        try:
            mixed = final_clip.with_audio(new_audio)
        except AttributeError:
            mixed = final_clip.set_audio(new_audio)

        print(f"🎵 BGM mix: {bgm_file.name} (volume={bgm_volume:.2f}, "
              f"duration={target_duration:.1f}s)")
        return mixed
    except Exception as e:
        print(f"⚠️ BGMミックス失敗（スキップして続行）: {e}")
        return final_clip


# ============================================================
# Illustration Generator (GPT DALL-E / OpenAI API)
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

def _call_openai_image(prompt, size="1024x1024", quality="medium", channel_id=None):
    """Call OpenAI gpt-image-1 API to generate an illustration."""
    if not OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY not set — skipping illustration generation")
        return None
    url = "https://api.openai.com/v1/images/generations"
    payload = json.dumps({
        "model": "gpt-image-1",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
    })
    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
                                 headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {OPENAI_API_KEY}",
                                 })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        b64 = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64)
        try:
            from pipeline import api_usage
            api_usage.record_image_usage(
                size=size, quality=quality,
                channel_id=channel_id, purpose="illustration",
            )
        except Exception:
            pass
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    except Exception as e:
        print(f"⚠️ Image API error: {e}")
        return None


# gpt-image-1 size mapping (channel illustration_style.format → API size string)
_ILLUST_FORMAT_SIZE = {
    "landscape": "1536x1024",
    "square":    "1024x1024",
    "portrait":  "1024x1536",
}

# Composition phrase per format (steers DALL-E to fill the canvas correctly)
_ILLUST_FORMAT_COMPOSITION = {
    "landscape": "Wide horizontal landscape composition (16:9)",
    "square":    "Centered square composition (1:1)",
    "portrait":  "Tall vertical portrait composition (9:16)",
}


def _build_illustration_prompt(topic_text, char_config=None, illust_style=None, channel_id=None):
    """Compose a DALL-E prompt for a channel-styled educational illustration.

    The MAIN subject of the image is a visual diagram/illustration that
    explains the content of the current dialogue line (`topic_text`).
    The channel's signature characters, when included, appear as TINY chibi
    figures tucked into the corners — they are decorative cameos, not the
    focus of the image.

    illust_style (dict) — channel-specific style overrides:
      art_style, background, include_characters, extra_prompt.

    channel_id — when provided, pull competitor-derived illustration hints from
    competitor_intelligence.build_illustration_competitor_hint() and append a
    short tone-only line to the prompt. Educational diagrams remain the focus;
    competitor input only nudges visual sensibility.
    """
    style = illust_style or {}
    art_style = style.get(
        "art_style",
        "colorful hand-drawn cartoon illustration in the style of popular Japanese "
        "educational YouTube explainer videos. Bright pop colors, thick clean outlines, "
        "playful flat-color shading with light gradients, friendly anime/manga aesthetic"
    )
    background = style.get(
        "background",
        "soft pastel background with subtle decorative shapes"
    )
    include_chars = style.get("include_characters", True)
    fmt = style.get("format", "landscape")
    composition = _ILLUST_FORMAT_COMPOSITION.get(fmt, _ILLUST_FORMAT_COMPOSITION["landscape"])
    extra = style.get("extra_prompt", "") or ""

    char_block = ""
    if include_chars and char_config:
        lines = []
        for name, cfg in char_config.items():
            appearance = cfg.get("appearance")
            if not appearance:
                continue
            side = cfg.get("side")
            if side == "left":
                corner = "in the bottom-left corner"
            elif side == "right":
                corner = "in the bottom-right corner"
            else:
                corner = "in a corner"
            lines.append(f"- {name} {corner}: {appearance}")
        if lines:
            char_block = (
                "Tuck the channel's mascot characters into the corners as TINY chibi "
                "cameos — each character should occupy at most ~12% of the canvas "
                "height, sit fully inside its corner, peek/point toward the central "
                "diagram, and never overlap or obscure the main illustration. They "
                "are small decorative observers, NOT the subject:\n"
                + "\n".join(lines)
                + "\n"
            )

    safe_topic = (topic_text or "").strip()[:300]
    allow_labels = bool(style.get("allow_text_labels", False))
    allow_frame = bool(style.get("allow_frame", False))

    if allow_frame:
        strict_block = (
            "STRICT: exactly ONE diagram/concept/focal subject. NO multi-panel, "
            "NO side-by-side, NO before/after, NO grids, NO collages. "
            "Describable in one short sentence."
        )
    else:
        strict_block = (
            "STRICT: exactly ONE diagram/concept/focal subject. NO multi-panel, "
            "NO frames, NO side-by-side, NO before/after, NO grids, NO collages. "
            "Describable in one short sentence."
        )

    if allow_labels:
        text_block = (
            "Short Japanese labels with pointer lines, simple arrows, and small "
            "icons are ALLOWED — keep them clean and minimal, like a textbook "
            "diagram. NO long sentences, NO paragraphs, NO logos, NO watermarks."
        )
    else:
        text_block = (
            "NO text, letters, numbers, captions, speech bubbles, logos, or "
            "watermarks of any kind. Pictures and symbols only."
        )

    competitor_hint = ""
    if channel_id:
        try:
            from pipeline.analytics.competitor_intelligence import (
                build_illustration_competitor_hint,
            )
            competitor_hint = build_illustration_competitor_hint(channel_id) or ""
        except Exception as e:
            print(f"  ⚠️ illustration competitor hint failed: {e}")

    parts = [
        f"{art_style}. Background: {background}. {composition}.",
        (
            "MAIN SUBJECT (center ~75% of canvas): ONE educational illustration "
            "that visually explains the SINGLE most central idea from this "
            "Japanese narration line. Use a clear literal visual metaphor "
            "(one object, anatomy view, cross-section, cause→effect arrow, "
            "or close-up). Draw the THING being discussed, not characters talking."
        ),
        strict_block,
        f"Narration: 「{safe_topic}」.",
        char_block,
        text_block,
        competitor_hint,
    ]
    if extra:
        parts.append(extra)
    return " ".join(p for p in parts if p)


def generate_illustration(topic_text, cache_dir=None, idx=0, char_config=None,
                          channel_id=None, illust_style=None):
    """
    Generate a channel-styled educational illustration for a given topic.

    illust_style (dict, optional) — overrides DALL-E style/size/prompt per channel.
    Returns PIL Image or None.
    """
    # Check cache first
    if cache_dir:
        cache_path = Path(cache_dir) / f"illust_{idx:03d}.png"
        if cache_path.exists():
            return Image.open(str(cache_path)).convert("RGBA")

    style = illust_style or {}
    fmt = style.get("format", "landscape")
    size = _ILLUST_FORMAT_SIZE.get(fmt, "1536x1024")
    quality = style.get("quality", "medium")
    if quality not in ("low", "medium", "high", "auto"):
        quality = "medium"

    prompt = _build_illustration_prompt(
        topic_text, char_config=char_config, illust_style=style, channel_id=channel_id
    )
    img = _call_openai_image(prompt, size=size, quality=quality, channel_id=channel_id)
    if img and cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        cache_path = Path(cache_dir) / f"illust_{idx:03d}.png"
        img.save(str(cache_path))
        print(f"  💾 Illustration cached: {cache_path}")
    return img


def plan_illustrations(scenario, interval_seconds=30, speed=1.3):
    """
    Plan illustration insertion points for yukkuri dialogue scenario.
    Returns list of (entry_index, topic_text) tuples — one entry per
    ~interval_seconds of estimated playback time.

    `topic_text` is the concatenation of all dialogue lines that will be
    spoken WHILE the illustration is on screen, so DALL-E can draw an
    explanatory diagram that matches what is actually being said during
    that window (not just the single line where the illustration first
    appears).

    Estimates per-line duration from character count (Japanese ゆっくり TTS is
    roughly 6 chars/sec at speed=1.0). The first illustration is planned for
    line 0 so the video opens with an image on screen.
    """
    chars_per_sec = 6.0 * max(speed, 0.5)

    line_durs = []
    for entry in scenario:
        text = entry.get("text", "")
        line_durs.append(max(len(text) / chars_per_sec, 1.0) + 0.3)

    insertion_indices = []
    cumulative_time = 0.0
    next_illust_time = 0.0
    for i, dur in enumerate(line_durs):
        if cumulative_time >= next_illust_time:
            insertion_indices.append(i)
            next_illust_time += interval_seconds
        cumulative_time += dur

    plans = []
    for k, start_idx in enumerate(insertion_indices):
        end_idx = insertion_indices[k + 1] if k + 1 < len(insertion_indices) else len(scenario)
        window_lines = [
            (scenario[j].get("text") or "").strip()
            for j in range(start_idx, end_idx)
            if (scenario[j].get("text") or "").strip()
        ]
        topic_text = " ".join(window_lines)
        plans.append((start_idx, topic_text))

    return plans


# ============================================================
# Frame Renderer (Full video - landscape)
# ============================================================
class FrameRenderer:
    def __init__(self, bg_video_path=None, bg_type="auto", fmt=None, char_config=None):
        """
        bg_type: "video" = 動的（動画背景）, "static" = 静的（画像or単色）, "auto" = ファイルがあれば動画
        fmt: VideoFormat layout/colors config dict (or None for defaults)
        char_config: チャンネル別キャラクター設定 (None = グローバルCHAR_CONFIG)
        """
        self.bg_video = None
        self.bg_video_duration = 0
        self.bg_image = None
        self.bg_type = bg_type
        # チャンネル別フォーマット設定
        self.fmt = fmt or {}
        self.char_cfg = char_config or CHAR_CONFIG
        # レイアウト値（fmtから取得、なければグローバルデフォルト）
        layout = self.fmt.get("layout", {})
        self.W = layout.get("width", WIDTH)
        self.H = layout.get("height", HEIGHT)
        self.char_canvas_w_ratio = layout.get("char_canvas_w_ratio", CHAR_CANVAS_W_RATIO)
        self.text_box_h_ratio = layout.get("text_box_height_ratio", TEXT_BOX_HEIGHT_RATIO)
        self.char_y_offset = layout.get("char_y_offset", 130)
        self.char_x_inset = layout.get("char_x_inset_ratio", 0.15)
        self.speaker_glow = layout.get("speaker_glow", True)
        self.nonspeaker_opacity = layout.get("nonspeaker_opacity", 0.5)
        self.text_font_size = layout.get("text_font_size", 42)
        self.text_stroke_width = layout.get("text_stroke_width", 3)
        self.text_line_spacing = layout.get("text_line_spacing", 4)
        self.text_margin_x = layout.get("text_margin_x", 60)
        self.text_box_opacity = layout.get("text_box_opacity", 180)
        self.illust_size = layout.get("illustration_size", 360)
        self.illust_card_padding = layout.get("illustration_card_padding", 10)
        self.illust_card_opacity = layout.get("illustration_card_opacity", 200)
        self.illust_y = layout.get("illustration_y", 40)
        # イラスト枠スタイル（チャンネル別）
        illust_style_cfg = self.fmt.get("illustration_style", {}) or {}
        self.frame_style = illust_style_cfg.get("frame_style", "wooden")
        self.illust_format = illust_style_cfg.get("format", "landscape")
        # カラー設定
        colors = self.fmt.get("colors", {})
        self.bg_color = tuple(colors.get("bg_color", [15, 25, 50, 255]))
        self.text_box_color = tuple(colors.get("text_box_color", [0, 0, 0]))
        self.text_stroke_color = tuple(colors.get("text_stroke_color", [0, 0, 0]))

        if bg_video_path and Path(bg_video_path).exists():
            ext = Path(bg_video_path).suffix.lower()
            if bg_type == "static" or ext in (".png", ".jpg", ".jpeg", ".bmp"):
                if ext in (".png", ".jpg", ".jpeg", ".bmp"):
                    self.bg_image = Image.open(str(bg_video_path)).convert("RGBA").resize((self.W, self.H))
                    print(f"🖼️ Static image background loaded")
                else:
                    vid = VideoFileClip(str(bg_video_path))
                    self.bg_image = Image.fromarray(vid.get_frame(0)).convert("RGBA").resize((self.W, self.H))
                    vid.close()
                    print(f"🖼️ Static background (first frame of video)")
            elif bg_type in ("video", "auto"):
                self.bg_video = VideoFileClip(str(bg_video_path))
                self.bg_video_duration = self.bg_video.duration
                print(f"🌊 Video background loaded: {self.bg_video_duration:.1f}s")

        # Load sprites — use channel char_config
        self.sprites = {}
        # キャラ名→ディレクトリ名の対応（チャンネル側で cfg["dir"]/["slug"] 指定可）
        _CHAR_DIR_MAP = {"理子": "riko", "真": "makoto", "あかり": "akari", "ゆうた": "yuuta",
                         "シロ": "shiro", "クロ": "kuro"}
        for name, cfg in self.char_cfg.items():
            self.sprites[name] = {}
            dir_name = (
                cfg.get("dir")
                or cfg.get("slug")
                or _CHAR_DIR_MAP.get(name)
                or name.lower()
            )
            char_dir = ASSETS_DIR / "characters" / dir_name
            if not char_dir.exists():
                char_dir = ASSETS_DIR / dir_name
            expressions = cfg.get("expressions", ["normal"])
            for expr in expressions:
                p = char_dir / f"{expr}.png"
                if p.exists():
                    self.sprites[name][expr] = Image.open(str(p)).convert("RGBA")

    def close(self):
        if self.bg_video:
            self.bg_video.close()

    def _get_bg_frame(self, t):
        W, H = self.W, self.H
        if self.bg_video:
            loop_t = t % self.bg_video_duration
            return Image.fromarray(self.bg_video.get_frame(loop_t)).convert("RGBA").resize((W, H))
        if self.bg_image:
            return self.bg_image.copy()
        return Image.new("RGBA", (W, H), self.bg_color)

    def _render_illust_frame(self, illust, isz_w, isz_h, W, H, usable_h):
        """Render the illustration onto a frame layer based on channel frame_style.

        frame_style: "wooden" (brown), "blackboard" (dark green-black),
                     "whiteboard" (white), "none" (no frame).
        """
        style = (self.frame_style or "wooden").lower()

        if style == "none":
            border = 0
            frame_w, frame_h = isz_w, isz_h
            frame = None
            inner_shadow = None
        elif style == "blackboard":
            border = 16
            frame_w = isz_w + border * 2
            frame_h = isz_h + border * 2
            frame = Image.new("RGBA", (frame_w, frame_h), (28, 38, 30, 255))
            inner_shadow = Image.new("RGBA", (isz_w + 4, isz_h + 4), (0, 0, 0, 150))
        elif style == "whiteboard":
            border = 12
            frame_w = isz_w + border * 2
            frame_h = isz_h + border * 2
            frame = Image.new("RGBA", (frame_w, frame_h), (245, 245, 245, 255))
            inner_shadow = Image.new("RGBA", (isz_w + 4, isz_h + 4), (180, 180, 180, 180))
        else:  # "wooden" (default)
            border = 14
            frame_w = isz_w + border * 2
            frame_h = isz_h + border * 2
            frame = Image.new("RGBA", (frame_w, frame_h), (110, 75, 40, 255))
            inner_shadow = Image.new("RGBA", (isz_w + 4, isz_h + 4), (0, 0, 0, 120))

        card_x = (W - frame_w) // 2
        card_y = (usable_h - frame_h) // 2
        card_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if frame is not None:
            card_layer.paste(frame, (card_x, card_y), frame)
        if inner_shadow is not None:
            card_layer.paste(inner_shadow, (card_x + border - 2, card_y + border - 2), inner_shadow)
        card_layer.paste(illust, (card_x + border, card_y + border), illust)
        return card_layer

    def _build_overlay(self, speaker, text, expression="normal", diagram=False, diagram_text=None, illustration=None):
        W, H = self.W, self.H
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        text_box_h = int(H * self.text_box_h_ratio)
        canvas_w = int(W * self.char_canvas_w_ratio)

        # Subtitle bar
        bar = Image.new("RGBA", (W, text_box_h), (*self.text_box_color, self.text_box_opacity))
        overlay.paste(bar, (0, H - text_box_h), bar)

        # Illustration panel — frame style is channel-configurable.
        if illustration:
            usable_h = H - text_box_h
            # Target box depends on illustration aspect (landscape fills wide; portrait/square narrower).
            iw, ih = illustration.size
            aspect = iw / max(ih, 1)
            if aspect >= 1.4:        # landscape
                target_w = int(W * 0.78) + 120
                target_h = int(usable_h * 0.72) + 80
            elif aspect <= 0.8:      # portrait
                target_w = int(W * 0.42) + 120
                target_h = int(usable_h * 0.85) + 80
            else:                     # square-ish
                target_w = int(W * 0.55) + 120
                target_h = int(usable_h * 0.78) + 80
            scale = min(target_w / iw, target_h / ih)
            isz_w = int(iw * scale)
            isz_h = int(ih * scale)
            illust = illustration.resize((isz_w, isz_h), Image.LANCZOS)

            card_layer = self._render_illust_frame(illust, isz_w, isz_h, W, H, usable_h)
            overlay = Image.alpha_composite(overlay, card_layer)

        # Characters — always show both, highlight the speaker
        for char_name, cfg in self.char_cfg.items():
            is_speaking = (char_name == speaker)
            expr = expression if is_speaking else "normal"
            sprite = self.sprites.get(char_name, {}).get(expr)
            if sprite is None:
                sprite = self.sprites.get(char_name, {}).get("normal")
            if sprite:
                scale = canvas_w / sprite.width
                new_w, new_h = canvas_w, int(sprite.height * scale)
                resized = sprite.resize((new_w, new_h), Image.LANCZOS)
                y = H - text_box_h - new_h + self.char_y_offset
                if cfg["side"] == "left":
                    x = -int(new_w * self.char_x_inset)
                else:
                    x = W - new_w + int(new_w * self.char_x_inset)

                if not is_speaking:
                    # Dim the non-speaking character
                    dimmed = resized.copy()
                    r, g, b, a = dimmed.split()
                    opacity = self.nonspeaker_opacity
                    a = a.point(lambda p: int(p * opacity))
                    dimmed = Image.merge("RGBA", (r, g, b, a))
                    overlay.paste(dimmed, (x, y), dimmed)
                else:
                    if self.speaker_glow:
                        # Glow effect under the speaking character
                        glow = Image.new("RGBA", (new_w + 40, new_h + 40), (0, 0, 0, 0))
                        glow_draw = ImageDraw.Draw(glow)
                        glow_color = cfg.get("text_color", (255, 255, 255))
                        glow_draw.ellipse(
                            [new_w // 4, new_h - 80, new_w * 3 // 4, new_h + 20],
                            fill=(*glow_color[:3], 30)
                        )
                        glow = glow.filter(ImageFilter.GaussianBlur(radius=20))
                        overlay.paste(glow, (x - 20, y - 20), glow)
                    overlay.paste(resized, (x, y), resized)

        # Subtitle text (centered for single line)
        if text:
            text_color = self.char_cfg.get(speaker, {}).get("text_color", (255, 255, 255))
            draw = ImageDraw.Draw(overlay)
            fsize = self.text_font_size
            max_text_w = W - self.text_margin_x * 2
            wrapped = wrap_text(text, fsize, max_text_w, draw)
            line_h = int(fsize * 1.15)
            total_h = len(wrapped) * line_h + (len(wrapped) - 1) * self.text_line_spacing
            y_start = H - text_box_h + (text_box_h - total_h) // 2
            for line in wrapped:
                tw = measure_composite_text(draw, line, fsize)
                tx = (W - tw) // 2
                draw_composite_text(draw, (tx, y_start), line, fsize, text_color,
                                    stroke_fill=self.text_stroke_color, stroke_width=self.text_stroke_width)
                y_start += line_h + self.text_line_spacing

        return overlay

    def make_video_clip(self, speaker, text, duration, time_offset, expression="normal", diagram=False, diagram_text=None, illustration=None):
        overlay = self._build_overlay(speaker, text, expression, diagram, diagram_text, illustration=illustration)
        if self.bg_video is None:
            bg = self._get_bg_frame(0)
            frame = np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
            return VideoClip(lambda t: frame, duration=duration)

        def make_frame(t):
            bg = self._get_bg_frame(time_offset + t)
            return np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
        return VideoClip(make_frame, duration=duration)


# ============================================================
# Short Frame Renderer (vertical, 2ch-style)
# ============================================================
class ShortFrameRenderer:
    def __init__(self, bg_video_path=None, bg_type="auto", char_config=None):
        self.bg_video = None
        self.bg_video_duration = 0
        self.bg_image = None
        self.bg_type = bg_type
        self.char_cfg = char_config or CHAR_CONFIG

        if bg_video_path and Path(bg_video_path).exists():
            ext = Path(bg_video_path).suffix.lower()
            if bg_type == "static" or ext in (".png", ".jpg", ".jpeg", ".bmp"):
                if ext in (".png", ".jpg", ".jpeg", ".bmp"):
                    img = Image.open(str(bg_video_path)).convert("RGBA")
                else:
                    vid = VideoFileClip(str(bg_video_path))
                    img = Image.fromarray(vid.get_frame(0)).convert("RGBA")
                    vid.close()
                # Crop to 9:16 and resize
                w, h = img.size
                target_w = int(h * 9 / 16)
                if target_w > w:
                    target_h = int(w * 16 / 9)
                    y_off = (h - target_h) // 2
                    img = img.crop((0, max(0, y_off), w, y_off + target_h))
                else:
                    x_off = (w - target_w) // 2
                    img = img.crop((max(0, x_off), 0, x_off + target_w, h))
                self.bg_image = img.resize((SHORT_W, SHORT_H))
                print(f"🖼️ Static short background loaded")
            elif bg_type in ("video", "auto"):
                self.bg_video = VideoFileClip(str(bg_video_path))
                self.bg_video_duration = self.bg_video.duration

        self.sprites = {}
        _SHORT_CHAR_DIR_MAP = {"理子": "riko", "真": "makoto", "あかり": "akari", "ゆうた": "yuuta",
                               "シロ": "shiro", "クロ": "kuro"}
        for name, cfg in self.char_cfg.items():
            self.sprites[name] = {}
            dir_name = (
                cfg.get("dir")
                or cfg.get("slug")
                or _SHORT_CHAR_DIR_MAP.get(name)
                or name.lower()
            )
            char_dir = ASSETS_DIR / "characters" / dir_name
            if not char_dir.exists():
                char_dir = ASSETS_DIR / dir_name
            for expr in cfg.get("expressions", ["normal"]):
                p = char_dir / f"{expr}.png"
                if p.exists():
                    self.sprites[name][expr] = Image.open(str(p)).convert("RGBA")

    def close(self):
        if self.bg_video:
            self.bg_video.close()

    def _get_bg_frame(self, t):
        if self.bg_video:
            loop_t = t % self.bg_video_duration
            frame_arr = self.bg_video.get_frame(loop_t)
            h, w = frame_arr.shape[:2]
            target_w = int(h * 9 / 16)
            if target_w > w:
                target_h = int(w * 16 / 9)
                y_off = (h - target_h) // 2
                cropped = frame_arr[max(0, y_off):y_off + target_h, :, :]
            else:
                x_off = (w - target_w) // 2
                cropped = frame_arr[:, max(0, x_off):x_off + target_w, :]
            return Image.fromarray(cropped).convert("RGBA").resize((SHORT_W, SHORT_H))
        if self.bg_image:
            return self.bg_image.copy()
        return Image.new("RGBA", (SHORT_W, SHORT_H), (15, 25, 50, 255))

    def _build_overlay(self, speaker, text, expression="normal"):
        overlay = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        cfg = self.char_cfg.get(speaker)
        if not cfg:
            return overlay

        # Single speaking character — circular icon (shorts = 1人ずつ表示)
        sprite = self.sprites.get(speaker, {}).get(expression)
        if sprite is None:
            sprite = self.sprites.get(speaker, {}).get("normal")
        icon_d = 280
        cx, cy = SHORT_W // 2, 580
        if sprite:
            crop_s = min(sprite.width, sprite.height)
            left = (sprite.width - crop_s) // 2
            cropped = sprite.crop((left, 0, left + crop_s, crop_s)).resize((icon_d, icon_d), Image.LANCZOS)
            mask = Image.new("L", (icon_d, icon_d), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, icon_d, icon_d], fill=255)
            # Ring color: use the character's text_color when defined (per-channel),
            # falling back to the historical riko-vs-other red/blue split.
            tcol = cfg.get("text_color")
            if tcol:
                ring_c = tuple(int(c) for c in tcol[:3])
            else:
                ring_c = (230, 50, 50) if cfg.get("side") == "left" else (50, 120, 230)
            rw = 6
            ring = Image.new("RGBA", (icon_d + rw*2, icon_d + rw*2), (0,0,0,0))
            rd = ImageDraw.Draw(ring)
            rd.ellipse([0, 0, icon_d+rw*2, icon_d+rw*2], fill=ring_c)
            rd.ellipse([rw, rw, icon_d+rw, icon_d+rw], fill=(0,0,0,0))
            overlay.paste(ring, (cx-icon_d//2-rw, cy-icon_d//2-rw), ring)
            ci = Image.new("RGBA", (icon_d, icon_d), (0,0,0,0))
            ci.paste(cropped, (0,0), mask)
            overlay.paste(ci, (cx-icon_d//2, cy-icon_d//2), ci)

        draw = ImageDraw.Draw(overlay)
        nw = measure_composite_text(draw, speaker, 36)
        draw_composite_text(draw, ((SHORT_W-nw)//2, cy-icon_d//2-50), speaker, 36,
                            (255,255,255), stroke_fill=(0,0,0), stroke_width=4)

        if text:
            tc = cfg.get("text_color", (255,255,255))
            wrapped = wrap_text(text, 64, SHORT_W-80, draw)
            y_start = cy + icon_d//2 + 40
            for line in wrapped:
                tw = measure_composite_text(draw, line, 64)
                draw_composite_text(draw, ((SHORT_W-tw)//2, y_start), line, 64, tc,
                                    stroke_fill=(0,0,0), stroke_width=5)
                y_start += 86

        return overlay

    def make_video_clip(self, speaker, text, duration, time_offset, expression="normal"):
        overlay = self._build_overlay(speaker, text, expression)
        if self.bg_video is None:
            bg = self._get_bg_frame(0)
            frame = np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
            return VideoClip(lambda t: frame, duration=duration)

        def make_frame(t):
            bg = self._get_bg_frame(time_offset + t)
            return np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
        return VideoClip(make_frame, duration=duration)


# ============================================================
# Expression picker
# ============================================================
def pick_expression(text, expressions):
    """喜怒哀楽＋驚き＋思考で表情差分を使い分け"""
    # 驚き: ！？、えっ、マジ、うそ、ほんと、すごい
    surprise_words = ["！？", "えっ", "マジ", "うそ", "ほんと", "すごい", "やばい", "信じられ", "まさか"]
    # 喜び: 嬉しい、楽しい、やった、いいね、最高、素敵
    happy_words = ["嬉しい", "楽しい", "やった", "いいね", "最高", "素敵", "面白い", "へぇ", "なるほど", "いい"]
    # 笑い: 笑、ウケる、あはは、ふふ
    laugh_words = ["笑", "ウケる", "あはは", "ふふ", "ww", "草", "おもしろ"]
    # 悲しみ: 悲しい、辛い、残念、かわいそう、つらい
    sad_words = ["悲しい", "辛い", "残念", "かわいそう", "つらい", "切ない", "泣", "しょんぼり"]
    # 怒り: 怒、ひどい、許せない、ふざけ、むかつく
    angry_words = ["怒", "ひどい", "許せない", "ふざけ", "むかつく", "イライラ", "腹立"]
    # 思考: ？、なぜ、どうして、なんで、考え、つまり
    think_words = ["なぜ", "どうして", "なんで", "考え", "つまり", "理由", "仕組み", "原因"]

    def has_any(words):
        return any(w in text for w in words)

    # 驚き（！？の組み合わせや驚きワード）
    if has_any(surprise_words) or ("！" in text and "？" in text):
        if "surprise" in expressions: return "surprise"
    # 純粋な感嘆（！だけ、驚きワードなし）
    if text.count("！") >= 2 or (text.endswith("！") and has_any(happy_words)):
        if "happy" in expressions: return "happy"
        if "laugh" in expressions: return "laugh"
    # 笑い
    if has_any(laugh_words):
        if "laugh" in expressions: return "laugh"
    # 喜び
    if has_any(happy_words):
        if "happy" in expressions: return "happy"
        if "laugh" in expressions: return "laugh"
    # 悲しみ
    if has_any(sad_words):
        if "sad" in expressions: return "sad"
    # 怒り（sad差分で代用、anger差分があればそっち）
    if has_any(angry_words):
        if "angry" in expressions: return "angry"
        if "sad" in expressions: return "sad"
    # 思考・疑問
    if "？" in text or has_any(think_words):
        if "think" in expressions: return "think"
    # 感嘆符のみ
    if "！" in text:
        if "surprise" in expressions: return "surprise"
        if "happy" in expressions: return "happy"
    # デフォルト: normal
    return "normal"


# ============================================================
# Monologue Frame Renderer (考えすぎる葦 style — キャラなし、テキスト中心)
# ============================================================
MONO_SPEAKER_ID = 13  # VOICEVOX: 青山龍星 (落ち着いた男性ナレーション)
MONO_TEXT_COLOR = (240, 240, 240)
MONO_ACCENT_COLOR = (120, 180, 255)  # Chapter見出し色

class MonologueFrameRenderer:
    """1人語り考察スタイル用レンダラー。キャラ立ち絵なし、テキスト＋チャプター表示。"""

    def __init__(self, bg_video_path=None, bg_type="auto"):
        self.bg_video = None
        self.bg_video_duration = 0
        self.bg_image = None
        self.bg_type = bg_type

        if bg_video_path and Path(bg_video_path).exists():
            ext = Path(bg_video_path).suffix.lower()
            if bg_type == "static" or ext in (".png", ".jpg", ".jpeg", ".bmp"):
                if ext in (".png", ".jpg", ".jpeg", ".bmp"):
                    self.bg_image = Image.open(str(bg_video_path)).convert("RGBA").resize((WIDTH, HEIGHT))
                else:
                    vid = VideoFileClip(str(bg_video_path))
                    self.bg_image = Image.fromarray(vid.get_frame(0)).convert("RGBA").resize((WIDTH, HEIGHT))
                    vid.close()
            elif bg_type in ("video", "auto"):
                self.bg_video = VideoFileClip(str(bg_video_path))
                self.bg_video_duration = self.bg_video.duration

    def close(self):
        if self.bg_video:
            self.bg_video.close()

    def _get_bg_frame(self, t):
        if self.bg_video:
            loop_t = t % self.bg_video_duration
            return Image.fromarray(self.bg_video.get_frame(loop_t)).convert("RGBA").resize((WIDTH, HEIGHT))
        if self.bg_image:
            return self.bg_image.copy()
        # Dark cinematic background for monologue style
        return Image.new("RGBA", (WIDTH, HEIGHT), (8, 8, 15, 255))

    def _build_overlay(self, text, chapter=None, is_chapter_title=False):
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if is_chapter_title:
            # Chapter title screen — centered large text with accent color
            # Dark overlay
            dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 140))
            overlay = Image.alpha_composite(overlay, dark)
            draw = ImageDraw.Draw(overlay)

            # Chapter number / name
            lines = text.split("\n") if "\n" in text else [text]
            total_h = len(lines) * 70
            y_start = (HEIGHT - total_h) // 2
            for line in lines:
                tw = measure_composite_text(draw, line, 54)
                tx = (WIDTH - tw) // 2
                draw_composite_text(draw, (tx, y_start), line, 54, MONO_ACCENT_COLOR,
                                    stroke_fill=(0, 0, 0), stroke_width=4)
                y_start += 70
            return overlay

        # Regular narration — subtitle bar at bottom + optional chapter indicator top-left
        text_box_h = int(HEIGHT * 0.22)
        # Gradient subtitle bar (bottom)
        bar = Image.new("RGBA", (WIDTH, text_box_h + 40), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar)
        for y in range(text_box_h + 40):
            alpha = int(200 * (y / (text_box_h + 40)))
            bar_draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))
        overlay.paste(bar, (0, HEIGHT - text_box_h - 40), bar)

        # Chapter indicator (top-left, subtle)
        if chapter:
            ch_text = f"— {chapter}"
            draw_composite_text(draw, (40, 40), ch_text, 24, (180, 180, 180, 200),
                                stroke_fill=(0, 0, 0), stroke_width=2)
            # Thin accent line under chapter
            draw.line([(40, 75), (40 + measure_composite_text(draw, ch_text, 24), 75)],
                      fill=(*MONO_ACCENT_COLOR, 120), width=2)

        # Main text (large, centered, white with soft shadow)
        if text:
            max_text_w = WIDTH - 160
            wrapped = wrap_text(text, 42, max_text_w, draw)
            line_h = 52
            total_h = len(wrapped) * line_h
            y_start = HEIGHT - text_box_h - 20 + (text_box_h - total_h) // 2
            for line in wrapped:
                tw = measure_composite_text(draw, line, 42)
                tx = (WIDTH - tw) // 2
                # Soft shadow
                draw_composite_text(draw, (tx + 2, y_start + 2), line, 42, (0, 0, 0),
                                    stroke_fill=None, stroke_width=0)
                draw_composite_text(draw, (tx, y_start), line, 42, MONO_TEXT_COLOR,
                                    stroke_fill=(0, 0, 0), stroke_width=3)
                y_start += line_h

        return overlay

    def make_video_clip(self, text, duration, time_offset, chapter=None, is_chapter_title=False):
        overlay = self._build_overlay(text, chapter, is_chapter_title)
        if self.bg_video is None:
            bg = self._get_bg_frame(0)
            frame = np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
            return VideoClip(lambda t: frame, duration=duration)

        def make_frame(t):
            bg = self._get_bg_frame(time_offset + t)
            return np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
        return VideoClip(make_frame, duration=duration)


class MonologueShortRenderer:
    """1人語りスタイルのショート用レンダラー（9:16縦型）。"""

    def __init__(self, bg_video_path=None, bg_type="auto"):
        self.bg_video = None
        self.bg_video_duration = 0
        self.bg_image = None

        if bg_video_path and Path(bg_video_path).exists():
            ext = Path(bg_video_path).suffix.lower()
            if bg_type == "static" or ext in (".png", ".jpg", ".jpeg", ".bmp"):
                if ext in (".png", ".jpg", ".jpeg", ".bmp"):
                    img = Image.open(str(bg_video_path)).convert("RGBA")
                else:
                    vid = VideoFileClip(str(bg_video_path))
                    img = Image.fromarray(vid.get_frame(0)).convert("RGBA")
                    vid.close()
                w, h = img.size
                target_w = int(h * 9 / 16)
                if target_w > w:
                    target_h = int(w * 16 / 9)
                    y_off = (h - target_h) // 2
                    img = img.crop((0, max(0, y_off), w, y_off + target_h))
                else:
                    x_off = (w - target_w) // 2
                    img = img.crop((max(0, x_off), 0, x_off + target_w, h))
                self.bg_image = img.resize((SHORT_W, SHORT_H))
            elif bg_type in ("video", "auto"):
                self.bg_video = VideoFileClip(str(bg_video_path))
                self.bg_video_duration = self.bg_video.duration

    def close(self):
        if self.bg_video:
            self.bg_video.close()

    def _get_bg_frame(self, t):
        if self.bg_video:
            loop_t = t % self.bg_video_duration
            frame_arr = self.bg_video.get_frame(loop_t)
            h, w = frame_arr.shape[:2]
            target_w = int(h * 9 / 16)
            if target_w > w:
                target_h = int(w * 16 / 9)
                y_off = (h - target_h) // 2
                cropped = frame_arr[max(0, y_off):y_off + target_h, :, :]
            else:
                x_off = (w - target_w) // 2
                cropped = frame_arr[:, max(0, x_off):x_off + target_w, :]
            return Image.fromarray(cropped).convert("RGBA").resize((SHORT_W, SHORT_H))
        if self.bg_image:
            return self.bg_image.copy()
        return Image.new("RGBA", (SHORT_W, SHORT_H), (8, 8, 15, 255))

    def _build_overlay(self, text):
        overlay = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Gradient bar at bottom
        text_box_h = int(SHORT_H * 0.25)
        bar = Image.new("RGBA", (SHORT_W, text_box_h + 40), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar)
        for y in range(text_box_h + 40):
            alpha = int(210 * (y / (text_box_h + 40)))
            bar_draw.line([(0, y), (SHORT_W, y)], fill=(0, 0, 0, alpha))
        overlay.paste(bar, (0, SHORT_H - text_box_h - 40), bar)

        if text:
            wrapped = wrap_text(text, 52, SHORT_W - 80, draw)
            y_start = SHORT_H - text_box_h + 20
            for line in wrapped:
                tw = measure_composite_text(draw, line, 52)
                draw_composite_text(draw, ((SHORT_W - tw) // 2, y_start), line, 52,
                                    MONO_TEXT_COLOR, stroke_fill=(0, 0, 0), stroke_width=4)
                y_start += 72

        return overlay

    def make_video_clip(self, text, duration, time_offset):
        overlay = self._build_overlay(text)
        if self.bg_video is None:
            bg = self._get_bg_frame(0)
            frame = np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
            return VideoClip(lambda t: frame, duration=duration)

        def make_frame(t):
            bg = self._get_bg_frame(time_offset + t)
            return np.array(Image.alpha_composite(bg, overlay).convert("RGB"))
        return VideoClip(make_frame, duration=duration)


# ============================================================
# Generate monologue video (1人語り考察スタイル)
# ============================================================
def generate_monologue_video(scenario, title, output_prefix, bg_video_path=None,
                              out_dir=None, bg_type="auto", speed=None, target_duration=None,
                              speaker_id=None, channel_format=None, channel_id=None,
                              bgm_volume=None):
    """
    1人語りスタイルのメイン動画生成。
    scenario format:
      [
        {"text": "ナレーション本文", "chapter": "Chapter 1 — タイトル"},  # chapter表示
        {"text": "本文"},  # 通常ナレーション
        {"chapter_title": "Chapter 2 — 次の章"},  # チャプタータイトル画面（読み上げなし）
      ]
    """
    print("=" * 60)
    print(f"モノローグ動画生成: {title}")
    print("=" * 60)

    use_vv = check_voicevox()
    sid = speaker_id or MONO_SPEAKER_ID
    if out_dir is None:
        out_dir = get_output_dir(title)
    out_dir = Path(out_dir)
    renderer = MonologueFrameRenderer(bg_video_path, bg_type=bg_type)
    tmp_dir = tempfile.mkdtemp(prefix="mono_")
    clips, t_off = [], 0.0
    audio_clips = []
    current_chapter = None
    current_mood = None
    mood_timeline = []

    for i, entry in enumerate(scenario):
        # A chapter_title or text entry may set a mood that sticks until the next change.
        if entry.get("mood"):
            current_mood = entry.get("mood")

        # Chapter title screen (no narration, just visual)
        if "chapter_title" in entry:
            current_chapter = entry["chapter_title"]
            ch_dur = entry.get("duration", 3.0)
            clip = renderer.make_video_clip(current_chapter, ch_dur, t_off, is_chapter_title=True)
            clips.append(clip)
            mood_timeline.append((t_off, t_off + ch_dur, current_mood))
            t_off += ch_dur
            print(f"  [{i+1}/{len(scenario)}] 📖 {current_chapter}")
            continue

        # Regular narration
        tx = entry["text"]
        if "chapter" in entry:
            current_chapter = entry["chapter"]

        print(f"  [{i+1}/{len(scenario)}] {tx[:40]}...")
        wav = os.path.join(tmp_dir, f"m_{i:03d}.wav")
        synthesize(tx, sid, wav, use_vv, speed=speed)
        dur = max(get_audio_duration(wav), 1.0) + 0.4  # Slightly longer pause for monologue pacing

        clip = renderer.make_video_clip(tx, dur, t_off, chapter=current_chapter)
        ac = AudioFileClip(wav)
        audio_clips.append(ac)
        clip = clip.with_audio(ac)
        clips.append(clip)
        mood_timeline.append((t_off, t_off + dur, current_mood))
        t_off += dur

    print(f"\n🎬 Concatenating... (total: {t_off:.1f}s = {t_off/60:.1f}min)")
    final = concatenate_videoclips(clips)
    final = _mix_bgm(final, channel_format, channel_id=channel_id, bgm_volume=bgm_volume, mood_timeline=mood_timeline)
    out = str(out_dir / f"{output_prefix}_メイン.mp4")
    temp_audio = os.path.join(tmp_dir, "temp_audio.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          threads=4, logger="bar", temp_audiofile=temp_audio)

    final.close()
    for c in clips: c.close()
    for ac in audio_clips: ac.close()
    renderer.close()
    print(f"✅ モノローグ動画: {out} ({os.path.getsize(out)/1024/1024:.1f}MB, {t_off/60:.1f}分)")
    return out


def generate_monologue_short(scenario, title, output_prefix, bg_video_path=None,
                               out_dir=None, bg_type="auto", speed=None, speaker_id=None,
                               channel_format=None, channel_id=None, bgm_volume=None):
    """1人語りスタイルのショート動画生成。"""
    print("=" * 60)
    print(f"���ノローグショート生成: {title}")
    print("=" * 60)

    use_vv = check_voicevox()
    sid = speaker_id or MONO_SPEAKER_ID
    if out_dir is None:
        out_dir = get_output_dir(title)
    out_dir = Path(out_dir)
    renderer = MonologueShortRenderer(bg_video_path, bg_type=bg_type)
    tmp_dir = tempfile.mkdtemp(prefix="monos_")
    clips, t_off = [], 0.0
    audio_clips = []
    mood_timeline = []

    for i, entry in enumerate(scenario):
        if "chapter_title" in entry:
            continue  # Skip chapter titles in shorts
        tx = entry["text"]
        wav = os.path.join(tmp_dir, f"ms_{i:03d}.wav")
        synthesize(tx, sid, wav, use_vv, speed=speed)
        dur = max(get_audio_duration(wav), 1.0) + 0.3

        clip = renderer.make_video_clip(tx, dur, t_off)
        ac = AudioFileClip(wav)
        audio_clips.append(ac)
        clip = clip.with_audio(ac)
        clips.append(clip)
        mood_timeline.append((t_off, t_off + dur, entry.get("mood")))
        t_off += dur

    final = concatenate_videoclips(clips)
    final = _mix_bgm(final, channel_format, channel_id=channel_id, bgm_volume=bgm_volume, mood_timeline=mood_timeline)
    out = str(out_dir / f"{output_prefix}_ショート.mp4")
    temp_audio = os.path.join(tmp_dir, "temp_audio.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          threads=4, logger="bar", temp_audiofile=temp_audio)

    final.close()
    for c in clips: c.close()
    for ac in audio_clips: ac.close()
    renderer.close()
    print(f"✅ モノ���ーグショート: {out}")
    return out


# ============================================================
# Generate full video (ゆっくり対話スタイル)
# ============================================================
def generate_full_video(scenario, title, output_prefix, bg_video_path=None, out_dir=None,
                        bg_type="auto", speed=None, target_duration=None, use_illustrations=True,
                        channel_format=None, char_config=None, channel_id=None,
                        bgm_volume=None):
    print("=" * 60)
    print(f"フル動画生成: {title}")
    print("=" * 60)

    use_vv = check_voicevox()
    print(f"{'✅ VOICEVOX' if use_vv else '⚠️ Mock TTS'}")

    if out_dir is None:
        out_dir = get_output_dir(title)
    out_dir = Path(out_dir)
    renderer = FrameRenderer(bg_video_path, bg_type=bg_type, fmt=channel_format, char_config=char_config)
    tmp_dir = tempfile.mkdtemp(prefix="full_")
    clips, t_off = [], 0.0

    # Pre-generate illustrations (every ~illustration_interval seconds).
    # Channel format may override the interval (default: 30s → ~24 images for a 12min video).
    layout_cfg = (channel_format or {}).get("layout", {})
    illust_interval = int(layout_cfg.get("illustration_interval", 30))
    illust_style = (channel_format or {}).get("illustration_style", {}) or {}
    plan_speed = speed if speed else 1.3
    illust_map = {}  # {entry_index: PIL.Image}
    if use_illustrations and OPENAI_API_KEY:
        illust_cache = str(Path(out_dir) / "illustrations")
        illust_plans = plan_illustrations(scenario, interval_seconds=illust_interval, speed=plan_speed)
        if illust_style:
            print(f"🎨 Generating {len(illust_plans)} illustrations "
                  f"(interval={illust_interval}s, quality={illust_style.get('quality','medium')}, "
                  f"format={illust_style.get('format','landscape')}, "
                  f"frame={illust_style.get('frame_style','wooden')})...")
        else:
            print(f"🎨 Generating {len(illust_plans)} illustrations (interval={illust_interval}s)...")
        for idx, (entry_idx, topic) in enumerate(illust_plans):
            img = generate_illustration(topic, cache_dir=illust_cache, idx=idx,
                                        char_config=char_config, illust_style=illust_style)
            if img:
                illust_map[entry_idx] = img
                print(f"  🖼️ [{idx+1}/{len(illust_plans)}] Illustration for line {entry_idx}")
            time.sleep(0.5)  # Rate limit buffer
    elif use_illustrations:
        print("⚠️ OPENAI_API_KEY not set — illustrations skipped")

    audio_clips = []
    current_illust = None  # sticky: keep showing the latest illustration until the next one
    mood_timeline = []  # list of (start, end, mood) per line for per-scene BGM
    active_chars = char_config or CHAR_CONFIG
    for i, entry in enumerate(scenario):
        sp, tx = entry["speaker"], entry["text"]
        cfg = active_chars.get(sp) or CHAR_CONFIG.get(sp) or next(iter(active_chars.values()))
        print(f"  [{i+1}/{len(scenario)}] {sp}: {tx[:35]}...")

        wav = os.path.join(tmp_dir, f"l_{i:03d}.wav")
        synthesize(tx, cfg["speaker_id"], wav, use_vv, speed=speed)
        dur = max(get_audio_duration(wav), 1.0) + 0.3
        expr = pick_expression(tx, cfg["expressions"])

        # Sticky illustration: switch when this entry has a new one, otherwise keep showing the previous.
        if i in illust_map:
            current_illust = illust_map[i]
        illust = current_illust

        clip = renderer.make_video_clip(sp, tx, dur, t_off, expr,
                                         entry.get("diagram", False), entry.get("diagram_text"),
                                         illustration=illust)
        ac = AudioFileClip(wav)
        audio_clips.append(ac)
        clip = clip.with_audio(ac)
        clips.append(clip)
        mood_timeline.append((t_off, t_off + dur, entry.get("mood")))
        t_off += dur

    print(f"\n🎬 Concatenating... (total: {t_off:.1f}s = {t_off/60:.1f}min)")
    if target_duration and t_off > 0:
        # target_duration is in SECONDS (e.g. 600 = 10min)
        target_s = target_duration
        print(f"🎯 Target: {target_duration}s ({target_s/60:.1f}min), actual: {t_off:.1f}s ({t_off/60:.1f}min)")
    final = concatenate_videoclips(clips)
    final = _mix_bgm(final, channel_format, channel_id=channel_id, bgm_volume=bgm_volume, mood_timeline=mood_timeline)
    out = str(out_dir / f"{output_prefix}_メイン.mp4")
    temp_audio = os.path.join(tmp_dir, "temp_audio.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          threads=4, logger="bar", temp_audiofile=temp_audio)

    final.close()
    for c in clips: c.close()
    for ac in audio_clips: ac.close()
    renderer.close()
    duration_min = os.path.getsize(out) and t_off / 60
    print(f"✅ メイン動画: {out} ({os.path.getsize(out)/1024/1024:.1f}MB, {duration_min:.1f}分)")
    return out


# ============================================================
# Generate short video
# ============================================================
def generate_short_video(short_scenario, title, output_prefix, bg_video_path=None, out_dir=None, bg_type="auto", speed=None,
                         channel_format=None, char_config=None, channel_id=None, bgm_volume=None):
    print("=" * 60)
    print(f"ショート動画生成: {title}")
    print("=" * 60)

    use_vv = check_voicevox()
    print(f"{'✅ VOICEVOX' if use_vv else '⚠️ Mock TTS'}")

    if out_dir is None:
        out_dir = get_output_dir(title)
    out_dir = Path(out_dir)
    renderer = ShortFrameRenderer(bg_video_path, bg_type=bg_type, char_config=char_config)
    active_chars = char_config or CHAR_CONFIG
    tmp_dir = tempfile.mkdtemp(prefix="short_")
    clips, audio_clips, t_off = [], [], 0.0
    mood_timeline = []

    for i, entry in enumerate(short_scenario):
        sp, tx = entry["speaker"], entry["text"]
        cfg = active_chars.get(sp) or CHAR_CONFIG.get(sp) or next(iter(active_chars.values()))
        print(f"  [{i+1}/{len(short_scenario)}] {sp}: {tx[:35]}...")

        wav = os.path.join(tmp_dir, f"s_{i:03d}.wav")
        synthesize(tx, cfg["speaker_id"], wav, use_vv, speed=speed)
        dur = max(get_audio_duration(wav), 1.0) + 0.2
        expr = pick_expression(tx, cfg["expressions"])

        clip = renderer.make_video_clip(sp, tx, dur, t_off, expr)
        ac = AudioFileClip(wav)
        audio_clips.append(ac)
        clip = clip.with_audio(ac)
        clips.append(clip)
        mood_timeline.append((t_off, t_off + dur, entry.get("mood")))
        t_off += dur

    print(f"\n🎬 Concatenating {len(clips)} clips ({t_off:.1f}s)...")
    final = concatenate_videoclips(clips)
    final = _mix_bgm(final, channel_format, channel_id=channel_id, bgm_volume=bgm_volume, mood_timeline=mood_timeline)
    out = str(out_dir / f"{output_prefix}_ショート.mp4")
    temp_audio = os.path.join(tmp_dir, "temp_audio.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          threads=4, logger="bar", temp_audiofile=temp_audio)

    final.close()
    for c in clips: c.close()
    for ac in audio_clips: ac.close()
    renderer.close()
    print(f"✅ ショート動画: {out} ({os.path.getsize(out)/1024/1024:.1f}MB, {t_off:.1f}s)")
    return out


# ============================================================
# Scenarios
# ============================================================
EARWORM_SHORT = [
    {"speaker": "真", "text": "98%！ほぼ全員じゃん！"},
    {"speaker": "理子", "text": "そう！研究者の調査で、なんと98%の人が勝手に頭の中で曲が再生される『イヤーワーム』を経験してるの"},
    {"speaker": "真", "text": "なんで脳はそんなことするの？"},
    {"speaker": "理子", "text": "好きな曲を聴くと、脳からドーパミンがドバッと出るの。特にサビが来た瞬間にね"},
    {"speaker": "真", "text": "だからサビを何度も聴きたくなるんだ！"},
    {"speaker": "理子", "text": "止めたい時は、その曲を最後まで聴くか、ガムを噛むと効果的よ"},
    {"speaker": "真", "text": "ガム！？そんな簡単な方法で！？"},
]

EARWORM_FULL = [
    {"speaker": "真", "text": "ねえリコ、最近ずっと同じ曲が頭の中でループしてるんだけど…"},
    {"speaker": "理子", "text": "あー、わかる。私も昨日からずっとサビが頭から離れないの"},
    {"speaker": "真", "text": "なんで人間って同じ曲を何十回も繰り返し聴いちゃうんだろう？飽きないのかな"},
    {"speaker": "理子", "text": "実はそれ、脳の仕組みがちゃんと関係してるの。今日は『イヤーワーム』の科学について解説するわ！"},
    {"speaker": "理子", "text": "まず『イヤーワーム』って聞いたことある？英語でearworm、直訳すると『耳の虫』ね"},
    {"speaker": "真", "text": "耳の虫！？なんか気持ち悪いな…"},
    {"speaker": "理子", "text": "学術的にはINMI、Involuntary Musical Imageryって呼ばれてるの。日本語だと『不随意な音楽的イメージ』"},
    {"speaker": "真", "text": "つまり、自分の意思とは関係なく勝手に音楽が頭の中で再生される現象ってこと？"},
    {"speaker": "理子", "text": "そう！研究者のジェームズ・ケラリスの調査によると、なんと98%の人がイヤーワームを経験してるの"},
    {"speaker": "真", "text": "98%！ほぼ全員じゃん！"},
    {"speaker": "理子", "text": "面白いことに、女性の方がイヤーワームが長く続く傾向があって、男性より不快に感じやすいっていうデータもあるの"},
    {"speaker": "真", "text": "へぇー。でもなんで脳はそんなことをするの？"},
    {"speaker": "理子", "text": "ここからが面白いところ。イヤーワームに関わっている脳の部位は主に2つ。右横側頭回と右下前頭回よ"},
    {"speaker": "真", "text": "右側の脳が音楽に関係してるんだ"},
    {"speaker": "理子", "text": "そう。これらの部位の神経回路が一種の『ループ』を作ってしまうの。レコードの針が同じ溝をぐるぐる回るみたいにね"},
    {"speaker": "真", "text": "脳内レコードプレーヤー…わかりやすい"},
    {"speaker": "理子", "text": "しかも研究で、これらの部位に関わるタンパク質の量が少ない人ほどイヤーワームが起きやすいこともわかってるの"},
    {"speaker": "真", "text": "タンパク質の量で決まるなんて、体質みたいなものなんだね"},
    {"speaker": "理子", "text": "ここからが本題。なぜ私たちは同じ曲を何度も聴いてしまうのか。大きく3つの理由があるの"},
    {"speaker": "理子", "text": "1つ目は『単純接触効果』。英語ではmere exposure effect。心理学者ザイアンスが提唱した有名な理論よ"},
    {"speaker": "真", "text": "単純接触効果？"},
    {"speaker": "理子", "text": "簡単に言うと、人は接触する回数が増えるほどその対象を好きになるっていう法則。音楽でも同じで、繰り返し聴くほどメロディが予測しやすくなって、心地よく感じるの"},
    {"speaker": "真", "text": "最初はピンとこなかった曲が、何回か聴いてるうちに好きになるやつだ！"},
    {"speaker": "理子", "text": "まさにそれ。研究でも、メロディを繰り返し聴かせると好感度が上がることが確認されてるわ"},
    {"speaker": "真", "text": "でもさ、聴きすぎると飽きるよね？"},
    {"speaker": "理子", "text": "いい質問！実はそこにも科学的な説明があるの。それが2つ目の理由『ドーパミン報酬系』よ"},
    {"speaker": "理子", "text": "好きな曲を聴くと、脳の側坐核からドーパミンが放出されるの。ドーパミンは快感や報酬に関わる神経伝達物質ね"},
    {"speaker": "真", "text": "ドーパミン！お菓子食べたときとか、ゲームで勝ったときに出るやつだ"},
    {"speaker": "理子", "text": "そう。特に面白いのは、曲のサビに向かう『盛り上がり部分』で尾状核が興奮して、サビが来た瞬間に側坐核からドーパミンがドバッと出るの"},
    {"speaker": "真", "text": "だからサビ前のAメロBメロも含めて何度も聴きたくなるんだ！期待してる時間も気持ちいいってこと？"},
    {"speaker": "理子", "text": "その通り！予測と報酬のサイクルが快感を生んでるの。でもね、これが繰り返しすぎると予測が完璧になって、驚きがなくなる"},
    {"speaker": "真", "text": "それが『飽きる』ってことか"},
    {"speaker": "理子", "text": "正確には、予測が完全に一致しすぎるとドーパミンの放出が減るの。だからある程度の複雑さがある曲ほど長く聴き続けられるわ"},
    {"speaker": "理子", "text": "そして3つ目の理由は『感情の条件付け』。扁桃体っていう脳の部位が関わってるの"},
    {"speaker": "真", "text": "扁桃体？"},
    {"speaker": "理子", "text": "ドーパミンが放出されると、扁桃体がその音楽とポジティブな感情を結びつけるの。だから同じ曲を聴くと、その時の幸せな気持ちが蘇る"},
    {"speaker": "真", "text": "あー！失恋したときに聴いてた曲を聴くと泣きそうになるのもそれ？"},
    {"speaker": "理子", "text": "まさにそう。音楽は感情の記憶と強く結びつくから、特定の曲が特定の気持ちのスイッチになるの"},
    {"speaker": "理子", "text": "イヤーワームが起きやすい曲には特徴があるの。テンポが速くてメロディラインがシンプル、そして音程の上下動が大きい曲ね"},
    {"speaker": "真", "text": "確かに、複雑なジャズとかより、ポップスのサビの方が頭に残りやすい気がする"},
    {"speaker": "理子", "text": "研究では、Lady GagaのBad RomanceやQueenのBohemian Rhapsodyが特にイヤーワームを引き起こしやすい曲として報告されてるわ"},
    {"speaker": "真", "text": "あー！Bad Romanceのあのサビ、聴いたら絶対頭から離れなくなるやつ！"},
    {"speaker": "理子", "text": "他にも面白い研究があるの。イヤーワームは『聴覚記憶』と深く関係していて、実際に音楽を聴いているときと同じ脳の領域が活性化するの"},
    {"speaker": "真", "text": "つまり頭の中で曲が流れてるとき、脳は本当に音楽を聴いてるのと同じ状態なの！？"},
    {"speaker": "理子", "text": "ほぼそう。脳のfMRI研究でそれが確認されてるわ"},
    {"speaker": "理子", "text": "じゃあどんなときにイヤーワームが起きやすいか。主に4つのトリガーがあるの"},
    {"speaker": "理子", "text": "1つ目は『最近聴いた曲』。これは単純で、直近で聴いた曲ほど脳に残りやすいの"},
    {"speaker": "真", "text": "朝聴いた曲が一日中流れてるやつだ"},
    {"speaker": "理子", "text": "2つ目は『感情の状態』。特定の気分のときに特定の曲が浮かびやすくなるの"},
    {"speaker": "真", "text": "気分がBGMを選んでるみたいだ"},
    {"speaker": "理子", "text": "3つ目は『連想』。特定の場所や人、言葉がきっかけで関連する曲が浮かぶの"},
    {"speaker": "真", "text": "海を見たらサザンが流れるみたいな？"},
    {"speaker": "理子", "text": "まさにそう！そして4つ目は『ストレスや疲労』。脳が疲れているとき、自動的な反復処理が起きやすくなるの"},
    {"speaker": "真", "text": "忙しいときほど曲が頭から離れないの、それが理由だったのか…"},
    {"speaker": "真", "text": "じゃあ逆に、イヤーワームを止める方法ってあるの？"},
    {"speaker": "理子", "text": "いくつか研究で効果が確認されている方法があるわ"},
    {"speaker": "理子", "text": "1つ目は、その曲を最後まで聴くこと。脳がループするのは曲が『未完了』だからで、最後まで聴くと脳が『完了した』と判断して止まりやすくなるの"},
    {"speaker": "真", "text": "サビだけ頭に残ってるなら、フルで聴けばいいってこと？"},
    {"speaker": "理子", "text": "そう。心理学では『ツァイガルニク効果』って言うの。未完了のタスクほど記憶に残りやすいっていう法則"},
    {"speaker": "真", "text": "ドラマの続きが気になるのと同じ原理だ！"},
    {"speaker": "理子", "text": "2つ目は、ガムを噛むこと。口を動かすと、脳の音楽再生に使うリソースが奪われてイヤーワームが弱まるっていう研究結果があるの"},
    {"speaker": "真", "text": "ガム！？そんな簡単な方法で！？"},
    {"speaker": "理子", "text": "3つ目は、別の曲で上書きすること。ただしこれは新しいイヤーワームを作るリスクもあるわ"},
    {"speaker": "真", "text": "イヤーワームの無限ループじゃん…"},
    {"speaker": "理子", "text": "だから上書きするなら、なるべく単調でテンポが遅い曲がおすすめよ"},
    {"speaker": "理子", "text": "じゃあ今日のまとめ！"},
    {"speaker": "理子", "text": "人が同じ曲を繰り返し聴く理由は3つ。単純接触効果で好感度が上がること、ドーパミン報酬系が快感を生むこと、そして感情の条件付けで記憶と結びつくこと"},
    {"speaker": "真", "text": "脳が勝手に『もう一回聴いて！』って言ってるんだね"},
    {"speaker": "理子", "text": "イヤーワームは脳の自然な働きだから、基本的には心配いらないの。むしろ音楽がいかに脳に深く影響してるかっていう証拠ね"},
    {"speaker": "真", "text": "今日の話を聞いて、ますます音楽が面白くなったよ！"},
    {"speaker": "理子", "text": "同じ曲をリピートしてる自分に気づいたら、『あ、今ドーパミン出てるんだな』って思ってみてね"},
    {"speaker": "真", "text": "科学がわかると日常が楽しくなるね！"},
    {"speaker": "理子", "text": "それがこのチャンネルのテーマだからね。みなさん、チャンネル登録と高評価、よろしくお願いします！"},
    {"speaker": "真", "text": "また次の動画で会おう！"},
]


# ============================================================
# シナリオ: 洗剤 vs 激落ちくん — 科学的にどっちが強い？
# ============================================================
CLEANING_SHORT = [
    {"speaker": "真", "text": "ねえリコ、洗剤と激落ちくん、どっちの方が汚れ落ちるの？"},
    {"speaker": "理子", "text": "実はね、この2つは汚れの落とし方が根本的に違うの。洗剤は『化学的洗浄』、激落ちくんは『物理的洗浄』"},
    {"speaker": "真", "text": "化学と物理！？掃除なのに科学の対決じゃん！"},
    {"speaker": "理子", "text": "洗剤の界面活性剤は水と油の境界をぶっ壊して汚れを包み込む。激落ちくんのメラミンフォームは硬度がガラス並みで、超微細に削り取ってるの"},
    {"speaker": "真", "text": "え、激落ちくんって削ってるの！？水だけで落ちるから魔法かと思ってた！"},
    {"speaker": "理子", "text": "結論を言うと、油汚れは洗剤の圧勝。水垢やこびりつきは激落ちくんが強い。そして組み合わせると最強よ"},
    {"speaker": "真", "text": "科学的に使い分ければ掃除マスターだね！"},
]

CLEANING_FULL = [
    {"speaker": "真", "text": "ねえリコ、台所の油汚れが全然落ちなくて困ってるんだけど…"},
    {"speaker": "理子", "text": "あー、洗剤使ってる？それとも激落ちくん派？"},
    {"speaker": "真", "text": "どっちも使ってるけど、正直どっちが強いのかよくわかんないんだよね"},
    {"speaker": "理子", "text": "実はこの2つ、汚れの落とし方が根本的に違うの。今日は『洗剤 vs 激落ちくん』を科学的に徹底比較するわ！"},
    # ── 第1章: 界面活性剤の科学 ──
    {"speaker": "理子", "text": "まずは洗剤から。洗剤の主役は『界面活性剤』っていう物質よ"},
    {"speaker": "真", "text": "界面活性剤？名前は聞いたことあるけど、何をしてるの？"},
    {"speaker": "理子", "text": "界面活性剤の分子は面白い構造をしてるの。一方の端が『親水基』で水が大好き、もう一方の端が『親油基』で油が大好き"},
    {"speaker": "真", "text": "水好きと油好きが一つの分子にくっついてるの！？"},
    {"speaker": "理子", "text": "そう。水と油は普通混ざらないけど、界面活性剤がその境界、つまり『界面』に割り込んで橋渡しをするの"},
    {"speaker": "真", "text": "だから『界面活性剤』って名前なんだ！"},
    {"speaker": "理子", "text": "油汚れに洗剤をかけると、親油基が油に突き刺さって、親水基が水側を向く。これで油が細かい粒になって水に取り囲まれるの"},
    {"speaker": "真", "text": "油を小さく分解して水で流せるようにしてるんだね"},
    {"speaker": "理子", "text": "この構造を『ミセル』って言うの。直径がだいたい数ナノメートル。油をミセルの中に閉じ込めて、水と一緒に流し去るのが洗剤の基本原理よ"},
    {"speaker": "真", "text": "ナノメートルって目に見えないくらい小さいんだよね。すごい仕組みだ"},
    {"speaker": "理子", "text": "有名な実験があるの。水面にコショウを浮かべて、洗剤を一滴垂らすとコショウがサーッと逃げていくの"},
    {"speaker": "真", "text": "見たことある！あれって何が起きてるの？"},
    {"speaker": "理子", "text": "界面活性剤が水の表面張力を急激に下げるの。コショウは表面張力で浮いてたから、それが壊れて外側に押し出されるのよ"},
    {"speaker": "真", "text": "洗剤一滴でそんなことが起きるんだ…"},
    {"speaker": "理子", "text": "ちなみに界面活性剤には大きく4つの種類があるの。陰イオン系、陽イオン系、両性イオン系、非イオン系"},
    {"speaker": "真", "text": "4種類もあるの？"},
    {"speaker": "理子", "text": "台所用洗剤に多いのは陰イオン系。洗浄力が一番強いの。柔軟剤に使われるのは陽イオン系で、これは繊維に吸着してフワフワにする効果があるわ"},
    {"speaker": "真", "text": "洗剤と柔軟剤で違う種類の界面活性剤が使われてるんだ。面白い！"},
    {"speaker": "理子", "text": "温度も重要よ。お湯を使うと界面活性剤の分子運動が活発になって、ミセル形成が早くなるの。だから油汚れはお湯で洗った方が落ちやすいのよ"},
    {"speaker": "真", "text": "おばあちゃんが『お湯で洗いなさい』って言ってたのは科学的に正しかったんだ"},
    # ── 第2章: メラミンフォームの科学 ──
    {"speaker": "理子", "text": "じゃあ次は激落ちくんの科学。激落ちくんの正体は『メラミンフォーム』っていう素材よ"},
    {"speaker": "真", "text": "メラミンフォーム？スポンジとは違うの？"},
    {"speaker": "理子", "text": "全然違う。普通のスポンジはポリウレタンで柔らかいけど、メラミンフォームはメラミン樹脂を発泡させたもので、硬度がモース硬度で約4あるの"},
    {"speaker": "真", "text": "モース硬度4って、どのくらい？"},
    {"speaker": "理子", "text": "ガラスが約5、鉄が約4.5。つまりメラミンフォームはガラスに近い硬さの超微細な繊維の集まりなの"},
    {"speaker": "真", "text": "え！あの白いフワフワがガラス並みに硬いの！？"},
    {"speaker": "理子", "text": "触った感じは柔らかいけど、それは繊維一本一本がものすごく細いから。直径わずか数マイクロメートルの硬い繊維が網目状に絡み合ってるの"},
    {"speaker": "真", "text": "じゃあ激落ちくんって、水だけで汚れを『溶かしてる』んじゃなくて…"},
    {"speaker": "理子", "text": "そう、『削ってる』の。超微細なヤスリで表面の汚れを物理的に削り取ってるのよ"},
    {"speaker": "真", "text": "魔法じゃなくて物理だったのか！"},
    {"speaker": "理子", "text": "ちなみにメラミンフォームは1990年代にドイツのBASF社が開発した素材で、元々は防音材や断熱材として使われてたの"},
    {"speaker": "真", "text": "掃除用じゃなかったんだ！"},
    {"speaker": "理子", "text": "そう。掃除に使えることが発見されたのは後からなの。日本では2003年にレック株式会社が『激落ちくん』として発売して大ヒットしたわ"},
    {"speaker": "真", "text": "もう20年以上前の商品なんだね"},
    {"speaker": "理子", "text": "だからこそ注意が必要なの。メラミンフォームは素材の表面も一緒に削っちゃうことがあるのよ"},
    {"speaker": "真", "text": "えっ、それヤバくない？"},
    {"speaker": "理子", "text": "コーティングされた家具、光沢のあるプラスチック、車のボディ、人の肌なんかには絶対使っちゃダメ。コーティングが剥がれたり、細かい傷がついて曇るの"},
    {"speaker": "真", "text": "歯を白くしようとして激落ちくんで磨く人がいるって聞いたけど…"},
    {"speaker": "理子", "text": "絶対ダメ！歯のエナメル質を削り取っちゃうの。エナメル質は再生しないから、取り返しがつかないわ"},
    # ── 第3章: 科学的対決 ──
    {"speaker": "理子", "text": "さて、ここからが本題。洗剤と激落ちくん、科学的にどっちが強いか？汚れの種類別に比較するわ"},
    {"speaker": "真", "text": "おー！科学対決、楽しみ！"},
    {"speaker": "理子", "text": "まず油汚れ。キッチンの換気扇やコンロの油。これは洗剤の圧勝よ"},
    {"speaker": "真", "text": "やっぱり油には洗剤なんだ"},
    {"speaker": "理子", "text": "界面活性剤が油を分子レベルでミセルに包み込むから、根本的に分解できるの。メラミンフォームだと表面は削れても油の膜がまた広がっちゃう"},
    {"speaker": "真", "text": "物理的に削っても油は液体だから意味ないのか"},
    {"speaker": "理子", "text": "次に水垢。蛇口やシンクの白いカリカリ。これは激落ちくんの勝ちよ"},
    {"speaker": "真", "text": "水垢って洗剤で落ちにくいもんね"},
    {"speaker": "理子", "text": "水垢の正体はカルシウムやマグネシウムの炭酸塩結晶。硬い固体だから、物理的に削り取るメラミンフォームの方が効果的なの"},
    {"speaker": "真", "text": "なるほど、固い汚れには物理攻撃が有効ってことだ"},
    {"speaker": "理子", "text": "3つ目、茶渋やコーヒー汚れ。マグカップの内側が茶色くなるやつ。これも激落ちくんが強いわ"},
    {"speaker": "真", "text": "あー、洗剤で洗っても取れないやつだ"},
    {"speaker": "理子", "text": "茶渋の正体はタンニンっていうポリフェノールが金属イオンと結合したもの。表面に固着してるから、削り取る方が効率的なの"},
    {"speaker": "真", "text": "化学的に溶かすより削った方が早いってことか"},
    {"speaker": "理子", "text": "4つ目、手垢や皮脂汚れ。スイッチプレートやドアノブの黒ずみ。これは引き分けね"},
    {"speaker": "真", "text": "引き分け？"},
    {"speaker": "理子", "text": "皮脂は油脂成分だから洗剤で落とせるけど、長期間蓄積して表面に固着してると洗剤だけでは不十分。メラミンフォームとの併用が一番効果的よ"},
    # ── 第4章: 最強の組み合わせ ──
    {"speaker": "理子", "text": "実はここからが一番大事な話。洗剤と激落ちくん、対決させるより組み合わせた方が圧倒的に強いの"},
    {"speaker": "真", "text": "合体技！？"},
    {"speaker": "理子", "text": "化学的洗浄と物理的洗浄のハイブリッド。まず洗剤で油分を浮かせて界面を崩し、そこからメラミンフォームで固着した残りを削り取る"},
    {"speaker": "真", "text": "順番が大事なんだね。先に洗剤で柔らかくしてから削る"},
    {"speaker": "理子", "text": "その通り。これは工業的な洗浄でも使われてる手法で、CIP洗浄って呼ばれてるの。化学洗浄で大まかに落として、物理洗浄で仕上げる"},
    {"speaker": "真", "text": "プロの掃除と同じ原理なんだ！"},
    {"speaker": "理子", "text": "ただし注意点があるの。メラミンフォームに洗剤を直接染み込ませすぎると、フォームの気泡が洗剤で埋まって研磨力が落ちるのよ"},
    {"speaker": "真", "text": "えー、じゃあ一緒に使えばいいってわけでもないんだ"},
    {"speaker": "理子", "text": "ベストな方法は、先にスプレー洗剤を汚れに吹きかけて少し置く。それから水で軽く流して、仕上げにメラミンフォームで擦るの"},
    {"speaker": "真", "text": "化学→物理の二段構え！これが科学的に最強の掃除法なんだね"},
    {"speaker": "理子", "text": "場所別に最強の掃除法を教えるわ。キッチンのコンロ周りは、まずアルカリ性洗剤をスプレーして5分放置。その後メラミンフォームで軽く擦る"},
    {"speaker": "真", "text": "アルカリ性？普通の洗剤じゃダメなの？"},
    {"speaker": "理子", "text": "油脂はアルカリ性で分解されやすいの。セスキ炭酸ソーダや重曹もアルカリ性だから、油汚れには効果的よ"},
    {"speaker": "真", "text": "重曹ってそういう理由で掃除に使われてるんだ"},
    {"speaker": "理子", "text": "逆にお風呂の水垢はカルシウムの結晶だから、クエン酸のような酸性のものが効くの。汚れの性質に合わせてpHを選ぶのが科学的な掃除法よ"},
    {"speaker": "真", "text": "酸性とアルカリ性を使い分けるなんて、まるで化学の実験だ"},
    # ── 第5章: 知っておくべき注意点 ──
    {"speaker": "理子", "text": "最後に、それぞれの注意点をまとめるわ"},
    {"speaker": "理子", "text": "洗剤の注意点。合成界面活性剤は水生生物に有害なものがあるの。特に直鎖アルキルベンゼンスルホン酸ナトリウム、通称LASは分解されにくいタイプもあるわ"},
    {"speaker": "真", "text": "環境にも影響があるんだ"},
    {"speaker": "理子", "text": "最近は生分解性の高い界面活性剤が増えてるけど、使いすぎは環境負荷になるの。適量を守るのが大事よ"},
    {"speaker": "理子", "text": "激落ちくんの注意点はさっきも言ったけど、使っちゃいけない場所がたくさんあるの"},
    {"speaker": "理子", "text": "フローリング、漆器、コーティング済みの鏡やレンズ、人の肌、歯、車のボディ。基本的に『傷つけたくない表面』には使わないこと"},
    {"speaker": "真", "text": "見た目が柔らかいから油断しちゃうんだよね…"},
    {"speaker": "理子", "text": "あと、メラミンフォームの削りカスは非常に細かいマイクロプラスチックになるの。排水に流すと環境に残りやすいから、拭き取ってゴミとして捨てるのがベストよ"},
    {"speaker": "真", "text": "掃除しながら環境のことも考えなきゃだね"},
    {"speaker": "理子", "text": "あともう一つ。洗剤の『混ぜるな危険』は絶対守ってね。塩素系と酸性を混ぜると有毒な塩素ガスが発生するの"},
    {"speaker": "真", "text": "それは怖い…具体的にはどんな組み合わせ？"},
    {"speaker": "理子", "text": "カビキラーのような塩素系漂白剤と、サンポールのような酸性洗剤。この2つを同じ場所で使うのは絶対NGよ"},
    {"speaker": "真", "text": "別々に使えば大丈夫なんだよね？"},
    {"speaker": "理子", "text": "そう。ただし同じ日に同じ場所で使う場合は、よく水で洗い流してからね。残留した成分が反応することもあるから"},
    # ── まとめ ──
    {"speaker": "理子", "text": "じゃあ今日のまとめ！"},
    {"speaker": "理子", "text": "洗剤は界面活性剤による『化学的洗浄』。油汚れを分子レベルで包み込んで流す。油汚れに最強"},
    {"speaker": "理子", "text": "激落ちくんはメラミンフォームによる『物理的洗浄』。ガラス並みの硬さで汚れを微細に削り取る。水垢や茶渋に最強"},
    {"speaker": "理子", "text": "そして最強は、化学洗浄→物理洗浄の二段構え。洗剤で浮かせてからメラミンフォームで仕上げ"},
    {"speaker": "真", "text": "科学がわかると掃除が上手くなるんだね！"},
    {"speaker": "理子", "text": "汚れの正体を知れば、正しい武器を選べるってことよ。みなさん、チャンネル登録と高評価、よろしくお願いします！"},
    {"speaker": "真", "text": "科学的お掃除で、家をピカピカにしよう！また次の動画で！"},
]


# ============================================================
# シナリオ: なぜ猫はキュウリに驚くのか — 捕食者検出×視覚の死角
# ============================================================
CAT_CUCUMBER_SHORT = [
    {"speaker": "真", "text": "猫の後ろにキュウリ置いたらめっちゃ飛ぶの知ってる！？"},
    {"speaker": "理子", "text": "あの動画バズってるよね。実はあれ、猫の脳が『ヘビだ！』って誤認してるの"},
    {"speaker": "真", "text": "ヘビ！？キュウリなのに！？"},
    {"speaker": "理子", "text": "猫の視覚は動体検出に特化してて、静止物の識別が苦手。細長い緑の物体＝爬虫類の可能性、って本能が判断するの"},
    {"speaker": "真", "text": "じゃあ猫にとってはマジで命の危機なんだ…"},
    {"speaker": "理子", "text": "そう。だからこの実験、実は猫に強いストレスを与えてるの。面白半分でやっちゃダメよ"},
    {"speaker": "真", "text": "知らなかった…科学を知ると優しくなれるね"},
]

CAT_CUCUMBER_FULL = [
    # ── 冒頭フック（バズ狙い） ──
    {"speaker": "真", "text": "ねえねえリコ！猫の後ろにキュウリ置いたらめっちゃ飛び上がる動画見たことある！？"},
    {"speaker": "理子", "text": "あー、あのバズり動画ね。再生回数が億超えてるやつもあるわよね"},
    {"speaker": "真", "text": "あれなんで！？キュウリだよ！？ただの野菜だよ！？"},
    {"speaker": "理子", "text": "実はあれ、猫の脳の中では『命に関わる緊急事態』が起きてるの"},
    {"speaker": "真", "text": "えっ…命に関わる！？キュウリで！？"},
    {"speaker": "理子", "text": "今日はその謎を、脳科学と進化生物学で完全解説するわ！"},
    # ── CTA ──
    {"speaker": "真", "text": "これ絶対面白いやつだ！"},
    {"speaker": "理子", "text": "ちなみにこのチャンネルでは、こういう日常のふとした疑問を科学で解き明かしてるの"},
    {"speaker": "真", "text": "まだチャンネル登録してない人はぜひお願いします！あと高評価といいねボタンも押してくれると僕たちのやる気がめっちゃ上がります！"},
    {"speaker": "理子", "text": "コメントも嬉しいわ。『うちの猫もキュウリで飛んだ』って人いたら教えてね"},
    {"speaker": "真", "text": "よし！じゃあ本題いってみよう！"},
    # ── 第1章: 猫の視覚システム ──
    {"speaker": "理子", "text": "まず大前提として、猫と人間では見えている世界がまったく違うの"},
    {"speaker": "真", "text": "猫って目がいいイメージあるけど"},
    {"speaker": "理子", "text": "暗闇での視力は人間の6倍。でも色の識別は苦手で、赤と緑の区別がほとんどできないの"},
    {"speaker": "真", "text": "えっ、猫にはキュウリの緑が見えてないの！？"},
    {"speaker": "理子", "text": "正確には、猫の網膜には錐体細胞が2種類しかないの。人間は3種類。だから色彩の解像度が低いのよ"},
    {"speaker": "真", "text": "人間で言うと色覚異常に近い感じ？"},
    {"speaker": "理子", "text": "そう。でも猫の視覚が本当にすごいのは動体検出能力。桿体細胞の密度が人間の6〜8倍で、暗闇でもわずかな動きを捉えられるの"},
    {"speaker": "真", "text": "ハンターとして進化してきたんだもんね"},
    {"speaker": "理子", "text": "ところが、この動体検出特化型の視覚には弱点があるの。静止している物体の細かい形を識別するのが苦手なのよ"},
    {"speaker": "真", "text": "動いてるものには強いけど、止まってるものは見分けにくいってこと？"},
    {"speaker": "理子", "text": "その通り。猫の視力は人間換算で0.1〜0.2程度。つまり目の前に突然現れた細長い静止物体の正体を、猫はすぐには判別できないの"},
    # ── 第2章: ヘビ検出モジュール ──
    {"speaker": "理子", "text": "ここからが本題よ。なぜ猫はキュウリを見て『飛び上がる』のか"},
    {"speaker": "真", "text": "待ってました！"},
    {"speaker": "理子", "text": "答えは『ヘビ検出モジュール』。哺乳類の脳に備わった、ヘビを素早く検出して回避する神経回路よ"},
    {"speaker": "真", "text": "ヘビ検出モジュール！？脳にそんな機能が！？"},
    {"speaker": "理子", "text": "京都大学の正高信男教授の研究で有名になったの。霊長類や多くの哺乳類は、ヘビの形状に対して他の刺激より速く反応する神経回路を持ってるの"},
    {"speaker": "真", "text": "人間もヘビ苦手な人多いもんね"},
    {"speaker": "理子", "text": "実は人間でも、花や魚の写真の中にヘビの写真を混ぜると、ヘビだけ異常に速く見つけられるの。これを『ヘビ検出仮説』って言うわ"},
    {"speaker": "真", "text": "意識する前に脳が反応してるんだ"},
    {"speaker": "理子", "text": "そう。扁桃体と上丘が関わっていて、視覚情報が大脳皮質で処理される前に、つまり『何か考える前に』体が逃避行動を起こすの"},
    {"speaker": "真", "text": "考える前に飛び上がるってこと！？"},
    {"speaker": "理子", "text": "まさにそう。猫の場合、この反応がさらに強化されてるの。猫科動物は野生環境でヘビに噛まれるリスクが高かったから"},
    {"speaker": "真", "text": "じゃあキュウリの細長い形が…"},
    {"speaker": "理子", "text": "猫の脳が『ヘビかもしれない！』と誤検出してるの。色が判別しにくい＋静止物体の形が曖昧＝細長い＝ヘビの可能性、って本能が判断する"},
    # ── 第3章: なぜ「背後」が重要なのか ──
    {"speaker": "理子", "text": "でもね、キュウリをただ見せても猫はそこまで驚かないの。ポイントは『背後に置く』っていうこと"},
    {"speaker": "真", "text": "あ、確かにバズ動画って全部、猫が食事中とかに背後にこっそり置いてるよね"},
    {"speaker": "理子", "text": "これは猫の『安全地帯認知』に関係してるの。猫は食事場所を安全な場所として認識してる"},
    {"speaker": "真", "text": "ご飯食べてるときはリラックスしてるもんね"},
    {"speaker": "理子", "text": "安全だと思っている場所で振り返ったら、見覚えのない細長い物体がいる。これが猫の脳に『安全地帯が侵害された！』というパニック信号を送るの"},
    {"speaker": "真", "text": "安心してるところに突然ヘビっぽいものが出現するから、余計にびっくりするんだ"},
    {"speaker": "理子", "text": "そう。専門用語では『文脈的恐怖条件づけ』に近い反応ね。場所の安全性が裏切られることで、通常より強い恐怖反応が起きるの"},
    {"speaker": "真", "text": "自分の部屋にヘビがいたら、外で見るより何倍も怖いもんね"},
    {"speaker": "理子", "text": "まさにその感覚よ"},
    # ── 第4章: 驚愕反射のメカニズム ──
    {"speaker": "理子", "text": "猫がキュウリを見て飛び上がるあの動き、あれは『驚愕反射』って言うの"},
    {"speaker": "真", "text": "驚愕反射？"},
    {"speaker": "理子", "text": "英語ではstartle reflex。突然の刺激に対して、意識的な判断を介さずに体が反射的に動く現象よ"},
    {"speaker": "真", "text": "反射ってことは、自分の意思じゃないんだ"},
    {"speaker": "理子", "text": "そう。脳幹の巨大網様体核が制御していて、わずか数十ミリ秒で反応するの。大脳皮質が『あ、キュウリだ』と判断するより遥かに速い"},
    {"speaker": "真", "text": "数十ミリ秒！？瞬きより速いじゃん！"},
    {"speaker": "理子", "text": "猫の場合、筋肉の瞬発力が体重比で人間の3〜4倍あるから、驚愕反射で体重の5倍の高さまでジャンプできるの"},
    {"speaker": "真", "text": "だからあんなに高く飛ぶんだ！"},
    {"speaker": "理子", "text": "あの動画が面白いのは、普段優雅な猫が予想外のリアクションをするギャップよね。でも猫の中では命がけの回避行動が起きてるの"},
    # ── 第5章: すべての猫が驚くわけではない ──
    {"speaker": "真", "text": "でもさ、全部の猫がキュウリで飛ぶわけじゃないよね？"},
    {"speaker": "理子", "text": "いい質問！実は猫の反応には個体差がかなりあるの"},
    {"speaker": "理子", "text": "子猫の時期に様々な物体に触れた経験がある猫は、新しい物体への恐怖反応が弱い傾向がある。これを『社会化期の経験学習』って言うの"},
    {"speaker": "真", "text": "いろんなものに慣れてると怖くないんだ"},
    {"speaker": "理子", "text": "あと、室内飼いのみの猫と、外にも出る猫では反応が違うの。外に出る猫は実際にヘビを見る機会があるから、逆に細長い物体への警戒心が強い場合もある"},
    {"speaker": "真", "text": "経験で変わるんだね"},
    {"speaker": "理子", "text": "品種による差もあるわ。シャム猫やアビシニアンなど活発な品種は反応が大きい傾向があって、ペルシャやラグドールなど穏やかな品種は比較的冷静"},
    {"speaker": "真", "text": "猫の性格も関係あるんだ"},
    # ── 第5.5章: 他の動物もヘビを怖がるのか ──
    {"speaker": "真", "text": "ちなみにヘビを怖がるのって猫だけ？"},
    {"speaker": "理子", "text": "いい質問！実はヘビ検出は哺乳類に広く見られる能力なの。サルの研究が特に有名よ"},
    {"speaker": "真", "text": "サルも？"},
    {"speaker": "理子", "text": "カリフォルニア大学の研究で、実験室で生まれてヘビを見たことがないサルに初めてヘビを見せると、一瞬で警戒姿勢を取ったの"},
    {"speaker": "真", "text": "見たことないのに怖がるの！？完全に本能じゃん！"},
    {"speaker": "理子", "text": "しかもMRIで脳を調べると、ヘビの画像に対しては視床枕という部位が特異的に活性化するの。花や車の画像では起きない反応よ"},
    {"speaker": "真", "text": "ヘビ専用の脳回路があるってこと？"},
    {"speaker": "理子", "text": "イスベルの『ヘビ検出理論』によると、霊長類の優れた視覚システム自体が、ヘビから身を守るために進化したって仮説もあるくらいよ"},
    {"speaker": "真", "text": "視力がいいのはヘビのおかげ！？スケールでかい話だな"},
    {"speaker": "理子", "text": "面白いことに、鳥類にもヘビへの先天的な恐怖反応があるの。ニワトリのヒナにヘビの模型を見せると逃避行動を取る研究がある"},
    {"speaker": "真", "text": "鳥も！？ってことは恐竜の時代からヘビは怖がられてたのかも"},
    {"speaker": "理子", "text": "その可能性はあるわね。ヘビと哺乳類の共進化は6000万年以上の歴史があるとされてるの"},
    {"speaker": "真", "text": "6000万年の本能がキュウリで発動してると思うと…猫に申し訳なくなるね"},
    {"speaker": "理子", "text": "ちなみに犬はキュウリにそこまで驚かないの。犬は猫ほど視覚依存じゃなくて嗅覚で先に情報を得るから、キュウリの匂いで安全と判断できるのよ"},
    {"speaker": "真", "text": "犬と猫で反応が違うのも面白い！"},
    # ── 第5.7章: バズ動画の倫理 ──
    {"speaker": "理子", "text": "ここで一つ、バズ動画の問題にも触れておくわ"},
    {"speaker": "真", "text": "問題？"},
    {"speaker": "理子", "text": "猫キュウリ動画は2015年頃にYouTubeで大流行したの。再生回数は累計で数十億回を超えてる"},
    {"speaker": "真", "text": "数十億！？"},
    {"speaker": "理子", "text": "問題は、バズを狙って何度も繰り返す飼い主が出てきたこと。1回ならまだしも、繰り返すと猫はPTSD類似の症状を示すことがあるの"},
    {"speaker": "真", "text": "PTSDって人間がなるやつだよね？猫もなるの！？"},
    {"speaker": "理子", "text": "正確には慢性ストレス反応ね。特定の場所を避ける、食欲低下、過度のグルーミングによる脱毛。これらは獣医行動学で認められた症状よ"},
    {"speaker": "真", "text": "再生数のために猫が苦しむなんて…"},
    {"speaker": "理子", "text": "2017年にはアメリカ動物虐待防止協会が公式に『猫をキュウリで驚かせる行為は動物虐待に該当する可能性がある』と声明を出してるの"},
    {"speaker": "真", "text": "そこまでの話だったんだ"},
    # ── 第6章: なぜやってはいけないのか ──
    {"speaker": "理子", "text": "最後にこれだけは絶対に伝えたいことがあるの"},
    {"speaker": "真", "text": "なに？"},
    {"speaker": "理子", "text": "猫にキュウリを置いて驚かせる実験、絶対にやらないでください"},
    {"speaker": "真", "text": "えっ、動画だとみんなやってるけど…"},
    {"speaker": "理子", "text": "獣医師や動物行動学者が口を揃えて警告してるの。これは猫に深刻なストレスを与える行為なのよ"},
    {"speaker": "理子", "text": "まず、驚愕反射の瞬間に猫は家具にぶつかったり、着地に失敗して怪我をするリスクがある"},
    {"speaker": "真", "text": "確かに動画でも棚にぶつかってるのあったな…"},
    {"speaker": "理子", "text": "さらに深刻なのは心理的影響。安全地帯だった食事場所がトラウマになると、食欲不振やストレス性の行動問題が出ることがあるの"},
    {"speaker": "真", "text": "ご飯の場所が怖くなっちゃうのか…"},
    {"speaker": "理子", "text": "慢性的なストレスは猫の免疫系にも影響するの。コルチゾールが持続的に高い状態は、尿路疾患や消化器疾患のリスクを上げる"},
    {"speaker": "真", "text": "バズり動画のために猫が病気になるかもしれないなんて…"},
    {"speaker": "理子", "text": "科学を知ると、なぜダメなのかが理解できるでしょ。猫の脳は本気で『死ぬかもしれない』と反応してるんだから"},
    # ── まとめ ──
    {"speaker": "理子", "text": "じゃあ今日のまとめ！"},
    {"speaker": "理子", "text": "猫がキュウリに驚く理由は3つ。第1に、猫の視覚は動体検出に特化していて静止物体の識別が苦手。第2に、哺乳類に備わったヘビ検出モジュールが細長い物体に反応する。第3に、安全地帯の背後という文脈がパニックを増幅する"},
    {"speaker": "真", "text": "猫にとっては本当の命の危機だったんだね…"},
    {"speaker": "理子", "text": "面白い動画の裏には、何百万年もの進化の歴史が詰まってるの。それを知ると、猫に対する見方も変わるわよね"},
    {"speaker": "真", "text": "うん。もう絶対キュウリ置いたりしない。猫が安心できる環境を作ってあげたい"},
    {"speaker": "理子", "text": "それが科学リテラシーの力よ。面白がるだけじゃなくて、正しい知識で動物を守れるようになる"},
    {"speaker": "真", "text": "今日もめっちゃ勉強になった！"},
    {"speaker": "理子", "text": "最後まで見てくれてありがとう！このチャンネルでは毎週、日常の疑問を科学で解説してるから、チャンネル登録と高評価、よろしくお願いします！"},
    {"speaker": "真", "text": "コメント欄で『うちの猫はキュウリ平気だよ』って人も教えてね！それじゃまた次の動画で！"},
]


# ============================================================
# サンプルシナリオ: 1人語り考察「なぜ人は行列に並ぶのか」
# ============================================================
QUEUE_MONO_SHORT = [
    {"text": "ディズニーランドで2時間並ぶのに、病院の30分は耐えられない。この矛盾、あなたも経験ありませんか？"},
    {"text": "行動経済学では『期待効用理論』で説明されます。楽しい結果が待っている待ち時間は、脳がドーパミンを出し続けるので苦痛を感じにくい。"},
    {"text": "一方、不確実で不快な結果が予想される待ち時間は、扁桃体が不安反応を引き起こし、時間を長く感じさせます。"},
    {"text": "つまり、待つこと自体が苦痛なのではなく、何を待っているかが全てなんです。"},
    {"text": "次に行列に並ぶとき、自分の脳が何をしているか、観察してみてください。"},
]

QUEUE_MONO_FULL = [
    {"chapter_title": "Chapter 1 — 行列のパラドックス", "duration": 3.5},
    {"text": "ディズニーランドで2時間待てるのに、コンビニの5分が耐えられない。この不思議な現象、心当たりありませんか？", "chapter": "Chapter 1 — 行列のパラドックス"},
    {"text": "実はこれ、単なる我慢比べではなく、脳の情報処理に深く関わる科学的な現象なんです。"},
    {"text": "今日は行動経済学と神経科学の観点から、『なぜ人は行列に並ぶのか』を考えていきます。"},
    {"chapter_title": "Chapter 2 — 期待効用と待ち時間の心理学", "duration": 3.5},
    {"text": "1944年、フォン・ノイマンとモルゲンシュテルンが提唱した期待効用理論。これが行列心理の基本フレームです。", "chapter": "Chapter 2 — 期待効用と待ち時間の心理学"},
    {"text": "人は『結果の価値×その確率』で意思決定をする。ディズニーのアトラクションは確実に楽しい体験が待っている。だから期待効用が高い。"},
    {"text": "ここで面白いのは、待っている間にもドーパミンが分泌されていること。期待そのものが報酬になっているんです。"},
    {"text": "神経科学者のウォルフラム・シュルツの実験では、報酬予測時の腹側被蓋野のドーパミンニューロンが、実際の報酬時と同程度に活性化することが示されました。"},
    {"text": "つまり、並んでいる時間は『苦痛を耐えている時間』ではなく、『報酬を先取りしている時間』なんです。"},
    {"chapter_title": "Chapter 3 — 不確実性が生む苦痛", "duration": 3.5},
    {"text": "では逆に、なぜ病院の待ち時間は長く感じるのか。", "chapter": "Chapter 3 — 不確実性が生む苦痛"},
    {"text": "ここに関わるのが不確実性の概念です。診察結果がわからない、いつ呼ばれるかわからない。この二重の不確実性が扁桃体を刺激します。"},
    {"text": "扁桃体は脅威検出の中核。不確実な状況では、コルチゾールを分泌させてストレス反応を引き起こします。"},
    {"text": "ここにカーネマンのピーク・エンドの法則も絡んできます。体験の印象は、最も感情が強かった瞬間と終了時の感情で決まる。"},
    {"text": "病院の待合室では、不安がピークに達しやすく、呼ばれた瞬間も安堵より緊張が勝る。だから全体の記憶が『長くて辛い』になるんです。"},
    {"chapter_title": "Chapter 4 — ラーメン屋の行列が成立する理由", "duration": 3.5},
    {"text": "ここで身近な例を考えましょう。人気ラーメン屋の行列。", "chapter": "Chapter 4 — ラーメン屋の行列が成立する理由"},
    {"text": "1時間並んで食べるラーメン。冷静に考えれば、隣の空いてる店でも十分美味しいかもしれない。でも並ぶ。なぜか。"},
    {"text": "ここに働くのは社会的証明のバイアスです。チャルディーニが提唱したこの概念、『他の人がやっていることは正しい』という推論。"},
    {"text": "行列の長さそのものが品質のシグナルになる。認知的負荷が高い状況、つまり情報が多すぎて判断できないとき、人はヒューリスティクスに頼ります。"},
    {"text": "さらに、並んだ後で『美味しくなかった』と認めるのは認知的不協和を生みます。だから脳は自動的に体験を美化する。"},
    {"text": "これがサンクコストバイアスと結びつきます。1時間投資した以上、それに見合う価値があったと信じたい。"},
    {"chapter_title": "Chapter 5 — デジタル時代の見えない行列", "duration": 3.5},
    {"text": "現代ではもう一つの行列があります。画面の向こうの、見えない行列。", "chapter": "Chapter 5 — デジタル時代の見えない行列"},
    {"text": "Amazonのセールで在庫限りと表示される商品。チケット購入サイトの待機画面。これらは全て行列の心理学を応用したデザインです。"},
    {"text": "希少性のバイアス。手に入りにくいものほど価値が高いと感じる。これにFOMO、Fear of Missing Outが加わると、人はデジタル行列に何時間も並びます。"},
    {"text": "興味深いのは、物理的な行列と違い、デジタル行列では進捗が見えにくいこと。これが不確実性を高め、より強い没入を生みます。"},
    {"chapter_title": "Chapter 6 — 結論", "duration": 3.0},
    {"text": "行列に並ぶという行為は、実は人間の認知バイアスの総合展示場です。", "chapter": "Chapter 6 — 結論"},
    {"text": "期待効用、社会的証明、サンクコスト、認知的不協和、希少性バイアス。これだけのメカニズムが、たった一列の行列の中で同時に働いている。"},
    {"text": "次に行列に並ぶとき、あるいは並ばない選択をするとき、自分の脳がどのバイアスに動かされているか、観察してみてください。"},
    {"text": "それでは、また次の考察で。"},
]


# ============================================================
# Thumbnail generation
# ============================================================
def _thumb_gradient(w, h):
    """紫～深青グラデーション背景（カノン風）"""
    img = Image.new("RGB", (w, h))
    pixels = []
    for y in range(h):
        ry = y / h
        r = int(55 * (1 - ry) + 10 * ry)
        g = int(0 * (1 - ry) + 5 * ry)
        b = int(120 * (1 - ry) + 150 * ry)
        pixels.extend([(r, g, b)] * w)
    img.putdata(pixels)
    return img.convert("RGBA")


def _thumb_neon_glow(img):
    """ネオン風光彩オーブ"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    orbs = [
        (180, 130, 220, (160, 30, 220, 55)),
        (950, 80, 240, (30, 80, 240, 50)),
        (640, 480, 300, (80, 20, 200, 40)),
        (1100, 380, 180, (120, 40, 240, 50)),
        (80, 520, 150, (140, 10, 200, 45)),
        (700, 200, 160, (60, 100, 255, 35)),
    ]
    for cx, cy, r, color in orbs:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    blurred = overlay.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(img, blurred)


def _thumb_draw_text_with_outline(draw, text, x, y, font, fill=(255,255,255),
                                    outline_color=(0,0,0), outline_width=6, anchor="mm"):
    """太い縁取り付きテキスト描画"""
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _thumb_draw_badge(draw, text, x, y, font, bg_color=(255, 200, 0), text_color=(20, 0, 80), radius=16):
    """バッジ描画（影付き角丸）"""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 28, 14
    rx0, ry0 = x - tw // 2 - pad_x, y - th // 2 - pad_y
    rx1, ry1 = x + tw // 2 + pad_x, y + th // 2 + pad_y
    draw.rounded_rectangle([rx0+3, ry0+3, rx1+3, ry1+3], radius=radius, fill=(0, 0, 0, 80))
    draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=radius, fill=bg_color)
    draw.text((x, y), text, font=font, fill=text_color, anchor="mm")


def _thumb_scatter_dots(img, count=35):
    """散りばめた小ドット（ピンク/紫系パーティクル）"""
    import random
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    colors = [
        (255, 80, 180, 140), (200, 60, 255, 120), (120, 80, 255, 100),
        (255, 120, 200, 110), (180, 40, 220, 130), (100, 200, 255, 90),
    ]
    random.seed(42)  # deterministic for consistency
    for _ in range(count):
        cx = random.randint(0, img.width)
        cy = random.randint(0, img.height)
        r = random.randint(3, 8)
        c = random.choice(colors)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c)
    return Image.alpha_composite(img, overlay)


def _thumb_dotted_circle(img, cx, cy, radius=45, dot_count=24, dot_r=3, color=(100, 200, 255, 180)):
    """点線サークル装飾"""
    import math
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(dot_count):
        angle = 2 * math.pi * i / dot_count
        dx = int(cx + radius * math.cos(angle))
        dy = int(cy + radius * math.sin(angle))
        draw.ellipse([dx-dot_r, dy-dot_r, dx+dot_r, dy+dot_r], fill=color)
    return Image.alpha_composite(img, overlay)


def generate_thumbnail(title, prefix, out_dir, bg_video_path=None, thumb_info=None):
    """
    Generate a YouTube-style thumbnail (カノン風デザイン).

    thumb_info dict (optional, for customizing text):
        hook_lines: list of str — main title lines (hook question, yellow, large)
        subtitle: str — topic name (cyan)
        tagline: str — catchy one-liner (smaller yellow)
    """
    TW, TH = 1280, 720

    # Default thumb_info if not provided
    if thumb_info is None:
        thumb_info = {}
    hook_lines = thumb_info.get("hook_lines", [title])
    subtitle = thumb_info.get("subtitle", title)
    tagline = thumb_info.get("tagline", "")

    # ----- System fonts (macOS) with fallbacks -----
    font_paths_bold = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    font_paths_medium = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path_bold = next((fp for fp in font_paths_bold if Path(fp).exists()), None)
    font_path_medium = next((fp for fp in font_paths_medium if Path(fp).exists()), font_path_bold)

    use_system_font = font_path_bold is not None

    # ----- 1. Background: gradient + glow + dots -----
    canvas = _thumb_gradient(TW, TH)
    canvas = _thumb_neon_glow(canvas)
    canvas = _thumb_scatter_dots(canvas, count=35)

    # ----- 2. Characters (small, at bottom corners) -----
    for name, cfg in CHAR_CONFIG.items():
        char_dir = ASSETS_DIR / "characters" / ("riko" if name == "理子" else "makoto")
        if not char_dir.exists():
            char_dir = ASSETS_DIR / ("riko" if name == "理子" else "makoto")
        expr = "happy" if name == "理子" else "surprise"
        sprite_path = char_dir / f"{expr}.png"
        if not sprite_path.exists():
            sprite_path = char_dir / "normal.png"
        if sprite_path.exists():
            sprite = Image.open(str(sprite_path)).convert("RGBA")
            # Small characters at bottom corners (like reference)
            s_h = int(TH * 0.28)
            s_w = int(sprite.width * s_h / sprite.height)
            sprite = sprite.resize((s_w, s_h), Image.LANCZOS)
            if cfg["side"] == "left":
                canvas.paste(sprite, (10, TH - s_h), sprite)
            else:
                canvas.paste(sprite, (TW - s_w - 10, TH - s_h), sprite)

    # ----- 3. Dotted circle decoration at top -----
    canvas = _thumb_dotted_circle(canvas, TW // 2, 120, radius=45)

    draw = ImageDraw.Draw(canvas)
    cx = TW // 2

    if use_system_font:
        font_title = ImageFont.truetype(font_path_bold, 72)
        font_sub = ImageFont.truetype(font_path_medium, 36)
        font_badge = ImageFont.truetype(font_path_medium, 26)
        font_tag = ImageFont.truetype(font_path_medium, 24)

        # ----- Layout from top -----
        y = 170  # below dotted circle

        # "ゆっくり解説" red badge
        _thumb_draw_badge(draw, "ゆっくり解説", cx, y, font_badge,
                          bg_color=(220, 40, 40), text_color=(255, 255, 255), radius=6)
        y += 50

        # Hook title lines (yellow, large, with black outline)
        for line in hook_lines:
            bb = font_title.getbbox(line)
            line_h = bb[3] - bb[1]
            y += 8
            _thumb_draw_text_with_outline(draw, line, cx, y + line_h // 2, font_title,
                                          fill=(255, 255, 50), outline_color=(0, 0, 0), outline_width=7)
            y += line_h

        # Subtitle (cyan)
        y += 16
        bb_sub = font_sub.getbbox(subtitle)
        sub_h = bb_sub[3] - bb_sub[1]
        _thumb_draw_text_with_outline(draw, subtitle, cx, y + sub_h // 2, font_sub,
                                      fill=(80, 220, 255), outline_color=(0, 0, 40), outline_width=4)
        y += sub_h

        # Tagline (smaller yellow/white)
        if tagline:
            y += 14
            bb_tag = font_tag.getbbox(tagline)
            tag_h = bb_tag[3] - bb_tag[1]
            # Yellow badge-style background
            tag_w = bb_tag[2] - bb_tag[0]
            draw.rounded_rectangle([cx - tag_w//2 - 16, y - 4, cx + tag_w//2 + 16, y + tag_h + 8],
                                   radius=6, fill=(200, 160, 0, 180))
            draw.text((cx, y + tag_h // 2 + 2), tagline, font=font_tag,
                      fill=(255, 255, 255), anchor="mm")

    else:
        # Fallback: composite text (no system fonts)
        draw = ImageDraw.Draw(canvas)
        y = 200

        # Badge
        badge_text = "ゆっくり解説"
        bw = measure_composite_text(draw, badge_text, 26)
        draw.rounded_rectangle([(cx - bw//2 - 12), y - 6, (cx + bw//2 + 12), y + 32],
                               radius=6, fill=(220, 40, 40))
        draw_composite_text(draw, (cx - bw//2, y), badge_text, 26, (255, 255, 255))
        y += 50

        # Hook lines
        for line in hook_lines:
            tw = measure_composite_text(draw, line, 72)
            draw_composite_text(draw, ((TW - tw)//2, y), line, 72, (255, 255, 50),
                                stroke_fill=(0, 0, 0), stroke_width=6)
            y += 84

        # Subtitle
        y += 10
        sw = measure_composite_text(draw, subtitle, 36)
        draw_composite_text(draw, ((TW - sw)//2, y), subtitle, 36, (80, 220, 255),
                            stroke_fill=(0, 0, 40), stroke_width=3)
        y += 48

        # Tagline
        if tagline:
            y += 8
            tw = measure_composite_text(draw, tagline, 24)
            draw.rounded_rectangle([(cx - tw//2 - 12), y - 4, (cx + tw//2 + 12), y + 30],
                                   radius=6, fill=(200, 160, 0, 180))
            draw_composite_text(draw, ((TW - tw)//2, y), tagline, 24, (255, 255, 255))

    out = str(Path(out_dir) / f"{prefix}_サムネイル.png")
    canvas.convert("RGB").save(out, quality=95)
    print(f"🖼️ サムネイル: {out}")
    return out


def generate_short_thumbnail(title, prefix, out_dir, thumb_info=None):
    """Generate a vertical (9:16) thumbnail for YouTube Shorts."""
    SW, SH = 1080, 1920

    # Default thumb_info
    if thumb_info is None:
        thumb_info = {}
    hook_lines = thumb_info.get("hook_lines", [title])
    subtitle = thumb_info.get("subtitle", title)
    tagline = thumb_info.get("tagline", "")

    # System fonts
    font_paths_bold = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    font_paths_medium = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W5.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path_bold = next((fp for fp in font_paths_bold if Path(fp).exists()), None)
    font_path_medium = next((fp for fp in font_paths_medium if Path(fp).exists()), font_path_bold)
    use_system_font = font_path_bold is not None

    # 1. Background: vertical gradient + glow
    canvas = Image.new("RGB", (SW, SH))
    pixels = []
    for y in range(SH):
        ry = y / SH
        r = int(55 * (1 - ry) + 10 * ry)
        g = int(0 * (1 - ry) + 5 * ry)
        b = int(120 * (1 - ry) + 150 * ry)
        pixels.extend([(r, g, b)] * SW)
    canvas.putdata(pixels)
    canvas = canvas.convert("RGBA")

    # Neon glow orbs (vertical layout)
    overlay = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw_glow = ImageDraw.Draw(overlay)
    orbs = [
        (150, 200, 200, (160, 30, 220, 50)),
        (800, 100, 220, (30, 80, 240, 45)),
        (540, 900, 280, (80, 20, 200, 35)),
        (900, 600, 160, (120, 40, 240, 45)),
        (100, 1400, 180, (140, 10, 200, 40)),
        (600, 1600, 200, (60, 100, 255, 30)),
    ]
    for cx, cy, r, color in orbs:
        draw_glow.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    canvas = Image.alpha_composite(canvas, overlay.filter(ImageFilter.GaussianBlur(80)))

    # Scatter dots
    import random
    random.seed(99)
    dot_overlay = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    dot_draw = ImageDraw.Draw(dot_overlay)
    colors = [(255, 80, 180, 140), (200, 60, 255, 120), (120, 80, 255, 100), (255, 120, 200, 110)]
    for _ in range(40):
        dx, dy = random.randint(0, SW), random.randint(0, SH)
        dr = random.randint(3, 8)
        dot_draw.ellipse([dx-dr, dy-dr, dx+dr, dy+dr], fill=random.choice(colors))
    canvas = Image.alpha_composite(canvas, dot_overlay)

    # 2. Characters (medium size, lower area)
    for name, cfg in CHAR_CONFIG.items():
        char_dir = ASSETS_DIR / "characters" / ("riko" if name == "理子" else "makoto")
        if not char_dir.exists():
            char_dir = ASSETS_DIR / ("riko" if name == "理子" else "makoto")
        expr = "happy" if name == "理子" else "surprise"
        sprite_path = char_dir / f"{expr}.png"
        if not sprite_path.exists():
            sprite_path = char_dir / "normal.png"
        if sprite_path.exists():
            sprite = Image.open(str(sprite_path)).convert("RGBA")
            s_h = int(SH * 0.35)
            s_w = int(sprite.width * s_h / sprite.height)
            sprite = sprite.resize((s_w, s_h), Image.LANCZOS)
            if cfg["side"] == "left":
                canvas.paste(sprite, (-int(s_w * 0.05), SH - s_h), sprite)
            else:
                canvas.paste(sprite, (SW - s_w + int(s_w * 0.05), SH - s_h), sprite)

    # 3. Dotted circle
    canvas = _thumb_dotted_circle(canvas, SW // 2, 280, radius=55, dot_count=28)

    draw = ImageDraw.Draw(canvas)
    cx = SW // 2

    if use_system_font:
        font_title = ImageFont.truetype(font_path_bold, 80)
        font_sub = ImageFont.truetype(font_path_medium, 44)
        font_badge = ImageFont.truetype(font_path_medium, 30)
        font_tag = ImageFont.truetype(font_path_medium, 28)

        y = 370

        # "ゆっくり解説" badge
        _thumb_draw_badge(draw, "ゆっくり解説", cx, y, font_badge,
                          bg_color=(220, 40, 40), text_color=(255, 255, 255), radius=6)
        y += 60

        # Hook lines
        for line in hook_lines:
            bb = font_title.getbbox(line)
            line_h = bb[3] - bb[1]
            y += 10
            _thumb_draw_text_with_outline(draw, line, cx, y + line_h // 2, font_title,
                                          fill=(255, 255, 50), outline_color=(0, 0, 0), outline_width=8)
            y += line_h

        # Subtitle
        y += 20
        bb_sub = font_sub.getbbox(subtitle)
        sub_h = bb_sub[3] - bb_sub[1]
        _thumb_draw_text_with_outline(draw, subtitle, cx, y + sub_h // 2, font_sub,
                                      fill=(80, 220, 255), outline_color=(0, 0, 40), outline_width=5)
        y += sub_h

        # Tagline
        if tagline:
            y += 18
            bb_tag = font_tag.getbbox(tagline)
            tag_h = bb_tag[3] - bb_tag[1]
            tag_w = bb_tag[2] - bb_tag[0]
            # Wrap if too wide
            if tag_w > SW - 80:
                mid = len(tagline) // 2
                for i in range(mid - 3, mid + 4):
                    if i < len(tagline) and tagline[i] in "！？、。のはがをに":
                        line1, line2 = tagline[:i+1], tagline[i+1:]
                        for tl in [line1, line2]:
                            bb_tl = font_tag.getbbox(tl)
                            tl_h = bb_tl[3] - bb_tl[1]
                            tl_w = bb_tl[2] - bb_tl[0]
                            draw.rounded_rectangle([cx - tl_w//2 - 16, y - 4, cx + tl_w//2 + 16, y + tl_h + 8],
                                                   radius=6, fill=(200, 160, 0, 180))
                            draw.text((cx, y + tl_h // 2 + 2), tl, font=font_tag, fill=(255, 255, 255), anchor="mm")
                            y += tl_h + 10
                        break
                else:
                    draw.rounded_rectangle([cx - tag_w//2 - 16, y - 4, cx + tag_w//2 + 16, y + tag_h + 8],
                                           radius=6, fill=(200, 160, 0, 180))
                    draw.text((cx, y + tag_h // 2 + 2), tagline, font=font_tag, fill=(255, 255, 255), anchor="mm")
            else:
                draw.rounded_rectangle([cx - tag_w//2 - 16, y - 4, cx + tag_w//2 + 16, y + tag_h + 8],
                                       radius=6, fill=(200, 160, 0, 180))
                draw.text((cx, y + tag_h // 2 + 2), tagline, font=font_tag, fill=(255, 255, 255), anchor="mm")
    else:
        # Fallback: composite text
        draw = ImageDraw.Draw(canvas)
        y = 400
        badge_text = "ゆっくり解説"
        bw = measure_composite_text(draw, badge_text, 30)
        draw.rounded_rectangle([(cx - bw//2 - 12), y - 6, (cx + bw//2 + 12), y + 36], radius=6, fill=(220, 40, 40))
        draw_composite_text(draw, (cx - bw//2, y), badge_text, 30, (255, 255, 255))
        y += 60
        for line in hook_lines:
            tw = measure_composite_text(draw, line, 72)
            draw_composite_text(draw, ((SW - tw)//2, y), line, 72, (255, 255, 50),
                                stroke_fill=(0, 0, 0), stroke_width=7)
            y += 90
        y += 10
        sw = measure_composite_text(draw, subtitle, 44)
        draw_composite_text(draw, ((SW - sw)//2, y), subtitle, 44, (80, 220, 255),
                            stroke_fill=(0, 0, 40), stroke_width=4)

    out = str(Path(out_dir) / f"{prefix}_ショート_サムネイル.png")
    canvas.convert("RGB").save(out, quality=95)
    print(f"🖼️ ショートサムネイル: {out}")
    return out


# ============================================================
# Description generation
# ============================================================
CHANNEL_NAME = "リコとマコトのゆっくり日常科学"
CHANNEL_CONCEPT = "日常のふとした疑問を科学の視点からゆっくり解説するチャンネル"

def generate_video_title(title, thumb_info=None):
    """
    YouTubeタイトル生成（カノン準拠テンプレート）
    型: 【ゆっくり解説】＋フック質問（具体例入り）＋テーマ名
    例: 【ゆっくり解説】なぜ「天体観測」「キセキ」「マリーゴールド」は売れた？カノン進行の科学
    """
    hook = ""
    if thumb_info and thumb_info.get("hook_lines"):
        hook = "".join(thumb_info["hook_lines"])

    if hook:
        return f"【ゆっくり解説】{hook}「{title}」"
    else:
        return f"【ゆっくり解説】{title}"


def generate_short_title(title, thumb_info=None, channel_dict=None):
    """
    YouTubeショートタイトル生成
    型: [シリーズ名]＋フック質問＋テーマ名 #shorts
    """
    hook = ""
    if thumb_info and thumb_info.get("hook_lines"):
        hook = "".join(thumb_info["hook_lines"])
    tagline = ""
    if thumb_info and thumb_info.get("tagline"):
        tagline = thumb_info["tagline"]

    series_prefix = ""
    if channel_dict:
        series_prefix = channel_dict.get("short_series_name") or ""

    if hook:
        return f"{series_prefix}{hook}#{title} #shorts #ゆっくり解説"
    else:
        return f"{series_prefix}{title} #shorts #ゆっくり解説"


def _build_description_template(channel_dict, title, channel_concept):
    """チャンネル設定から説明文用テンプレート断片を組み立てる。

    channel_dict["description_template"] が定義されていればそちらを優先。
    未定義のチャンネルは defaults.hashtags と concept からフォールバック生成する。
    """
    tmpl = (channel_dict or {}).get("description_template") or {}
    defaults = (channel_dict or {}).get("defaults") or {}
    default_hashtags = defaults.get("hashtags") or ["#ゆっくり解説"]
    default_hashtag_str = " ".join(default_hashtags)

    main_intro = tmpl.get("main_intro")
    if main_intro is None:
        main_intro = (
            f"{{title}}について、ゆっくり解説していきます。\n"
            f"{channel_concept}\n"
            "ぜひ最後までご視聴ください！"
        )
    main_intro = main_intro.format(title=title, concept=channel_concept)

    main_hashtags = tmpl.get("main_hashtags") or default_hashtag_str
    short_hashtags = tmpl.get("short_hashtags") or f"#shorts {default_hashtag_str}"

    return {
        "main_intro": main_intro,
        "main_hashtags": main_hashtags,
        "short_hashtags": short_hashtags,
    }


def generate_descriptions(title, short_scenario, full_scenario=None, thumb_info=None, video_title=None, channel_dict=None):
    """
    Generate description text files for both main and short videos.
    テンプレート型（カノン準拠）: タイトル→フック→概要→タイムスタンプ→チャンネル情報→ハッシュタグ
    """
    # チャンネル名/コンセプト — channel_dict が渡されていればそちらを優先
    channel_name = (channel_dict or {}).get("name") or CHANNEL_NAME
    channel_concept = (channel_dict or {}).get("concept") or CHANNEL_CONCEPT
    desc_tmpl = _build_description_template(channel_dict, title, channel_concept)

    # YouTubeタイトル（説明文の最上部に表示）
    if video_title is None:
        video_title = generate_video_title(title, thumb_info)
    short_title = generate_short_title(title, thumb_info, channel_dict=channel_dict)

    hook = ""
    if thumb_info and thumb_info.get("hook_lines"):
        hook = "".join(thumb_info["hook_lines"])
    tagline = ""
    if thumb_info and thumb_info.get("tagline"):
        tagline = thumb_info["tagline"]

    # ---- ショート説明文 ----
    first_line = short_scenario[0].get("text", "") if short_scenario else ""
    lines_short = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🎬 続きはフル動画で公開中！",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👉 『{title}』",
        f"   チャンネル「{channel_name}」で検索！",
        "",
        "▼ ショートでは語りきれなかった",
        "  詳しい解説・データ・裏話は本編へ ▼",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📝 {hook or first_line}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📺 {channel_name}",
        f"   {channel_concept}",
        "",
        desc_tmpl["short_hashtags"],
    ]

    # ---- メイン説明文 ----
    # 概要セクション
    summary = f"{hook}" if hook else f"{title}について"
    if tagline:
        summary += f"\n{tagline}"

    # タイムスタンプ（シナリオから自動生成、2分ごとの目安）
    timestamps = []
    if full_scenario:
        # 約2分間隔でチャプター生成（1行 ≈ 8秒として概算）
        secs_per_line = 8.0
        chapter_interval = 120  # 2分ごと
        current_chapter_time = 0
        timestamps.append("00:00 オープニング")
        for i, entry in enumerate(full_scenario):
            estimated_time = int(i * secs_per_line)
            # Monologue chapter_title entries: use as chapter marker
            if "chapter_title" in entry:
                mm = estimated_time // 60
                ss = estimated_time % 60
                timestamps.append(f"{mm:02d}:{ss:02d} {entry['chapter_title']}")
                current_chapter_time = estimated_time
                continue
            if estimated_time >= current_chapter_time + chapter_interval:
                current_chapter_time = estimated_time
                mm = estimated_time // 60
                ss = estimated_time % 60
                text = entry.get("text", entry.get("chapter_title", ""))
                chapter_title = text[:20].rstrip("。！？、")
                timestamps.append(f"{mm:02d}:{ss:02d} {chapter_title}")
        timestamps.append("エンディング")

    lines_main = [
        f"タイトル: {video_title}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 {summary}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        desc_tmpl["main_intro"],
        "",
    ]

    # タイムスタンプセクション
    if timestamps:
        lines_main += [
            "⏱ タイムスタンプ",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ] + timestamps + [""]

    # チャンネル情報
    lines_main += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📺 チャンネル: {channel_name}",
        f"   {channel_concept}",
        "",
        "🔔 チャンネル登録・高評価をぜひお願いします！",
        "   新しい動画を見逃さないよう通知をONにしてね",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        desc_tmpl["main_hashtags"],
    ]

    return {
        "short": "\n".join(lines_short),
        "main": "\n".join(lines_main),
        "video_title": video_title,
        "short_title": short_title,
    }


# ============================================================
# Full pipeline: generate everything into one folder
# ============================================================
def _generate_html_thumbnail(title, prefix, out_dir, channel_dict, thumb_info=None):
    """HTML+CSS+Playwright サムネ生成（GPT-4o + DALL-E 3）。

    失敗したら None を返す（呼び出し側で Pillow 版にフォールバック）。
    """
    try:
        from pipeline.thumbnail_generator import generate_thumbnail as _html_thumb
    except Exception as e:
        print(f"⚠️ thumbnail_generator import failed: {e}")
        return None

    api_key = OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("⚠️ OPENAI_API_KEY 未設定 → HTMLサムネをスキップ")
        return None

    out_path = Path(out_dir) / f"{prefix}_サムネイル.png"
    bg_path = Path(out_dir) / f"{prefix}_サムネ背景.png"
    try:
        # thumb_info に line1/line2/line3_badge があれば GPT-4o をスキップ
        brief_override = None
        if thumb_info and any(thumb_info.get(k) for k in ("line1", "line2", "line3_badge")):
            brief_override = {
                "line1": thumb_info.get("line1") or thumb_info.get("hook_lines", [""])[0] or title,
                "line2": thumb_info.get("line2") or "驚きの真実！？",
                "line3_badge": thumb_info.get("line3_badge") or thumb_info.get("badge_text") or "衝撃の事実",
                "sub_text": thumb_info.get("sub_text") or thumb_info.get("subtitle") or "",
                "highlight_word": thumb_info.get("highlight_word", ""),
                "background_concept": thumb_info.get("background_concept")
                    or f"Cinematic illustration related to: {title}",
            }
        result = _html_thumb(
            title,
            channel_dict,
            out_path,
            openai_api_key=api_key,
            background_save_path=bg_path,
            brief_override=brief_override,
        )
        print(f"🖼️ サムネイル(HTML): {result['thumbnail_path']}")
        return result["thumbnail_path"]
    except Exception as e:
        print(f"⚠️ HTMLサムネ生成失敗 → Pillow版にフォールバック: {e}")
        return None


def generate_all(title, prefix, short_scenario, full_scenario=None,
                 bg_video_path=None, output_dir=None, gen_type="both", bg_type="auto",
                 thumb_info=None, speed=None, target_duration=None, video_title=None,
                 style="yukkuri", use_illustrations=True,
                 channel_format=None, char_config=None, channel_dict=None,
                 bgm_volume=None,
                 cancel_check=None, scenario_meta=None):
    """
    Generate all outputs into one folder.

    Args:
        title: Theme name (used as folder name)
        prefix: File prefix (e.g. "earworm")
        short_scenario: Scenario lines for short video
        full_scenario: Scenario lines for full video (defaults to short if None)
        bg_video_path: Path to background video or image
        output_dir: Override output directory
        gen_type: "both", "short", or "full"
        bg_type: "video" / "static" / "auto"
        thumb_info: dict with hook_lines, subtitle, tagline for thumbnail
        style: "yukkuri" = ゆっくり対話, "monologue" = 1人語り考察
        use_illustrations: True = GPT DALL-Eで手書き風イラスト生成 (yukkuriスタイル時)
        channel_format: dict from VideoFormat.to_dict() — チャンネル固定フォーマット
        char_config: dict of character configs (None = global CHAR_CONFIG)

    Returns:
        dict with output paths
    """
    # Increase file descriptor limit for large scenarios
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < 2048:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(2048, hard), hard))
            print(f"📎 File descriptor limit: {soft} → {min(2048, hard)}")
    except Exception:
        pass

    if full_scenario is None:
        full_scenario = short_scenario

    # ジョブ中断チェック用ヘルパー（cancel_check が None なら no-op）
    def _ck():
        if cancel_check is not None:
            cancel_check()

    _ck()

    # Determine output directory
    if output_dir:
        out_dir = Path(output_dir) / title
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = get_output_dir(title)

    print(f"📂 出力先: {out_dir}")
    print(f"🎨 スタイル: {'ゆっくり対話' if style == 'yukkuri' else '1人語り考察'}")

    # Generate video_title if not provided
    if video_title is None:
        video_title = generate_video_title(title, thumb_info)
    short_title = generate_short_title(title, thumb_info, channel_dict=channel_dict)
    results = {"output_dir": str(out_dir), "video_title": video_title, "short_title": short_title, "style": style}

    channel_id = (channel_dict or {}).get("id") if channel_dict else None

    # ── Scenario archive (A1) — markdown 原文を永続化 ──
    if channel_id:
        try:
            from pipeline.analytics.scenario_archive import archive_scenario
            meta = scenario_meta or {}
            archive_scenario(
                channel_id=channel_id,
                prefix=prefix,
                title=title,
                short_scenario=short_scenario,
                full_scenario=full_scenario,
                thumb_info=thumb_info,
                theme=meta.get("theme"),
                style=style,
                video_title=video_title,
                applied_feedback=meta.get("applied_feedback"),
                generated_by=meta.get("generated_by"),
                selected_by=(meta.get("compete") or {}).get("selected_by") if meta.get("compete") else None,
                compete=meta.get("compete"),
            )
        except Exception as e:
            print(f"⚠️ scenario archive failed: {e}")

    # ── Style routing ──
    if style == "monologue":
        # Monologue style — no thumbnail generation for now (different aesthetic)
        # TODO: Monologue-specific thumbnail generator
        _ck()
        html_thumb = _generate_html_thumbnail(title, prefix, out_dir, channel_dict, thumb_info) if channel_dict else None
        results["thumbnail"] = html_thumb or generate_thumbnail(
            title, prefix, str(out_dir), bg_video_path, thumb_info=thumb_info,
        )

        if gen_type in ("short", "both"):
            _ck()
            results["short"] = generate_monologue_short(
                short_scenario, title, prefix, bg_video_path,
                out_dir=str(out_dir), bg_type=bg_type, speed=speed,
                channel_format=channel_format, channel_id=channel_id,
                bgm_volume=bgm_volume)

        if gen_type in ("full", "both"):
            _ck()
            results["full"] = generate_monologue_video(
                full_scenario, title, prefix, bg_video_path,
                out_dir=str(out_dir), bg_type=bg_type, speed=speed,
                target_duration=target_duration,
                channel_format=channel_format, channel_id=channel_id,
                bgm_volume=bgm_volume)

    else:
        # Yukkuri dialogue style (default)
        # 1. Thumbnails (HTML+Playwright when channel_dict is supplied; else legacy Pillow)
        _ck()
        html_thumb = _generate_html_thumbnail(title, prefix, out_dir, channel_dict, thumb_info) if channel_dict else None
        results["thumbnail"] = html_thumb or generate_thumbnail(
            title, prefix, str(out_dir), bg_video_path, thumb_info=thumb_info,
        )
        if gen_type in ("short", "both"):
            _ck()
            results["short_thumbnail"] = generate_short_thumbnail(title, prefix, str(out_dir), thumb_info=thumb_info)

        # 2. Videos
        if gen_type in ("short", "both"):
            _ck()
            results["short"] = generate_short_video(short_scenario, title, prefix, bg_video_path,
                                                     out_dir=str(out_dir), bg_type=bg_type, speed=speed,
                                                     channel_format=channel_format, char_config=char_config,
                                                     channel_id=channel_id, bgm_volume=bgm_volume)

        if gen_type in ("full", "both"):
            _ck()
            results["full"] = generate_full_video(full_scenario, title, prefix, bg_video_path,
                                                   out_dir=str(out_dir), bg_type=bg_type, speed=speed,
                                                   target_duration=target_duration,
                                                   use_illustrations=use_illustrations,
                                                   channel_format=channel_format, char_config=char_config,
                                                   channel_id=channel_id, bgm_volume=bgm_volume)

    # 3. Description txts (common to both styles)
    _ck()
    descs = generate_descriptions(title, short_scenario, full_scenario, thumb_info=thumb_info, video_title=video_title, channel_dict=channel_dict)

    short_desc_path = str(out_dir / f"{prefix}_ショート_説明文.txt")
    main_desc_path = str(out_dir / f"{prefix}_メイン_説明文.txt")

    if gen_type in ("short", "both"):
        with open(short_desc_path, "w", encoding="utf-8") as f:
            f.write(descs["short"])
        results["short_description"] = short_desc_path
        print(f"📝 ショート説明文: {short_desc_path}")

    if gen_type in ("full", "both"):
        with open(main_desc_path, "w", encoding="utf-8") as f:
            f.write(descs["main"])
        results["main_description"] = main_desc_path
        print(f"📝 メイン説明文: {main_desc_path}")

    icloud_dir = copy_to_icloud(out_dir, title)
    if icloud_dir is not None:
        results["icloud_dir"] = str(icloud_dir)

    print(f"\n🎉 All done! → {out_dir}")
    return results


# ============================================================
# Channel-mode runner
# ============================================================
def _run_channel_mode(args):
    """Run video generation using a channel JSON + scenario JSON.

    Loads:
      - data/channels/<id>.json           — channel config (chars, fmt, defaults)
      - data/scenarios/<id>/<scenario>.json — scenario lines + thumb info
    """
    # Make sibling-package import work whether invoked as module or script
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from channels import ChannelManager  # noqa: E402

    cm = ChannelManager(data_dir=str(repo_root / "data" / "channels"))
    ch = cm.get(args.channel)
    if ch is None:
        print(f"❌ Unknown channel: {args.channel}")
        print(f"   Available: {', '.join(cm.list_ids())}")
        sys.exit(1)

    # ── Locate scenario JSON ──
    scenarios_dir = repo_root / "data" / "scenarios" / args.channel
    if args.scenario_file:
        sc_path = Path(args.scenario_file)
        if not sc_path.is_absolute():
            sc_path = repo_root / sc_path
    else:
        if not scenarios_dir.exists():
            print(f"❌ Scenarios dir not found: {scenarios_dir}")
            sys.exit(1)
        candidates = sorted(scenarios_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print(f"❌ No scenario files in: {scenarios_dir}")
            sys.exit(1)
        sc_path = candidates[0]
    print(f"📄 Scenario file: {sc_path}")

    sc_data = json.loads(sc_path.read_text(encoding="utf-8"))

    # ── Resolve background ──
    bg = args.bg
    if bg is None:
        bg_rel = ch.defaults.get("bg_path")
        if bg_rel:
            cand = repo_root / bg_rel
            if cand.exists():
                bg = str(cand)
    if bg is None:
        for candidate in [
            ASSETS_DIR / "backgrounds" / "ocean_waves.mp4",
            ASSETS_DIR / "bg" / "ocean_waves.mp4",
        ]:
            if candidate.exists():
                bg = str(candidate)
                break

    bg_type = args.bg_type
    if bg_type == "auto":
        bg_type = ch.defaults.get("bg_type", "auto")
    print(f"🖼️ Background: {bg} (type={bg_type})")

    # ── Resolve title / prefix / scenarios ──
    title = sc_data.get("title") or sc_path.stem
    prefix = sc_data.get("prefix") or sc_path.stem
    short_scenario = sc_data.get("short_scenario") or sc_data.get("short") or []
    full_scenario = sc_data.get("full_scenario") or sc_data.get("full") or short_scenario
    video_title = sc_data.get("video_title")
    thumb_info = sc_data.get("thumb_info")

    # Channel defaults
    speed = args.speed if args.speed != 1.3 else ch.get_speed()
    target_duration = args.duration if args.duration != 600 else ch.get_target_duration()
    use_illustrations = (not args.no_illustrations) and ch.get_use_illustrations()
    style = args.style or ch.style or "yukkuri"

    print(f"📺 Channel: {ch.id} ({ch.name})")
    print(f"📝 Title: {title}")
    print(f"⏱️  target_duration={target_duration}s, speed={speed}x")
    print(f"🎬 Lines — short:{len(short_scenario)} full:{len(full_scenario)}")

    generate_all(
        title=title,
        prefix=prefix,
        short_scenario=short_scenario,
        full_scenario=full_scenario,
        bg_video_path=bg,
        output_dir=args.output,
        gen_type=args.type,
        bg_type=bg_type,
        thumb_info=thumb_info,
        speed=speed,
        target_duration=target_duration,
        video_title=video_title,
        style=style,
        use_illustrations=use_illustrations,
        channel_format=ch.video_format.to_dict(),
        char_config=ch.char_config(),
    )


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="ゆっくり動画生成")
    parser.add_argument("--type", choices=["full", "short", "both"], default="both")
    parser.add_argument("--scenario", default="earworm", help="Scenario name")
    parser.add_argument("--style", choices=["yukkuri", "monologue"], default=None,
                        help="Video style: yukkuri=ゆっくり対話, monologue=1人語り考察")
    parser.add_argument("--bg", default=None, help="Background video/image path")
    parser.add_argument("--bg-type", choices=["video", "static", "auto"], default="auto",
                        help="Background type: video=動的, static=静的, auto=自動判定")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--speed", type=float, default=1.3, help="話速倍率 (default: 1.3)")
    parser.add_argument("--duration", type=int, default=600, help="目標尺（秒, default: 600 = 10分）")
    parser.add_argument("--no-illustrations", action="store_true", help="イラスト生成をスキップ")
    parser.add_argument("--channel", default=None, help="Channel ID (e.g. daily-science). 指定時は data/channels/<id>.json と data/scenarios/<id>/ を使う")
    parser.add_argument("--scenario-file", default=None, help="Path to a scenario JSON (used with --channel; defaults to newest in data/scenarios/<channel>/)")
    args = parser.parse_args()

    # ── Channel mode: load channel config + scenario JSON, then run pipeline ──
    if args.channel:
        return _run_channel_mode(args)

    bg = args.bg
    if bg is None:
        for candidate in [
            ASSETS_DIR / "backgrounds" / "ocean_waves.mp4",
            ASSETS_DIR / "bg" / "ocean_waves.mp4",
        ]:
            if candidate.exists():
                bg = str(candidate)
                break

    SCENARIOS = {
        "earworm": {
            "title": "イヤーワームの科学",
            "video_title": "【ゆっくり解説】なぜ同じ曲が頭から離れない？98%が経験する「イヤーワーム」の科学",
            "prefix": "earworm",
            "short": EARWORM_SHORT,
            "full": EARWORM_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["なぜ同じ曲を", "何度も聴いちゃうの?"],
                "subtitle": "イヤーワームの科学",
                "tagline": "98%の人が経験！脳が勝手にリピートする理由",
            },
        },
        "cleaning": {
            "title": "洗剤vs激落ちくんの科学",
            "video_title": "【ゆっくり解説】洗剤vs激落ちくん、科学的にどっちが強い？化学洗浄vs物理洗浄の科学",
            "prefix": "cleaning",
            "short": CLEANING_SHORT,
            "full": CLEANING_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["洗剤vs激落ちくん", "どっちが強い？"],
                "subtitle": "化学洗浄vs物理洗浄",
                "tagline": "科学的に正しい掃除法を徹底比較！",
            },
        },
        "cat_cucumber": {
            "title": "なぜ猫はキュウリに驚くのか",
            "video_title": "【ゆっくり解説】なぜ猫はキュウリで飛び上がる？億再生バズ動画の裏にある脳科学と進化の秘密",
            "prefix": "cat_cucumber",
            "short": CAT_CUCUMBER_SHORT,
            "full": CAT_CUCUMBER_FULL,
            "style": "yukkuri",
            "thumb_info": {
                "hook_lines": ["なぜ猫は", "キュウリで飛ぶ！？"],
                "subtitle": "ヘビ検出モジュール×驚愕反射",
                "tagline": "億再生バズ動画の裏にある脳科学の真実",
            },
        },
        "queue": {
            "title": "なぜ人は行列に並ぶのか",
            "video_title": "なぜディズニーで2時間並べるのに病院の30分が耐えられないのか【行動経済学×神経科学】",
            "prefix": "queue",
            "short": QUEUE_MONO_SHORT,
            "full": QUEUE_MONO_FULL,
            "style": "monologue",
            "thumb_info": {
                "hook_lines": ["行列に並ぶ", "科学的な理由"],
                "subtitle": "行動経済学×神経科学",
                "tagline": "なぜディズニーの2時間は平気なのに病院の30分は地獄なのか",
            },
        },
    }

    sc = SCENARIOS.get(args.scenario)
    if not sc:
        print(f"❌ Unknown scenario: {args.scenario}")
        print(f"   Available: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    # Style: CLI arg overrides scenario default
    style = args.style or sc.get("style", "yukkuri")

    generate_all(
        title=sc["title"],
        prefix=sc["prefix"],
        short_scenario=sc["short"],
        full_scenario=sc["full"],
        bg_video_path=bg,
        output_dir=args.output,
        gen_type=args.type,
        bg_type=args.bg_type,
        thumb_info=sc.get("thumb_info"),
        speed=args.speed,
        target_duration=args.duration,
        video_title=sc.get("video_title"),
        style=style,
        use_illustrations=not args.no_illustrations,
    )


if __name__ == "__main__":
    main()
