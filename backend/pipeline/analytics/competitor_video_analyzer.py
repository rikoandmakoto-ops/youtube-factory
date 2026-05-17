"""
CompetitorVideoAnalyzer (Phase F-1c) — 競合動画を「ビジュアル + 内容」の両面から深掘り分析。

ビジュアル分析:
  - yt-dlp で動画を一時ディレクトリに最低画質でダウンロード
  - サムネを取得（YouTube i.ytimg.com / yt-dlp の --write-thumbnail）
  - ffmpeg でランダム 3 シーンのフレームを JPEG で抽出
  - **抽出後に動画ファイルは必ず削除する**（ディスク圧迫防止）
  - サムネ + フレーム 3 枚を Claude Vision に投げて、構図 / 色 / テキスト配置 /
    演出スタイル / 視覚的な差別化ポイントを JSON で返してもらう

内容分析:
  - まず yt-dlp で YouTube 自動字幕（vtt）を取得（第一手段、無料・高速）
  - 字幕無ければ decopy.ai (https://decopy.ai/jp/youtube-video-summarizer/) を
    Playwright スクレイピングで要約取得（フォールバック）
  - 取得した字幕/要約を Claude に投げて、テーマ / 構成 / 尺配分 / パンチライン /
    なぜ伸びているかの仮説 / 話し方のトーン / 視聴者を引き込むテクニックを JSON で返してもらう

公開関数:
  - analyze_one_video(channel_id, competitor_id, video) → dict
  - analyze_top_videos_for_competitor(channel_id, competitor_id, *, top_n=3) → dict
      （既存の competitor_analyses から TOP 動画を引っ張ってきて深掘り）
  - analyze_top_videos_for_channel(channel_id, *, top_n_per_competitor=3) → dict
      （登録済み全競合に対してまとめて実行）

制約:
  - 動画ファイルは常に try/finally で削除する。サイズ抑制のため
    `-f 'worst[ext=mp4]/worst'` 相当を指定して短時間で落とす。
  - yt-dlp / ffmpeg が無ければ visual 分析は空、content 分析だけ走らせる。
  - decopy.ai は API が無いので Playwright で best-effort スクレイピング。
    取れなければ transcript_source='none' で content 分析もスキップ。
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import store as analytics_store


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CACHE_ROOT = PROJECT_ROOT / "data" / "cache" / "competitor_videos"


# ---------------------------------------------------------------------
# Binary availability
# ---------------------------------------------------------------------

def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _ytdlp_bin() -> Optional[str]:
    """yt-dlp が PATH にあれば返す。無ければ pip 経由で `python -m yt_dlp` を試す。"""
    p = _which("yt-dlp")
    if p:
        return p
    # `python -m yt_dlp` で呼べるなら sentinel を返す
    try:
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return f"{sys.executable} -m yt_dlp"
    except Exception:
        pass
    return None


def _ffmpeg_bin() -> Optional[str]:
    return _which("ffmpeg") or _which("ffmpeg.exe")


def _ffprobe_bin() -> Optional[str]:
    return _which("ffprobe") or _which("ffprobe.exe")


def _ensure_yt_dlp() -> Optional[str]:
    """yt-dlp が無ければ pip でインストールを試みる。"""
    b = _ytdlp_bin()
    if b:
        return b
    try:
        print("📦 yt-dlp not found — installing via pip ...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "yt-dlp"],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            print(f"⚠️ pip install yt-dlp failed: {r.stderr.strip()[:200]}")
            return None
    except Exception as e:
        print(f"⚠️ pip install yt-dlp failed: {e}")
        return None
    return _ytdlp_bin()


# ---------------------------------------------------------------------
# Cache layout
# ---------------------------------------------------------------------

def _video_cache_dir(competitor_id: str, video_id: str) -> Path:
    safe_comp = re.sub(r"[^A-Za-z0-9_\-]", "_", competitor_id)
    safe_vid = re.sub(r"[^A-Za-z0-9_\-]", "_", video_id)
    p = CACHE_ROOT / safe_comp / safe_vid
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------
# yt-dlp wrappers
# ---------------------------------------------------------------------

def _run_subprocess(cmd: List[str], *, timeout: int = 300) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def _ytdlp_cmd(bin_str: str, args: List[str]) -> List[str]:
    """`bin_str` が "python -m yt_dlp" のときも split して扱える形にする。"""
    parts = bin_str.split()
    return parts + args


def _download_thumbnail(video_id: str, dest: Path) -> Optional[Path]:
    """YouTube サムネを直接落とす。yt-dlp 不要、urllib のみ。"""
    candidates = [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]
    out = dest / f"thumb_{video_id}.jpg"
    for url in candidates:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "youtube-factory/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if data and len(data) > 1024:
                out.write_bytes(data)
                return out
        except Exception:
            continue
    return None


def _download_video(
    ytdlp: str, video_id: str, dest: Path, *, max_height: int = 360
) -> Optional[Path]:
    """yt-dlp で最低画質に近い MP4 を 1 本ダウンロード。返り値はファイルパス。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tpl = str(dest / "video.%(ext)s")
    # 1) format 18 (360p mp4 progressive: video+audio in one file) を最優先
    # 2)無ければ単一ファイルで最低解像度（storyboard を弾くため vcodec/acodec 必須）
    # 3) android player client で YouTube の SABR ガードを回避
    fmt = (
        f"18/worst[ext=mp4][vcodec!=none][acodec!=none][height<={max_height}]"
        "/worst[vcodec!=none][acodec!=none]"
    )
    args = [
        "-q",
        "--no-warnings",
        "--no-playlist",
        "--no-progress",
        "--extractor-args", "youtube:player_client=android,web_safari",
        "-f", fmt,
        "-o", out_tpl,
        url,
    ]
    rc, _stdout, stderr = _run_subprocess(_ytdlp_cmd(ytdlp, args), timeout=300)
    if rc != 0:
        cleaned = "\n".join(
            ln for ln in (stderr or "").splitlines()
            if ln.strip()
            and "NotOpenSSLWarning" not in ln
            and "Deprecated Feature" not in ln
            and "warnings.warn" not in ln
            and "urllib3" not in ln
        )
        print(f"⚠️ yt-dlp download failed ({video_id}): {cleaned.strip()[:400]}")
        return None
    # 落ちたファイルを拾う（拡張子は mp4 以外も来うる）
    for ext in ("mp4", "webm", "mkv", "m4a"):
        p = dest / f"video.{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    # fallback: dest 内の動画っぽいファイルを探す
    for p in dest.iterdir():
        if p.is_file() and p.suffix.lower() in {".mp4", ".webm", ".mkv"}:
            return p
    return None


