"""
動画演出 (visual effects) レイヤ — シーン / セリフのムードに応じて
MoviePy のクリップに軽量な演出を追加する。

設計方針:
  - 既存の video_generator.FrameRenderer が返す `VideoClip` を受け取り、
    エフェクトを「重ね合わせ」「クリップ間トランジション」「クリップ内変形」
    の 3 系統で適用する。
  - レンダリング時間を爆発させないため、効果は安価な GPU/CPU 操作のみ:
      * クロスフェード / フェード
      * 軽い zoom-in / pan (Resize + Crop で実現)
      * 小振幅の振動 (画面シェイク = with_position + 周期関数)
      * 全画面 RGBA カラーオーバーレイ (赤フラッシュ / グリッチ tint)
      * ピクセル化エフェクト (短時間だけ低解像化 → 等倍リサイズ)
  - 内容に応じた自動選択:
      * scene の mood (`scary` 等) と本文中のキーワード (突然 / 驚き / 恐怖 等)
      * 動画内位置 (冒頭 / 末尾) を考慮
  - チャンネル JSON の `video_format.effects` セクションで ON/OFF とプリセット
    を切り替えられる。デフォルトはバランス重視の "balanced"。

公開 API:
  - load_effects_config(channel_format) -> EffectsConfig
  - decide_effect_plan(text, mood, *, position, total_count, cfg) -> List[Effect]
  - apply_clip_effects(clip, plan, *, fmt_size) -> VideoClip
  - build_transitions(clips, plan_per_clip, cfg) -> List[VideoClip]
      隣接クリップに crossfade などのトランジションを差し込み、
      最終的に concatenate するための新しいクリップリストを返す。

このモジュールは PIL と numpy しか追加で使わない。MoviePy は v2 系を想定。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    from moviepy import VideoClip, CompositeVideoClip, ColorClip
    from moviepy.video.fx import FadeIn, FadeOut, CrossFadeIn, CrossFadeOut, Resize
except Exception:  # pragma: no cover — runtime path covered by video_generator
    VideoClip = None  # type: ignore
    CompositeVideoClip = None  # type: ignore
    ColorClip = None  # type: ignore


# ---------------------------------------------------------------------
# Effect catalog
# ---------------------------------------------------------------------

@dataclass
class Effect:
    """1 シーンに適用するエフェクト指示。複数並べて重ねがけする。"""
    kind: str                  # "zoom_in" / "shake" / "flash" / "tint" / "pixelate" / "glitch_rgb" / "fade_in" / "fade_out"
    intensity: float = 1.0     # 0..1 の強さ（揺れ幅・ズーム率・ティント不透明度などに掛ける）
    duration: Optional[float] = None  # None ならクリップ全体
    color: Tuple[int, int, int] = (255, 0, 0)  # tint / flash の色
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

@dataclass
class EffectsConfig:
    enabled: bool = True
    preset: str = "balanced"          # off | minimal | balanced | horror
    allow_zoom: bool = True
    allow_shake: bool = True
    allow_flash: bool = True
    allow_tint: bool = True
    allow_pixelate: bool = True
    allow_glitch: bool = True
    allow_transitions: bool = True
    max_effects_per_scene: int = 2
    shake_max_px: int = 14            # 振動振幅 (1080p 基準)
    zoom_max: float = 0.06            # 1.06x までの拡大
    transition_duration: float = 0.35
    transition_min_gap: float = 6.0   # 同種トランジションを避けるための最小間隔(s)
    fade_in_first: bool = True
    fade_out_last: bool = True
    # --- ショート専用: 1.5〜2秒ごとの「寄り直し」で画面を止めない ---
    # 2026 のショートは 1.5〜2 秒ごとに視覚が変わらないと完視聴率が落ちる。
    # 1 行 = 3〜5 秒のセリフの中で、beat_interval ごとに寄り→戻しを繰り返し、
    # 疑似的なカット割りを作る（実カットを増やさないのでレンダー時間は据え置き）。
    short_beat_zoom: bool = True
    beat_interval: float = 1.8        # 寄り直しの周期(s)
    beat_zoom_max: float = 0.05       # 1 ビートあたりの最大寄り量 (1.0 → 1.05)


_DEFAULT_PRESETS = {
    "off": EffectsConfig(enabled=False),
    "minimal": EffectsConfig(
        preset="minimal",
        allow_shake=False, allow_flash=False, allow_pixelate=False,
        allow_glitch=False, allow_tint=False,
        max_effects_per_scene=1, zoom_max=0.03,
        transition_duration=0.25,
    ),
    # 科学 / 雑学解説向け: るーいのゆっくり科学 等の落ち着いた演出を踏襲。
    # 揺れ / フラッシュ系は完全 OFF、ズーム + 重要語の emphasis のみで魅せる。
    "science": EffectsConfig(
        preset="science",
        allow_shake=False, allow_flash=False, allow_pixelate=False,
        allow_glitch=False, allow_tint=False,
        max_effects_per_scene=1, zoom_max=0.04, shake_max_px=4,
        transition_duration=0.3,
    ),
    "balanced": EffectsConfig(preset="balanced"),
    "horror": EffectsConfig(
        preset="horror",
        shake_max_px=22, zoom_max=0.09, max_effects_per_scene=3,
        transition_duration=0.45,
    ),
}


def load_effects_config(channel_format: Optional[Dict[str, Any]]) -> EffectsConfig:
    """channel JSON の video_format.effects を読み込んで EffectsConfig を返す。"""
    raw = ((channel_format or {}).get("effects") or {})
    preset = str(raw.get("preset") or "balanced").lower()
    base = _DEFAULT_PRESETS.get(preset, _DEFAULT_PRESETS["balanced"])
    cfg = EffectsConfig(**base.__dict__)
    # 個別の上書き
    if "enabled" in raw:
        cfg.enabled = bool(raw["enabled"])
    if not cfg.enabled:
        return cfg
    overrides = {
        "allow_zoom", "allow_shake", "allow_flash", "allow_tint",
        "allow_pixelate", "allow_glitch", "allow_transitions",
        "fade_in_first", "fade_out_last",
    }
    for k in overrides | {"short_beat_zoom"}:
        if k in raw:
            setattr(cfg, k, bool(raw[k]))
    for k in ("max_effects_per_scene", "shake_max_px"):
        if k in raw:
            try:
                setattr(cfg, k, int(raw[k]))
            except Exception:
                pass
    for k in ("zoom_max", "transition_duration", "transition_min_gap",
              "beat_interval", "beat_zoom_max"):
        if k in raw:
            try:
                setattr(cfg, k, float(raw[k]))
            except Exception:
                pass
    cfg.preset = preset
    return cfg


# ---------------------------------------------------------------------
# Keyword sets for auto-selection
# ---------------------------------------------------------------------

_HORROR_WORDS = (
    "恐怖", "怖", "恐ろし", "戦慄", "悲鳴", "絶叫", "悪夢", "怪奇",
    "Keter", "ケテル", "暴走", "収容違反", "脱走", "暴れ", "襲", "殺",
    "死", "死亡", "腐", "血", "屍", "禁忌", "禁断", "呪",
)
_SHOCK_WORDS = (
    "突然", "いきなり", "驚", "瞬間", "刹那", "閃光", "爆発", "崩壊",
    "破壊", "衝撃", "現れた", "出現", "登場", "ばっ", "ドン", "ガッ",
)
_MYSTERY_WORDS = (
    "謎", "未解明", "正体", "実は", "真実", "正解", "明らかに", "暗号",
    "封印", "機密", "REDACTED", "DATA EXPUNGED", "削除", "禁止",
)
_FUNNY_WORDS = (
    "ｗ", "笑", "草", "可愛", "ほっこり", "癒し", "ふざけ", "おもしろ",
)
# 科学 / 雑学系で重要語にエンファシス（ゆっくり寄せ・図解強調）を当てるための語彙。
# るーいのゆっくり科学 等の人気科学チャンネルの分析から抽出。
_EMPHASIS_WORDS = (
    "つまり", "実は", "ポイント", "結論", "重要", "つまり", "なぜなら",
    "ということは", "答え", "正解", "原因", "理由", "ここがすごい",
    "驚き", "意外", "つまり", "言い換える",
)
# 「Before/After」「比較」「変化」を示唆するキーワード — 軽いスライドを当てる契機
_COMPARISON_WORDS = (
    "before", "after", "ビフォー", "アフター", "比べる", "比較",
    "違い", "変化", "前", "後",
)


def _contains_any(text: str, words: Tuple[str, ...]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(w.lower() in t for w in words)


def _normalize_mood(mood: Optional[str]) -> str:
    if not mood:
        return "calm"
    m = str(mood).strip().lower()
    return m


# ---------------------------------------------------------------------
# Effect plan selection
# ---------------------------------------------------------------------

def decide_effect_plan(
    text: str,
    mood: Optional[str],
    *,
    position: int,
    total_count: int,
    cfg: EffectsConfig,
    rng: Optional[random.Random] = None,
    is_short: bool = False,
) -> List[Effect]:
    """このシーンに乗せるエフェクトを返す。順序が重ねる順。

    プリセットが ``science`` / ``minimal`` のときは決して shake/flash/glitch を
    使わないよう、cfg.allow_* がそもそも False になっている前提。本関数では
    重要語にだけ軽い emphasis_pulse を当てる動きを増やす。

    ``is_short=True`` のときは、1 行の中で 1.5〜2 秒ごとに寄り直す ``beat_zoom``
    を必ず 1 つ足す（2026 ショート対策: 画面が数秒動かないと離脱する）。
    通常の ``zoom_in`` とは二重に掛けない（リサイズ 2 回分の描画コストを避ける）。
    """
    if not cfg.enabled:
        return []
    plan = _decide_effect_plan_base(
        text, mood, position=position, total_count=total_count, cfg=cfg, rng=rng)
    if is_short and cfg.allow_zoom and cfg.short_beat_zoom:
        plan = [e for e in plan if e.kind != "zoom_in"]
        beat = Effect(kind="beat_zoom", intensity=0.7,
                      extra={"interval": cfg.beat_interval})
        # フェードは端に残したいので、fade_in の直後に差し込む
        insert_at = 1 if (plan and plan[0].kind == "fade_in") else 0
        plan.insert(insert_at, beat)
    return plan


def _decide_effect_plan_base(
    text: str,
    mood: Optional[str],
    *,
    position: int,
    total_count: int,
    cfg: EffectsConfig,
    rng: Optional[random.Random] = None,
) -> List[Effect]:
    """内容ベースのエフェクト選択（従来ロジック）。"""
    if not cfg.enabled:
        return []
    rng = rng or random.Random()
    m = _normalize_mood(mood)
    plan: List[Effect] = []
    is_first = position == 0
    is_last = position == total_count - 1

    # 科学 / 雑学プリセットは別ロジックで「落ち着いた強調」を出す
    if cfg.preset in ("science", "minimal"):
        emphasis_hit = _contains_any(text, _EMPHASIS_WORDS)
        compare_hit = _contains_any(text, _COMPARISON_WORDS)
        if emphasis_hit:
            plan.append(Effect(kind="emphasis_pulse", intensity=0.5, duration=0.6))
        if compare_hit and cfg.allow_zoom:
            plan.append(Effect(kind="zoom_in", intensity=0.35))
        elif not plan and cfg.allow_zoom and rng.random() < 0.45:
            # 通常シーンに軽い ken-burns
            plan.append(Effect(kind="zoom_in", intensity=0.3))
        if is_first and cfg.fade_in_first:
            plan.insert(0, Effect(kind="fade_in", duration=0.5))
        if is_last and cfg.fade_out_last:
            plan.append(Effect(kind="fade_out", duration=0.8))
        # 同シーンでは emphasis + zoom の 2 種までに抑制
        cap = cfg.max_effects_per_scene + 2
        if len(plan) > cap:
            fades = [e for e in plan if e.kind in ("fade_in", "fade_out")]
            others = [e for e in plan if e.kind not in ("fade_in", "fade_out")]
            others = others[: cfg.max_effects_per_scene]
            plan = fades[:1] + others + fades[1:]
        return plan

    horror_hit = _contains_any(text, _HORROR_WORDS) or m in ("tense", "scary", "mysterious")
    shock_hit = _contains_any(text, _SHOCK_WORDS)
    mystery_hit = _contains_any(text, _MYSTERY_WORDS) or m == "mysterious"
    funny_hit = _contains_any(text, _FUNNY_WORDS) or m == "funny"
    emphasis_hit = _contains_any(text, _EMPHASIS_WORDS)

    # 1) 衝撃語があれば短い白フラッシュ → ピクセル化 → シェイク（強）
    if shock_hit and cfg.allow_flash:
        plan.append(Effect(kind="flash", intensity=0.55, duration=0.18,
                           color=(255, 255, 255)))
        if cfg.allow_pixelate:
            plan.append(Effect(kind="pixelate", intensity=0.6, duration=0.25))
        if cfg.allow_shake:
            plan.append(Effect(kind="shake", intensity=1.0,
                               duration=min(0.9, _safe_dur(text))))

    # 2) ホラー語 / 不気味系 → 赤ティント + 低振幅のシェイク
    if horror_hit:
        if cfg.allow_tint:
            plan.append(Effect(kind="tint", intensity=0.18,
                               color=(170, 0, 0)))
        if cfg.allow_shake and not any(e.kind == "shake" for e in plan):
            plan.append(Effect(kind="shake", intensity=0.45))

    # 3) ミステリー語 → 軽いズームイン + 短時間の RGB ずれ
    if mystery_hit:
        if cfg.allow_zoom:
            plan.append(Effect(kind="zoom_in", intensity=0.5))
        if cfg.allow_glitch and rng.random() < 0.45:
            plan.append(Effect(kind="glitch_rgb", intensity=0.5, duration=0.2))

    # 4) ふざけ系 → 軽い揺れ + ポップなティント
    if funny_hit:
        if cfg.allow_shake and not any(e.kind == "shake" for e in plan):
            plan.append(Effect(kind="shake", intensity=0.3))
        if cfg.allow_tint and not any(e.kind == "tint" for e in plan):
            plan.append(Effect(kind="tint", intensity=0.12,
                               color=(255, 240, 120)))

    # 5) 重要語が含まれていれば emphasis_pulse（科学系から学んだ控えめな強調）
    if emphasis_hit and not any(e.kind == "emphasis_pulse" for e in plan):
        plan.append(Effect(kind="emphasis_pulse", intensity=0.45, duration=0.5))

    # 6) ノイズが何も付かなかった通常シーンには軽い ken-burns ズームを 35% で
    if not plan and cfg.allow_zoom and rng.random() < 0.35:
        plan.append(Effect(kind="zoom_in", intensity=0.35))

    # 6) 端のフェード
    if is_first and cfg.fade_in_first:
        plan.insert(0, Effect(kind="fade_in", duration=0.5))
    if is_last and cfg.fade_out_last:
        plan.append(Effect(kind="fade_out", duration=0.8))

    # 同一シーンでの過剰積み防止
    if len(plan) > cfg.max_effects_per_scene + 2:  # +2 はフェード分の許容
        # フェード系を保持しつつ、それ以外を切り詰める
        fades = [e for e in plan if e.kind in ("fade_in", "fade_out")]
        others = [e for e in plan if e.kind not in ("fade_in", "fade_out")]
        others = others[: cfg.max_effects_per_scene]
        plan = fades[:1] + others + fades[1:]
    return plan


def _safe_dur(text: str) -> float:
    return max(0.8, min(2.5, len(text) / 18.0))


# ---------------------------------------------------------------------
# Effect application — implementations
# ---------------------------------------------------------------------

def _shake_position(intensity: float, base_px: int) -> Callable[[float], Tuple[int, int]]:
    """周期的なジッタ位置関数 (位置オフセット用)。"""
    amp = max(2, int(base_px * intensity))
    seed = random.random() * 100
    def pos(t: float) -> Tuple[int, int]:
        # 2 つの異なる周期のサインを合成 → 不規則感
        x = math.sin((t + seed) * 17.0) * amp + math.sin((t + seed) * 7.3) * amp * 0.5
        y = math.cos((t + seed) * 13.0) * amp + math.cos((t + seed) * 5.1) * amp * 0.5
        return (int(x), int(y))
    return pos


def _apply_shake(clip, intensity: float, *, fmt_size: Tuple[int, int], cfg: EffectsConfig):
    W, H = fmt_size
    pos_fn = _shake_position(intensity, cfg.shake_max_px)
    # CompositeVideoClip + with_position(t -> (W/2 + dx, H/2 + dy)) で実装。
    # ただし元クリップが画面全体を覆っているので、シェイクすると黒縁が出る。
    # → 元クリップを少しスケールアップ (1.04) してオーバースキャンで覆う。
    over = clip.with_effects([Resize(1.06)])
    over = over.with_position(lambda t: ("center" if False else
                                         (W // 2 - over.w // 2 + pos_fn(t)[0],
                                          H // 2 - over.h // 2 + pos_fn(t)[1])))
    return CompositeVideoClip([over], size=fmt_size).with_duration(clip.duration)


def _apply_zoom_in(clip, intensity: float, *, fmt_size: Tuple[int, int]):
    # クリップ全体を通じて 1.0 → 1.0 + zoom_max*intensity に拡大。
    # Resize(callable) は時間でフレームサイズが変動するので、隣接クリップとの
    # 連結時に「array size 1921 vs 1920」のような次元不一致を起こす。
    # CompositeVideoClip(size=fmt_size) で固定サイズに正規化する。
    W, H = fmt_size
    end_scale = 1.0 + 0.06 * max(0.3, intensity)
    dur = max(0.1, float(clip.duration or 1.0))
    def scale_fn(t: float) -> float:
        progress = min(1.0, t / dur)
        return 1.0 + (end_scale - 1.0) * progress
    over = clip.with_effects([Resize(scale_fn)])
    over = over.with_position(lambda t: (
        int(W / 2 - clip.w * scale_fn(t) / 2),
        int(H / 2 - clip.h * scale_fn(t) / 2),
    ))
    return CompositeVideoClip([over], size=fmt_size).with_duration(clip.duration)


def _apply_tint(clip, intensity: float, color: Tuple[int, int, int],
                *, fmt_size: Tuple[int, int]):
    """画面全体に半透明の単色を被せる。intensity は 0..0.5 程度を推奨。"""
    opacity = max(0.0, min(0.6, intensity))
    overlay = ColorClip(size=fmt_size, color=color, duration=clip.duration)
    overlay = overlay.with_opacity(opacity)
    return CompositeVideoClip([clip, overlay], size=fmt_size).with_duration(clip.duration)


def _apply_flash(clip, intensity: float, color: Tuple[int, int, int],
                 duration: float, *, fmt_size: Tuple[int, int]):
    """冒頭で短い色フラッシュ。fade 風に opacity が減衰する。"""
    dur = min(max(0.05, duration), float(clip.duration or duration))
    flash = ColorClip(size=fmt_size, color=color, duration=dur)
    peak = max(0.2, min(0.85, intensity))
    # 線形に opacity が peak → 0 になる
    def op_fn(t: float) -> float:
        progress = min(1.0, t / max(0.01, dur))
        return peak * (1.0 - progress)
    flash = flash.with_opacity(peak).with_effects([FadeOut(dur)])
    return CompositeVideoClip([clip, flash], size=fmt_size).with_duration(clip.duration)


def _apply_pixelate(clip, intensity: float, duration: float,
                    *, fmt_size: Tuple[int, int]):
    """冒頭 `duration` 秒間だけピクセル化（低解像 → 等倍 NEAREST）。"""
    W, H = fmt_size
    dur = min(max(0.1, duration), float(clip.duration or duration))
    block = max(4, int(40 * max(0.3, intensity)))  # ピクセルサイズ(px)

    def trans(get_frame, t):
        frame = get_frame(t)
        if t > dur:
            return frame
        # progress: t=0 → 1.0 (最大ピクセル化) , t=dur → 0 (元通り)
        progress = 1.0 - min(1.0, t / dur)
        cur_block = max(1, int(block * progress))
        if cur_block <= 1:
            return frame
        h, w = frame.shape[:2]
        small_w = max(1, w // cur_block)
        small_h = max(1, h // cur_block)
        # NumPy で素朴にダウン / アップサンプル
        ys = (np.arange(h) * small_h // h).astype(np.int32)
        xs = (np.arange(w) * small_w // w).astype(np.int32)
        # まず縮小
        downs = frame[
            (np.linspace(0, h - 1, small_h)).astype(np.int32)
        ][:, (np.linspace(0, w - 1, small_w)).astype(np.int32)]
        # 最近傍で拡大
        ups = downs[ys[:, None], xs[None, :]]
        return ups

    return clip.transform(trans, apply_to=[], keep_duration=True)


def _apply_glitch_rgb(clip, intensity: float, duration: float):
    """RGB ずれエフェクト — 冒頭の duration 秒だけ R/B チャンネルを左右にずらす。"""
    dur = max(0.05, duration)
    shift_max = max(2, int(12 * max(0.3, intensity)))

    def trans(get_frame, t):
        frame = get_frame(t)
        if t > dur:
            return frame
        out = frame.copy()
        if out.ndim != 3 or out.shape[2] < 3:
            return frame
        sx = shift_max  # ずらし量
        # R を左に, B を右に
        out[:, :-sx, 0] = frame[:, sx:, 0]
        out[:, sx:, 2] = frame[:, :-sx, 2]
        return out

    return clip.transform(trans, apply_to=[], keep_duration=True)


def _apply_emphasis_pulse(clip, intensity: float, duration: float,
                          *, fmt_size: Tuple[int, int]):
    """重要語の冒頭でフレーム全体をふわっと 1.0 → 1.0+δ → 1.0 にパルス。

    科学系で「ポイント」「実は」等の語が出た瞬間に視聴者の注意を引く控えめな演出。
    duration は約 0.3〜1.0s。intensity は 0..1（0.5 で δ=2.5%）。

    Resize(callable) を直接返すと時間でフレーム寸法が変わり、後続クリップとの
    concatenate で次元不一致 (例: 1921 vs 1920) を起こすため CompositeVideoClip
    で fmt_size に正規化する。
    """
    W, H = fmt_size
    dur = max(0.15, duration)
    peak = 1.0 + 0.05 * max(0.3, min(1.0, intensity))
    half = dur / 2.0

    def scale_fn(t: float) -> float:
        if t >= dur:
            return 1.0
        if t <= half:
            return 1.0 + (peak - 1.0) * (t / half)
        return 1.0 + (peak - 1.0) * (1.0 - (t - half) / half)

    over = clip.with_effects([Resize(scale_fn)])
    over = over.with_position(lambda t: (
        int(W / 2 - clip.w * scale_fn(t) / 2),
        int(H / 2 - clip.h * scale_fn(t) / 2),
    ))
    return CompositeVideoClip([over], size=fmt_size).with_duration(clip.duration)


def _apply_beat_zoom(clip, intensity: float, interval: float,
                     *, fmt_size: Tuple[int, int], cfg: EffectsConfig):
    """1.5〜2秒ごとに寄り直す「疑似カット割り」。

    各ビートの中で 1.0 → 1.0+amp までゆっくり寄り、ビートの切れ目でスッと戻る。
    実際にカットを増やさずに「画面が定期的に切り替わる」印象を作れるので、
    ショートの完視聴率対策として全行に薄く掛ける。

    偶数ビートと奇数ビートで寄りの向きを変え（寄る / 引く）、単調な反復に
    見えないようにしている。
    """
    W, H = fmt_size
    amp = max(0.01, min(0.08, cfg.beat_zoom_max * max(0.3, min(1.0, intensity))))
    iv = max(0.8, float(interval or 1.8))
    dur = max(0.1, float(clip.duration or 1.0))

    def scale_fn(t: float) -> float:
        beat = int(t // iv)
        p = (t % iv) / iv
        ease = 1 - (1 - p) ** 2  # ease-out: ビート頭の動きを大きく見せる
        if beat % 2 == 0:        # 寄る
            return 1.0 + amp * ease
        return 1.0 + amp * (1.0 - ease)  # 引く（1.0+amp から 1.0 へ）

    if dur <= iv * 0.6:
        # ビート 1 つ分にも満たない短いクリップは軽い寄りだけ
        return _apply_zoom_in(clip, intensity * 0.6, fmt_size=fmt_size)

    over = clip.with_effects([Resize(scale_fn)])
    over = over.with_position(lambda t: (
        int(W / 2 - clip.w * scale_fn(t) / 2),
        int(H / 2 - clip.h * scale_fn(t) / 2),
    ))
    return CompositeVideoClip([over], size=fmt_size).with_duration(clip.duration)


def _apply_fade_in(clip, duration: float):
    d = min(max(0.05, duration), float(clip.duration or duration))
    return clip.with_effects([FadeIn(d)])


def _apply_fade_out(clip, duration: float):
    d = min(max(0.05, duration), float(clip.duration or duration))
    return clip.with_effects([FadeOut(d)])


def apply_clip_effects(
    clip,
    plan: List[Effect],
    *,
    fmt_size: Tuple[int, int],
    cfg: EffectsConfig,
):
    """plan に従ってクリップにエフェクトを順番に重ねがけ。"""
    if not plan:
        return clip
    out = clip
    for eff in plan:
        try:
            if eff.kind == "zoom_in":
                out = _apply_zoom_in(out, eff.intensity, fmt_size=fmt_size)
            elif eff.kind == "beat_zoom":
                out = _apply_beat_zoom(out, eff.intensity,
                                       (eff.extra or {}).get("interval", cfg.beat_interval),
                                       fmt_size=fmt_size, cfg=cfg)
            elif eff.kind == "shake":
                out = _apply_shake(out, eff.intensity, fmt_size=fmt_size, cfg=cfg)
            elif eff.kind == "tint":
                out = _apply_tint(out, eff.intensity, eff.color, fmt_size=fmt_size)
            elif eff.kind == "flash":
                out = _apply_flash(out, eff.intensity, eff.color,
                                   duration=eff.duration or 0.18, fmt_size=fmt_size)
            elif eff.kind == "pixelate":
                out = _apply_pixelate(out, eff.intensity,
                                      duration=eff.duration or 0.3, fmt_size=fmt_size)
            elif eff.kind == "glitch_rgb":
                out = _apply_glitch_rgb(out, eff.intensity,
                                        duration=eff.duration or 0.2)
            elif eff.kind == "emphasis_pulse":
                out = _apply_emphasis_pulse(out, eff.intensity,
                                            duration=eff.duration or 0.5,
                                            fmt_size=fmt_size)
            elif eff.kind == "fade_in":
                out = _apply_fade_in(out, eff.duration or 0.5)
            elif eff.kind == "fade_out":
                out = _apply_fade_out(out, eff.duration or 0.8)
            # 未知の kind は黙って無視
        except Exception as e:
            print(f"  ⚠️ effect '{eff.kind}' failed: {e}")
    return out


# ---------------------------------------------------------------------
# Cross-clip transitions
# ---------------------------------------------------------------------

def maybe_add_crossfades(
    clips: List[Any],
    *,
    cfg: EffectsConfig,
    durations: List[float],
) -> List[Any]:
    """各クリップの冒頭に短い CrossFadeIn を入れる。

    隣接が音声も持っているケースを考慮して、トランジション長は短め (~0.35s)。
    最初のクリップにはフェードを掛けない（fade_in は plan で別途扱う）。
    """
    if not cfg.enabled or not cfg.allow_transitions or len(clips) < 2:
        return clips
    out_clips = [clips[0]]
    dur = max(0.1, min(cfg.transition_duration, 0.6))
    last_cf = -10.0  # 直前にトランジションを掛けた時刻
    t_running = float(durations[0] or 0.0)
    for i in range(1, len(clips)):
        c = clips[i]
        # 最小ギャップ未満ならスキップ
        if (t_running - last_cf) >= cfg.transition_min_gap:
            try:
                c = c.with_effects([CrossFadeIn(dur)])
                last_cf = t_running
            except Exception as e:
                print(f"  ⚠️ crossfade failed on clip {i}: {e}")
        out_clips.append(c)
        t_running += float(durations[i] or 0.0)
    return out_clips


# ---------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------

def summarize_plan(plans: List[List[Effect]]) -> Dict[str, int]:
    """全シーン分の plan を集計して、エフェクト種別ごとの登場回数を返す。"""
    cnt: Dict[str, int] = {}
    for p in plans:
        for e in p:
            cnt[e.kind] = cnt.get(e.kind, 0) + 1
    return cnt
