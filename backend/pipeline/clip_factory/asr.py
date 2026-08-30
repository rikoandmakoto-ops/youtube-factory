"""海外動画の音声書き起こし（Whisper）。

clip-lab（国内素材）は YouTube の自動字幕を落として `captions.py` で行タイムラインに
していたが、Reddit / TikTok の転載動画に字幕は付いてこない。そこで **手元で
音声認識する**。ネットワークもサードパーティ API も使わないので、autopilot から
無人で回せるしコストもゼロ。

════════════════════════════════════════════════════════════════════
■ バックエンド
════════════════════════════════════════════════════════════════════

    faster-whisper … 既定。CTranslate2 実装で CPU でも実用速度が出る
    openai-whisper … 予備。PyTorch 実装。入っていれば使う

どちらも **ローカルで動く OSS モデル**であって OpenAI の API ではない
（台本・テキスト生成を OpenAI API に依存させない、という運用ルールに抵触しない）。
翻訳とフック文の生成は Claude が担当する（`translate.py`）。

════════════════════════════════════════════════════════════════════
■ 無音動画の扱い
════════════════════════════════════════════════════════════════════

r/funny 系には **音声が無い / BGM だけ** の投稿が普通にある。その場合
`segments` は空で返る。呼び出し側は「字幕なしで作る（フック文だけ）」か
「その素材を捨てる」かを選べるよう、`speech_ratio` と `segments` の両方を返す。
無音を無理に文字起こしすると Whisper は幻聴（"Thank you for watching!" など
学習データ由来の定型文）を出すので、**VAD で無音を落としてから**渡している。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

#: Whisper が無音区間に対して出しがちな幻聴。落とさないと字幕に混ざる。
HALLUCINATION_PATTERNS = (
    r"(?i)^\s*(thank you|thanks) for watching[.!]*\s*$",
    r"(?i)^\s*please subscribe[.!]*\s*$",
    r"(?i)^\s*subscribe to my channel[.!]*\s*$",
    r"(?i)^\s*\[?(music|applause|laughter|silence)\]?[.!]*\s*$",
    r"(?i)^\s*you\s*$",
    r"^\s*[♪♫\-–—.。、\s]*$",
)

_HALLUCINATION_RES = [re.compile(p) for p in HALLUCINATION_PATTERNS]


@dataclass
class SpeechSegment:
    """書き起こしの1区間（元言語のまま）。"""

    index: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "start": round(self.start, 3),
                "end": round(self.end, 3), "text": self.text}


@dataclass
class Transcript:
    """1本分の書き起こし。"""

    language: str
    segments: List[SpeechSegment] = field(default_factory=list)
    duration: float = 0.0
    backend: str = ""

    @property
    def speech_ratio(self) -> float:
        """尺のうち発話が占める割合。無音動画の判定に使う。"""
        if self.duration <= 0:
            return 0.0
        return min(1.0, sum(s.duration for s in self.segments) / self.duration)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "backend": self.backend,
            "duration": round(self.duration, 2),
            "speech_ratio": round(self.speech_ratio, 3),
            "segments": [s.to_dict() for s in self.segments],
        }


class AsrUnavailable(RuntimeError):
    """Whisper のバックエンドが1つも使えない。"""


# ---------------------------------------------------------------------
# 音声の切り出し
# ---------------------------------------------------------------------

def _ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def extract_audio(
    video_path: Path | str,
    *,
    start: float = 0.0,
    duration: Optional[float] = None,
    out_path: Optional[Path] = None,
) -> Optional[Path]:
    """16kHz モノラル WAV を書き出す。音声トラックが無ければ None。

    Whisper に mp4 を直接渡しても内部で ffmpeg を呼ぶだけなので、
    区間を切る都合もあってここで明示的に落とす。
    """
    out_path = Path(out_path or Path(tempfile.mkdtemp(prefix="asr_")) / "audio.wav")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(video_path)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1024:
        # 音声トラックが無い動画は珍しくない（GIF 由来の投稿など）
        return None
    return out_path


def has_audio(video_path: Path | str) -> bool:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=120,
    )
    return "audio" in (proc.stdout or "")


# ---------------------------------------------------------------------
# バックエンド
# ---------------------------------------------------------------------

def available_backend() -> Optional[str]:
    try:
        import faster_whisper  # noqa: F401
        return "faster_whisper"
    except Exception:
        pass
    try:
        import whisper  # noqa: F401
        return "whisper"
    except Exception:
        pass
    return None


_MODEL_CACHE: Dict[str, Any] = {}


def _load_faster_whisper(model_size: str, compute_type: str):
    key = f"fw:{model_size}:{compute_type}"
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel  # type: ignore
        print(f"  🧠 Whisper モデルを読み込み中: {model_size} ({compute_type})")
        _MODEL_CACHE[key] = WhisperModel(
            model_size, device="cpu", compute_type=compute_type)
    return _MODEL_CACHE[key]


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if any(r.match(t) for r in _HALLUCINATION_RES):
        return ""
    return t


def transcribe(
    video_path: Path | str,
    *,
    start: float = 0.0,
    duration: Optional[float] = None,
    model_size: str = "small",
    compute_type: str = "int8",
    language: Optional[str] = None,
    beam_size: int = 5,
) -> Transcript:
    """動画（または区間）を書き起こす。

    Args:
        language: 元言語を決め打ちする場合に指定（"en" など）。None なら自動判定。
            海外バイラルは英語が大半だが、スペイン語・ポルトガル語も混ざるので
            既定は自動判定にしてある。

    Raises:
        AsrUnavailable: Whisper のバックエンドが入っていない。
    """
    backend = available_backend()
    if not backend:
        raise AsrUnavailable(
            "Whisper が入っていません。`python3 -m pip install faster-whisper` を"
            "実行してください（ローカル実行・API 不要）")

    video_path = Path(video_path)
    if not has_audio(video_path):
        return Transcript(language="", segments=[], duration=duration or 0.0,
                          backend=backend)

    wav = extract_audio(video_path, start=start, duration=duration)
    if wav is None:
        return Transcript(language="", segments=[], duration=duration or 0.0,
                          backend=backend)

    try:
        if backend == "faster_whisper":
            model = _load_faster_whisper(model_size, compute_type)
            raw, info = model.transcribe(
                str(wav),
                language=language,
                beam_size=beam_size,
                # 無音を先に落とす。これが無いと無音区間に幻聴が乗る
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
                condition_on_previous_text=False,
            )
            lang = str(getattr(info, "language", "") or "")
            rows = [(float(s.start), float(s.end), str(s.text)) for s in raw]
        else:
            import whisper  # type: ignore
            key = f"w:{model_size}"
            if key not in _MODEL_CACHE:
                _MODEL_CACHE[key] = whisper.load_model(model_size)
            res = _MODEL_CACHE[key].transcribe(str(wav), language=language)
            lang = str(res.get("language") or "")
            rows = [(float(s["start"]), float(s["end"]), str(s["text"]))
                    for s in (res.get("segments") or [])]
    finally:
        try:
            shutil.rmtree(wav.parent, ignore_errors=True)
        except Exception:
            pass

    segments: List[SpeechSegment] = []
    for start_s, end_s, text in rows:
        clean = _clean(text)
        if not clean:
            continue
        segments.append(SpeechSegment(
            index=len(segments), start=start_s, end=max(end_s, start_s + 0.3),
            text=clean,
        ))

    total = duration if duration is not None else (
        segments[-1].end if segments else 0.0)
    tr = Transcript(language=lang, segments=segments, duration=total or 0.0,
                    backend=backend)
    print(f"  🎙️ 書き起こし: {len(segments)} 区間 / lang={lang or '不明'} "
          f"/ 発話率 {tr.speech_ratio:.0%}")
    return tr


# ---------------------------------------------------------------------
# 区間選定の補助
# ---------------------------------------------------------------------

def densest_window(
    transcript: Transcript,
    *,
    window_sec: float,
    step_sec: float = 1.0,
) -> Optional[tuple]:
    """発話が最も詰まっている窓を返す。

    元動画が目標尺より長いときに「どこを切るか」を決めるための素朴な指標。
    バイラル動画は 60 秒未満が大半なのでほとんど出番が無いが、たまに
    3 分のコンピレーションが混ざるのでその保険。

    Returns:
        (start, end) または発話が無ければ None。
    """
    if not transcript.segments or transcript.duration <= 0:
        return None
    if transcript.duration <= window_sec:
        return (0.0, transcript.duration)

    best = (0.0, window_sec)
    best_score = -1.0
    t = 0.0
    while t + window_sec <= transcript.duration:
        end = t + window_sec
        speech = sum(
            max(0.0, min(s.end, end) - max(s.start, t))
            for s in transcript.segments
        )
        if speech > best_score:
            best_score = speech
            best = (t, end)
        t += step_sec
    return best


def slice_segments(
    transcript: Transcript, start: float, end: float,
) -> List[SpeechSegment]:
    """指定区間に掛かる発話だけを取り出し、区間の外側を切り詰める。"""
    out: List[SpeechSegment] = []
    for s in transcript.segments:
        if s.end <= start or s.start >= end:
            continue
        out.append(SpeechSegment(
            index=len(out),
            start=max(s.start, start),
            end=min(s.end, end),
            text=s.text,
        ))
    return out