_VTT_TAG_RE = re.compile(r"<[^>]+>")
_VTT_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->")
_VTT_CUE_NUM_RE = re.compile(r"^\d+$")


def _parse_vtt(text: str) -> str:
    """VTT/SRT 字幕からタイムコード等を除いて本文を結合。"""
    lines: List[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if _VTT_TS_RE.match(line):
            continue
        if _VTT_CUE_NUM_RE.match(line):
            continue
        clean = _VTT_TAG_RE.sub("", line).strip()
        if not clean:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        lines.append(clean)
    return "\n".join(lines)


def _fetch_youtube_subtitles(ytdlp: str, video_id: str, dest: Path) -> Optional[str]:
    """yt-dlp で日本語 / 英語の自動字幕を試す。先に手動 → 自動の順で。"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tpl = str(dest / "subs.%(ext)s")
    languages = "ja,en,ja.*,en.*"
    args = [
        "-q", "--no-warnings", "--no-playlist", "--no-progress",
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", languages,
        "--sub-format", "vtt/srv1/best",
        "-o", out_tpl,
        url,
    ]
    rc, _stdout, stderr = _run_subprocess(_ytdlp_cmd(ytdlp, args), timeout=60)
    if rc != 0:
        # 失敗してもファイルが落ちている可能性は低い、抜ける
        return None
    # dest 直下に subs.*.vtt が落ちている
    vtt_files = sorted(dest.glob("subs.*.vtt")) + sorted(dest.glob("subs.*.srt"))
    if not vtt_files:
        return None
    # 優先順位: ja > en
    def _lang_priority(p: Path) -> int:
        name = p.name.lower()
        if ".ja" in name:
            return 0
        if ".en" in name:
            return 1
        return 2
    vtt_files.sort(key=_lang_priority)
    chosen = vtt_files[0]
    try:
        text = chosen.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    parsed = _parse_vtt(text)
    # 字幕ファイルは消す（容量対策）
    for p in vtt_files:
        try:
            p.unlink()
        except Exception:
            pass
    return parsed.strip() or None


# ---------------------------------------------------------------------
# ffmpeg frame extraction
# ---------------------------------------------------------------------

def _probe_duration_seconds(ffprobe: str, video_path: Path) -> Optional[float]:
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    rc, stdout, _ = _run_subprocess(cmd, timeout=30)
    if rc != 0:
        return None
    try:
        return float(stdout.strip())
    except Exception:
        return None


def _extract_random_frames(
    ffmpeg: str, video_path: Path, dest: Path, *, count: int = 3,
    duration_seconds: Optional[float] = None,
) -> List[Path]:
    """動画から count シーンのフレームを JPEG で抽出。

    duration が不明なら 5..60s の範囲で擬似ランダムに選ぶ。
    最初の 5% と最後の 5% は除外（タイトル / 終了画面を避ける）。
    """
    if duration_seconds is None or duration_seconds <= 0:
        # 動画自体は短い保証がないので推定値
        duration_seconds = 60.0
    head_skip = max(2.0, duration_seconds * 0.05)
    tail_skip = max(2.0, duration_seconds * 0.05)
    usable_start = head_skip
    usable_end = max(usable_start + 1.0, duration_seconds - tail_skip)
    rng = random.Random(hash(str(video_path)) & 0xFFFFFFFF)
    points: List[float] = []
    if usable_end - usable_start <= count:
        # 等間隔
        step = (usable_end - usable_start) / max(count + 1, 2)
        for i in range(count):
            points.append(usable_start + step * (i + 1))
    else:
        for _ in range(count * 4):
            if len(points) >= count:
                break
            t = rng.uniform(usable_start, usable_end)
            if all(abs(t - x) > 1.5 for x in points):
                points.append(t)
        if len(points) < count:
            # 足りなければ等間隔で埋める
            step = (usable_end - usable_start) / (count + 1)
            for i in range(count - len(points)):
                points.append(usable_start + step * (i + 1))
    points.sort()

    frames: List[Path] = []
    for idx, t in enumerate(points):
        out = dest / f"frame_{idx + 1}.jpg"
        cmd = [
            ffmpeg, "-loglevel", "error", "-y",
            "-ss", f"{t:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale='min(1280,iw)':-2",
            "-q:v", "3",
            str(out),
        ]
        rc, _stdout, stderr = _run_subprocess(cmd, timeout=60)
        if rc == 0 and out.exists() and out.stat().st_size > 0:
            frames.append(out)
        else:
            print(f"  ⚠️ frame extract failed (t={t:.1f}s): {stderr.strip()[:120]}")
    return frames


# ---------------------------------------------------------------------
# decopy.ai fallback (Playwright スクレイピング)
# ---------------------------------------------------------------------

_DECOPY_URL = "https://decopy.ai/jp/youtube-video-summarizer/"


def _scrape_decopy_ai(video_id: str, *, timeout_ms: int = 90_000) -> Optional[str]:
    """decopy.ai にアクセスして要約テキストを取得（best-effort）。

    DOM が変わったら null を返すだけ。本体クラッシュさせない。
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        print("⚠️ playwright not available — decopy.ai fallback skipped")
        return None
    url = f"https://www.youtube.com/watch?v={video_id}"
    summary_text: Optional[str] = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/123.0.0.0 Safari/537.36"
                    ),
                    locale="ja-JP",
                )
                page = context.new_page()
                page.goto(_DECOPY_URL, timeout=timeout_ms, wait_until="domcontentloaded")
                # URL を入れる input を best-effort で探す
                input_candidates = [
                    "input[type='url']",
                    "input[placeholder*='URL']",
                    "input[placeholder*='youtube']",
                    "input[name*='url']",
                    "textarea",
                ]
                filled = False
                for sel in input_candidates:
                    try:
                        el = page.locator(sel).first
                        if el and el.count() > 0:
                            el.fill(url, timeout=5000)
                            filled = True
                            break
                    except Exception:
                        continue
                if not filled:
                    return None
                # 送信ボタン
                button_candidates = [
                    "button:has-text('要約')",
                    "button:has-text('Summarize')",
                    "button[type='submit']",
                    "button:has-text('生成')",
                    "button:has-text('Generate')",
                ]
                clicked = False
                for sel in button_candidates:
                    try:
                        b = page.locator(sel).first
                        if b and b.count() > 0:
                            b.click(timeout=5000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    return None
                # 結果が現れるのを待つ — best-effort で 60s 待つ
                deadline = time.time() + 60
                last_text = ""
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    # よくある結果コンテナ候補
                    result_sels = [
                        "[class*='result']",
                        "[class*='summary']",
                        "[class*='output']",
                        "article",
                        "main",
                    ]
                    for sel in result_sels:
                        try:
                            loc = page.locator(sel).first
                            if loc and loc.count() > 0:
                                txt = (loc.inner_text(timeout=2000) or "").strip()
                                if len(txt) > 200 and txt != last_text:
                                    last_text = txt
                        except Exception:
                            continue
                    if last_text and len(last_text) > 500:
                        break
                summary_text = last_text or None
            finally:
                browser.close()
    except Exception as e:
        print(f"⚠️ decopy.ai scrape failed ({video_id}): {e}")
        return None
    if summary_text and len(summary_text) > 100:
        # ノイズ削減: 連続空行をまとめる
        cleaned = re.sub(r"\n{3,}", "\n\n", summary_text).strip()
        return cleaned
    return None


# ---------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------

def _analyze_visual_with_claude(
    *,
    channel_id: str,
    video_title: str,
    competitor_title: str,
    image_paths: List[Path],
) -> Optional[Dict[str, Any]]:
    if not image_paths:
        return None
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    user = (
        f"競合チャンネル「{competitor_title}」の動画「{video_title}」のサムネと、"
        f"本編からランダムに抜き出したフレーム {max(0, len(image_paths) - 1)} 枚です。"
        "（1 枚目がサムネ、2 枚目以降が本編フレーム）\n\n"
        "ビジュアル面を分析し、以下の JSON を返してください:\n"
        "{\n"
        "  \"thumbnail_composition\": \"構図 / 視線誘導 / 主役の配置 ...\",\n"
        "  \"color_palette\": [\"#RRGGBB or 色名\", ...],\n"
        "  \"text_layout\": \"テキスト要素の配置 / フォント / 強調手法 ...\",\n"
        "  \"production_style\": \"テロップ多用 / カメラワーク / 編集テンポ など\",\n"
        "  \"visual_differentiation\": [\"他チャンネルと差別化されている視覚的ポイント\", ...],\n"
        "  \"thumbnail_to_video_consistency\": \"サムネと本編の世界観の一致度・落差\",\n"
        "  \"actionable_takeaways\": [\"自チャンネルで真似できる具体策\", ...]\n"
        "}\n"
        "JSON のみを返してください。"
    )
    return claude_client.call_claude_vision_json(
        system=(
            "あなたは YouTube のサムネ / 動画演出のアートディレクター。"
            "提示された画像を客観的に観察し、デザイン原則と訴求の観点で言語化する。"
        ),
        user_text=user,
        image_paths=image_paths,
        temperature=0.3,
        max_tokens=2000,
        channel_id=channel_id,
        purpose="competitor_video_visual",
    )


def _analyze_content_with_claude(
    *,
    channel_id: str,
    video_title: str,
    competitor_title: str,
    transcript: str,
    transcript_source: str,
    duration_seconds: Optional[int],
    views: Optional[int],
) -> Optional[Dict[str, Any]]:
    try:
        from pipeline import claude_client
    except Exception:
        return None
    if not claude_client.has_api_key():
        return None
    # Claude のコストを抑えるため、極端に長い字幕は先頭 8000 文字に切る
    snippet = transcript[:8000]
    meta_lines = [
        f"競合チャンネル: {competitor_title}",
        f"動画タイトル: {video_title}",
    ]
    if duration_seconds:
        meta_lines.append(f"尺: 約 {int(duration_seconds)} 秒")
    if views:
        meta_lines.append(f"再生数: {views:,}")
    meta_lines.append(f"テキストソース: {transcript_source}")
    user = (
        "\n".join(meta_lines)
        + "\n\n--- 字幕 / 要約テキスト ---\n"
        + snippet
        + "\n--- ここまで ---\n\n"
        + "上記の内容を分析し、以下の JSON を返してください:\n"
        "{\n"
        "  \"theme\": \"動画全体のテーマを 1〜2 文で\",\n"
        "  \"structure\": [\"導入\", \"展開1\", \"展開2\", \"オチ\" のような構成要素を順に],\n"
        "  \"time_allocation\": \"パートごとの尺配分の特徴（推測でよい）\",\n"
        "  \"punchline\": \"一番盛り上がるポイント / 視聴維持率が上がりそうな核\",\n"
        "  \"why_it_works\": [\"なぜこの動画が伸びていると推測できるか の仮説\", ...],\n"
        "  \"speaking_tone\": \"話し方 / 語尾 / テンション / キャラクター付け\",\n"
        "  \"hook_techniques\": [\"視聴者を引き込む具体テクニック（冒頭フック / 中盤の煽り / 視聴離脱を防ぐ仕掛け）\", ...],\n"
        "  \"actionable_takeaways\": [\"自チャンネルが取り入れるべき具体策\", ...]\n"
        "}\n"
        "JSON のみを返してください。"
    )
    return claude_client.call_claude_json(
        system=(
            "あなたは YouTube の編集 / 構成作家。"
            "提示された字幕や要約を読み、伸びる理由と再現可能なテクニックを言語化する。"
        ),
        user=user,
        temperature=0.3,
        max_tokens=2200,
        channel_id=channel_id,
        purpose="competitor_video_content",
    )


# ---------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------

def analyze_one_video(
    channel_id: str,
    competitor_id: str,
    video: Dict[str, Any],
    *,
    competitor_title: Optional[str] = None,
    frame_count: int = 3,
    keep_video_file: bool = False,
) -> Dict[str, Any]:
    """1 本の動画に対して visual + content 分析を行い、DB に保存。

    `video` は competitor_analyzer._fetch_video_details が返す dict 形式想定:
      { video_id, title, views, published_at, thumbnail_url, duration, ... }
    """
    video_id = (video.get("video_id") or "").strip()
    if not video_id:
        return {"ok": False, "error": "video_id missing"}

    video_title = str(video.get("title") or "(no title)")
    competitor_title = competitor_title or competitor_id

    cache_dir = _video_cache_dir(competitor_id, video_id)
    # 一時 DL 用ディレクトリ（フレーム抽出後に動画ファイルを削除する）
    work_dir = Path(tempfile.mkdtemp(prefix="cvideo_", dir=str(cache_dir)))

    errors: List[str] = []
    thumb_path: Optional[Path] = None
    frame_paths: List[Path] = []
    visual_insights: Optional[Dict[str, Any]] = None
    transcript: Optional[str] = None
    transcript_source = "none"
    content_insights: Optional[Dict[str, Any]] = None
    duration_seconds_int: Optional[int] = None

    try:
        # --- thumbnail (best-effort, yt-dlp 不要) ---
        try:
            thumb_path = _download_thumbnail(video_id, cache_dir)
        except Exception as e:
            errors.append(f"thumbnail: {e}")

        # --- yt-dlp 系（動画 DL + 字幕）---
        ytdlp = _ensure_yt_dlp()
        if not ytdlp:
            errors.append("yt-dlp not available")

        video_file: Optional[Path] = None
        if ytdlp:
            # 動画ダウンロード（最低画質）
            try:
                video_file = _download_video(ytdlp, video_id, work_dir)
                if not video_file:
                    errors.append("video download failed")
            except Exception as e:
                errors.append(f"download: {e}")

            # 字幕（動画 DL とは独立に成功しうる）
            try:
                transcript = _fetch_youtube_subtitles(ytdlp, video_id, work_dir)
                if transcript:
                    transcript_source = "yt-dlp-subs"
            except Exception as e:
                errors.append(f"subs: {e}")

        # --- ffmpeg フレーム抽出 ---
        ffmpeg = _ffmpeg_bin()
        ffprobe = _ffprobe_bin()
        try:
            if video_file and ffmpeg:
                duration: Optional[float] = None
                if ffprobe:
                    duration = _probe_duration_seconds(ffprobe, video_file)
                if duration:
                    duration_seconds_int = int(duration)
                frames = _extract_random_frames(
                    ffmpeg, video_file, cache_dir,
                    count=frame_count, duration_seconds=duration,
                )
                frame_paths = frames
            elif not ffmpeg:
                errors.append("ffmpeg not available")
        except Exception as e:
            errors.append(f"frame extract: {e}")
        finally:
            # **重要: 動画ファイルは必ず削除する（ディスク圧迫防止）**
            if not keep_video_file and video_file and video_file.exists():
                try:
                    video_file.unlink()
                except Exception as e:
                    print(f"  ⚠️ failed to delete video file ({video_file}): {e}")

        # --- decopy.ai fallback（字幕が取れなければ）---
        if not transcript:
            try:
                summary = _scrape_decopy_ai(video_id)
                if summary:
                    transcript = summary
                    transcript_source = "decopy.ai"
            except Exception as e:
                errors.append(f"decopy: {e}")

        # --- Claude vision ---
        image_paths: List[Path] = []
        if thumb_path:
            image_paths.append(thumb_path)
        image_paths.extend(frame_paths)
        if image_paths:
            try:
                visual_insights = _analyze_visual_with_claude(
                    channel_id=channel_id,
                    video_title=video_title,
                    competitor_title=competitor_title,
                    image_paths=image_paths,
                )
            except Exception as e:
                errors.append(f"claude visual: {e}")

        # --- Claude content ---
        if transcript:
            try:
                content_insights = _analyze_content_with_claude(
                    channel_id=channel_id,
                    video_title=video_title,
                    competitor_title=competitor_title,
                    transcript=transcript,
                    transcript_source=transcript_source,
                    duration_seconds=duration_seconds_int,
                    views=int(video.get("views") or 0) or None,
                )
            except Exception as e:
                errors.append(f"claude content: {e}")

    finally:
        # work_dir には字幕や残ファイルが残っているので削除
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

    transcript_excerpt = (transcript or "")[:2000] if transcript else None
    error_str = " | ".join(errors) if errors else None

    rec_id = analytics_store.upsert_competitor_video_analysis(
        channel_id=channel_id,
        competitor_id=competitor_id,
        video_id=video_id,
        video_title=video_title,
        published_at=video.get("published_at"),
        views=int(video.get("views") or 0) or None,
        duration_seconds=duration_seconds_int,
        thumbnail_path=str(thumb_path.relative_to(PROJECT_ROOT)) if thumb_path else None,
        frame_paths=[str(p.relative_to(PROJECT_ROOT)) for p in frame_paths],
        visual_insights=visual_insights,
        transcript_source=transcript_source,
        transcript_excerpt=transcript_excerpt,
        content_insights=content_insights,
        error=error_str,
    )

    return {
        "ok": True,
        "record_id": rec_id,
        "video_id": video_id,
        "video_title": video_title,
        "competitor_id": competitor_id,
        "thumbnail_path": str(thumb_path.relative_to(PROJECT_ROOT)) if thumb_path else None,
        "frame_count": len(frame_paths),
        "visual_insights": visual_insights,
        "transcript_source": transcript_source,
        "transcript_chars": len(transcript) if transcript else 0,
        "content_insights": content_insights,
        "errors": errors,
    }


def _top_videos_for_competitor(
    channel_id: str, competitor_id: str, top_n: int
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """既存の competitor_analyses から該当競合の最新スキャンを取り、TOP 動画を返す。"""
    rows = analytics_store.list_competitor_analyses(
        channel_id, competitor_id=competitor_id, limit=1
    )
    if not rows:
        return None, []
    row = rows[0]
    title = row.get("competitor_title")
    videos = row.get("top_videos_json") or []
    # views で再ソート（念のため）
    videos.sort(key=lambda v: int(v.get("views") or 0), reverse=True)
    return title, videos[:top_n]


def analyze_top_videos_for_competitor(
    channel_id: str,
    competitor_id: str,
    *,
    top_n: int = 3,
    frame_count: int = 3,
) -> Dict[str, Any]:
    """既存スキャンの TOP 動画を deep-analyze。

    competitor_analyses にスキャン結果が無ければ先に通常スキャンを促す（このメソッド単体では走らせない）。
    """
    title, videos = _top_videos_for_competitor(channel_id, competitor_id, top_n)
    if not videos:
        return {
            "ok": False,
            "competitor_id": competitor_id,
            "error": (
                "no competitor_analyses found — まず /api/competitors/{channel_id}/scan を"
                "実行してから video-analyze を呼んでください"
            ),
        }
    started = int(time.time())
    results: List[Dict[str, Any]] = []
    for v in videos:
        try:
            r = analyze_one_video(
                channel_id, competitor_id, v,
                competitor_title=title,
                frame_count=frame_count,
            )
        except Exception as e:
            r = {
                "ok": False,
                "video_id": v.get("video_id"),
                "error": str(e),
            }
        results.append(r)
    return {
        "ok": True,
        "channel_id": channel_id,
        "competitor_id": competitor_id,
        "competitor_title": title,
        "analyzed": len(results),
        "results": results,
        "started_at": started,
        "finished_at": int(time.time()),
    }


def analyze_top_videos_for_channel(
    channel_id: str,
    *,
    top_n_per_competitor: int = 3,
    max_competitors: int = 10,
    frame_count: int = 3,
) -> Dict[str, Any]:
    """登録済み全競合に対して deep-analyze をまとめて実行。"""
    from . import competitor_analyzer  # 遅延 import で循環回避
    competitor_ids = competitor_analyzer.list_competitors(channel_id)[:max_competitors]
    if not competitor_ids:
        return {
            "ok": True,
            "channel_id": channel_id,
            "competitors": [],
            "note": "no competitors registered",
        }
    started = int(time.time())
    out: List[Dict[str, Any]] = []
    for cid in competitor_ids:
        try:
            r = analyze_top_videos_for_competitor(
                channel_id, cid,
                top_n=top_n_per_competitor,
                frame_count=frame_count,
            )
        except Exception as e:
            r = {"ok": False, "competitor_id": cid, "error": str(e)}
        out.append({
            "competitor_id": cid,
            "ok": r.get("ok"),
            "analyzed": r.get("analyzed"),
            "error": r.get("error"),
        })
    return {
        "ok": True,
        "channel_id": channel_id,
        "started_at": started,
        "finished_at": int(time.time()),
        "competitors": out,
        "count": len(out),
    }
