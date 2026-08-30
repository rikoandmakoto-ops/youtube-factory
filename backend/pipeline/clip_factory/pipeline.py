"""切り抜きチャンネルのオーケストレーション。

    在庫探索 → 元動画を1本選ぶ → エンジンで切り抜き生成 → メタ生成
    → （任意で）YouTube 投稿 → 消化済み区間を記録

エンジンは差し替え可能（local / noimos / viral）。noimos が使えない環境では
clip.fallback_engine に自動で落ちるので、autopilot は止まらない。

════════════════════════════════════════════════════════════════════
■ 1チャンネルに2系統が同居する（2026-08-30〜）
════════════════════════════════════════════════════════════════════

`clip-lab` は国内切り抜き（許諾済み YouTube 素材 / engine=local）と
海外バイラル翻訳（Reddit 素材 / engine=viral）を **同じチャンネルの別スロット**
で回す。17:45 が国内、20:45 が海外（autopilot の time slot に `engine` を書く）。

そのため素材の探索はエンジンで振り分ける（`_collect_sources(engine=...)`）。
混ぜると local エンジンが Reddit 素材（台本も日本語字幕も無い）を掴んで必ず
失敗するし、viral エンジンが2時間の生配信を掴んで Whisper に流し込む。
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import sources as src_mod
from .engines import get_engine
from .engines.noimos import NoimosUnavailable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

# 切り抜きの出力先。**~/Desktop の外**に置くのが重要。
#
# レンダリングは Homebrew の ffmpeg（/opt/homebrew/bin/ffmpeg）が行うが、これは
# backend とは別のバイナリなので TCC の許可を独自に要求する。launchd 配下では
# 許可ダイアログを出せないため、~/Desktop 配下へ書こうとすると **エラーも出さずに
# 永久にブロックする**（実測 2026-08-21: CPU 0.02 秒のまま 15 分以上ハング）。
# 素材の読み出しは ~/Movies のミラーで解決しているので、書き出しも同様に
# TCC 保護外へ逃がす。`clip.output_dir` で上書きできる。
DEFAULT_OUT_BASE = Path(
    os.environ.get("CLIP_OUTPUT_BASE") or (Path.home() / "Movies" / "yf_clips")
)

#: 海外バイラル翻訳のエンジン名。素材の探索先とメタの上書きがこの名前で切り替わる。
VIRAL_ENGINE = "viral"


def load_channel_raw(channel_id: str) -> Dict[str, Any]:
    path = CHANNELS_DIR / f"{channel_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"channel JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _source_channel_ids(clip_cfg: Dict[str, Any]) -> List[str]:
    return [str(s.get("channel_id")) for s in (clip_cfg.get("sources") or []) if s.get("channel_id")]


def _source_roots(clip_cfg: Dict[str, Any]) -> Optional[List[Path]]:
    """clip.source_roots があればそれを使う（TCC 回避ミラーの指定用）。"""
    roots = clip_cfg.get("source_roots")
    if not roots:
        return None
    return [Path(str(r)).expanduser() for r in roots if str(r).strip()]


def _source_weights(clip_cfg: Dict[str, Any]) -> Dict[str, float]:
    return {
        str(s.get("channel_id")): float(s.get("weight") or 1.0)
        for s in (clip_cfg.get("sources") or []) if s.get("channel_id")
    }


def _credit_name(clip_cfg: Dict[str, Any], source: "src_mod.SourceVideo") -> str:
    if source.credit_name:
        return str(source.credit_name)
    for s in clip_cfg.get("sources") or []:
        if s.get("channel_id") == source.source_channel_id:
            name = s.get("credit_name")
            if name:
                return str(name)
    try:
        return str(load_channel_raw(source.source_channel_id).get("name")
                   or source.source_channel_id)
    except Exception:
        return source.source_channel_id


def _external_weights(clip_cfg: Dict[str, Any]) -> Dict[str, float]:
    """allowlist の weight を外部素材のキー形式で返す（pick_source 用）。"""
    from .external import external_channel_key

    cfg = clip_cfg.get("external_sources") or {}
    out: Dict[str, float] = {}
    for entry in cfg.get("allowlist_channels") or []:
        cid = str(entry.get("channel_id") or "").strip()
        if cid:
            out[external_channel_key(cid)] = float(entry.get("weight") or 1.0)
    return out


def _collect_sources(clip_cfg: Dict[str, Any], *, resolve_youtube_ids: bool = True,
                     engine: Optional[str] = None):
    """素材を集める。**エンジンで探索先を振り分ける**。

    `clip-lab` は国内切り抜きと海外バイラルが同居しているので、両方を1つの
    リストに混ぜると `pick_source` が engine に合わない素材を選びうる。

        engine == "viral" … 海外バイラル素材だけ
        それ以外           … 自社在庫 + 許諾済み外部素材だけ
        engine is None     … 従来どおり全部（UI の在庫一覧など）
    """
    from . import acquisition as acq
    from . import external as ext_mod
    from . import viral_sources as vs

    want_viral = engine is None or engine == VIRAL_ENGINE
    want_local = engine is None or engine != VIRAL_ENGINE

    source_ids = _source_channel_ids(clip_cfg)
    found = []
    if want_local and source_ids:
        print(f"📦 自社在庫を探索: {', '.join(source_ids)}")
        found.extend(src_mod.discover_sources(
            source_ids, resolve_youtube_ids=resolve_youtube_ids,
            source_roots=_source_roots(clip_cfg),
        ))

    if want_local and acq.is_enabled(clip_cfg):
        cfg = clip_cfg.get("external_sources") or {}
        print("🌐 許諾済み外部チャンネルを探索…")
        found.extend(ext_mod.discover_external_sources(
            clip_cfg, limit=int(cfg.get("prepare_limit") or 3),
        ))

    if want_viral and vs.is_enabled(clip_cfg):
        cfg = vs.cfg(clip_cfg)
        print("🔥 海外バイラル素材を探索…")
        found.extend(vs.discover_viral_sources(
            clip_cfg, limit=int(cfg.get("prepare_limit") or 5),
        ))
    return found


def _recoverable_errors() -> tuple:
    """「その素材だけ諦めて次へ」で済む例外。

    権利・内容ゲートで落ちるのは想定内の分岐であって、パイプラインの故障では
    ない。ここに載っているものだけが次の素材へ進み、それ以外は従来どおり
    ジョブごと失敗させる（黙って作り続けない）。
    """
    from .engines.viral import ViralClipRejected
    from .translate import TranslationRejected

    return (ViralClipRejected, TranslationRejected)


def _record_rejection(source: "src_mod.SourceVideo", reason: str) -> None:
    """不採用を調達履歴に残す（翌日も同じ素材を掴まないため）。"""
    try:
        from .engines.viral import record_rejection
        record_rejection(source, reason)
    except Exception:
        pass


def build_title(hook: str, channel_raw: Dict[str, Any],
                *, overrides: Optional[Dict[str, Any]] = None) -> str:
    """フック文からショートのタイトルを作る。

    YouTube のタイトルに改行は入れられない（API が弾く）。フック文は帯の中で
    2行に割る前提で作られるので、改行や連続空白が混ざりうる。ここで必ず潰す。

    `overrides` は海外バイラル枠のように、同じチャンネルでも別のハッシュタグを
    付けたい系統向け（`clip.viral_sources.metadata`）。
    """
    overrides = overrides or {}
    tags = str(overrides.get("short_title_hashtags")
               or (channel_raw.get("defaults") or {}).get("short_title_hashtags")
               or "#shorts")
    clean = re.sub(r"\s+", " ", str(hook or "")).strip()
    title = f"{clean} {tags}".strip()
    return title[:100]


def build_description(
    channel_raw: Dict[str, Any],
    *,
    source_url: Optional[str],
    source_title: str,
    credit_name: str,
    attribution: str = "",
    overrides: Optional[Dict[str, Any]] = None,
) -> str:
    """説明欄を作る。

    出典（元動画URL・元チャンネル名）は**必ず**入れる。許諾を得ている切り抜きでも、
    出典が無いと視聴者からも権利者からも無断転載と区別が付かない。

    `overrides` に `short_intro` / `short_hashtags` があればそちらを使う
    （海外バイラル枠は「▼ この切り抜きの本編はこちら」では意味が通らないため）。
    """
    tpl = {**(channel_raw.get("description_template") or {}),
           **{k: v for k, v in (overrides or {}).items() if v}}
    body = str(tpl.get("short_intro") or "")
    body = body.format(
        source_url=source_url or "（本編URLはプロフィールから）",
        source_title=source_title,
        credit_name=credit_name,
    )
    hashtags = str(tpl.get("short_hashtags") or "")
    parts = [body]
    if attribution:
        parts.append(attribution)
    parts.append(hashtags)
    return "\n\n".join(p for p in parts if p.strip()).strip()


def list_available_sources(channel_id: str = "clip-lab",
                           *, include_external: bool = False) -> List[Dict[str, Any]]:
    """切り抜き可能な在庫を一覧する（UI / 運用確認用）。

    Args:
        include_external: 外部素材も見る。YouTube API と yt-dlp を叩くので
            数十秒かかる。UI の一覧は既定 off のまま即返す。
    """
    channel_raw = load_channel_raw(channel_id)
    clip_cfg = channel_raw.get("clip") or {}
    if include_external:
        found = _collect_sources(clip_cfg, resolve_youtube_ids=False)
    else:
        found = src_mod.discover_sources(
            _source_channel_ids(clip_cfg), resolve_youtube_ids=False,
            source_roots=_source_roots(clip_cfg),
        )
    per_video = int(clip_cfg.get("clips_per_video") or 3)
    return [
        {**s.to_dict(), "remaining_clips": max(0, per_video - len(s.used_segments))}
        for s in found
    ]


def generate_clip(
    channel_id: str = "clip-lab",
    *,
    count: int = 1,
    source_title: Optional[str] = None,
    out_dir: Optional[Path] = None,
    upload: bool = False,
    privacy: Optional[str] = None,
    dry_run: bool = False,
    engine: Optional[str] = None,
) -> Dict[str, Any]:
    """切り抜きを count 本作る（既定は1本）。

    Args:
        source_title: 指定すると、その元動画から切り抜く（手動運転用）。
        engine: `clip.engine` を上書きする。`clip-lab` は国内切り抜き（local）と
            海外バイラル翻訳（viral）が同居しているので、呼び出し側が
            「今どちらの系統を回すか」を明示する。autopilot の time slot と
            `run_viral_clip.py` がこれを渡す。
    """
    from . import acquisition as acq
    from . import viral_sources as vs

    channel_raw = load_channel_raw(channel_id)
    clip_cfg = channel_raw.get("clip") or {}
    engine_name = str(engine or clip_cfg.get("engine") or "local").strip().lower()
    is_viral = engine_name == VIRAL_ENGINE

    source_ids = _source_channel_ids(clip_cfg)
    if is_viral and not vs.is_enabled(clip_cfg):
        return {"ok": False, "engine": engine_name,
                "error": (f"{channel_id}.clip.viral_sources.enabled が false です"
                          "（海外バイラル枠が無効）")}
    if not is_viral and not source_ids and not acq.is_enabled(clip_cfg):
        return {"ok": False, "engine": engine_name,
                "error": (f"{channel_id}.clip.sources が空で、external_sources も "
                          "無効です")}

    found = _collect_sources(clip_cfg, engine=engine_name)
    if not found:
        return {"ok": False, "error": (
            "切り抜ける元動画が見つかりません。"
            "自社在庫はローカル出力フォルダを、許諾済み外部素材は許諾文言"
            "（permission_phrases）を、海外バイラル素材は調達経路"
            "（REDDIT_CLIENT_ID / 内容ゲート）を確認してください")}

    # 海外バイラルは1投稿＝1本（同じ Reddit 投稿を切り直さない）。国内切り抜きの
    # clips_per_video（長尺1本から5本）をそのまま使うと意味が変わる。
    viral_out = vs.output_cfg(clip_cfg)
    per_video = int((viral_out.get("clips_per_video") if is_viral else None)
                    or (1 if is_viral else 0)
                    or clip_cfg.get("clips_per_video") or 3)
    if source_title:
        source = next((s for s in found if s.title == source_title), None)
        if source is None:
            return {"ok": False, "error": f"指定の元動画が見つかりません: {source_title}"}
    else:
        weights = {**_source_weights(clip_cfg), **_external_weights(clip_cfg)}
        source = src_mod.pick_source(found, weights=weights,
                                     max_clips_per_video=per_video)
    if source is None:
        return {"ok": False, "error": "全ての元動画が切り抜き済みです（clips_per_video を上げるか元動画を増やしてください）"}

    print(f"🎞️ 元動画: [{source.source_channel_id}] {source.title}")
    print(f"   {source.video_path or source.source_url()}  "
          f"({source.duration:.0f}s / 既出 {len(source.used_segments)}本)")
    if source.is_external:
        print(f"   🔏 許諾: {source.permission.get('reason')}")

    # 1本の元動画から取り過ぎない。clips_per_video を超えると同じ動画ばかりになる
    remaining = max(0, per_video - len(source.used_segments))
    if remaining and count > remaining:
        print(f"   ℹ️ この元動画の残り枠は {remaining} 本なので count を絞ります")
        count = remaining

    # 外部素材の元チャンネルは自社の channel JSON に存在しない（話者色などは無し）
    try:
        source_channel_raw = load_channel_raw(source.source_channel_id)
    except FileNotFoundError:
        source_channel_raw = {}
    if out_dir:
        out_base = Path(out_dir)
    elif clip_cfg.get("output_dir"):
        out_base = Path(str(clip_cfg["output_dir"])).expanduser()
    else:
        out_base = DEFAULT_OUT_BASE
    out_base.mkdir(parents=True, exist_ok=True)

    # viral 枠で noimos に落ちると素材の前提（フルの長尺動画）が合わないので、
    # フォールバックは同じ viral に固定する。
    fallback = (VIRAL_ENGINE if is_viral
                else str(clip_cfg.get("fallback_engine") or "local"))
    clips: List[Dict[str, Any]] = []
    used_engine = engine_name

    # 素材ごとのゲート落ちは「失敗」ではなく「次を見る」。海外バイラルは
    # 内容ゲート（NSFW・禁止語・Claude の安全判定）で落ちるのが常態なので、
    # 1本目で諦めるとその日の投稿が丸ごと消える。
    attempts = [source]
    if is_viral and not source_title:
        limit = int(viral_out.get("max_source_attempts")
                    or clip_cfg.get("max_source_attempts") or 4)
        attempts += [s for s in found if s is not source][: max(0, limit - 1)]

    rejected: List[Dict[str, str]] = []
    last_error: Optional[str] = None
    for attempt in attempts:
        try:
            clips = get_engine(engine_name)(
                source=attempt, clip_cfg=clip_cfg, channel_raw=channel_raw,
                source_channel_raw=source_channel_raw, out_dir=out_base,
                count=count, dry_run=dry_run,
            )
            source = attempt
            break
        except NoimosUnavailable as e:
            if fallback and fallback != engine_name:
                print(f"⚠️ NoimosAI を使えないため {fallback} エンジンに切り替えます: {e}")
                used_engine = fallback
                clips = get_engine(fallback)(
                    source=attempt, clip_cfg=clip_cfg, channel_raw=channel_raw,
                    source_channel_raw=source_channel_raw, out_dir=out_base,
                    count=count, dry_run=dry_run,
                )
                source = attempt
                break
            return {"ok": False, "error": str(e), "engine": engine_name}
        except _recoverable_errors() as e:
            print(f"  ⏭️ この素材は見送ります: {e}")
            last_error = str(e)
            rejected.append({"title": attempt.title, "reason": str(e)})
            _record_rejection(attempt, str(e))
            continue
        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "error": f"{engine_name} エンジンが失敗: {e}",
                    "engine": engine_name}
    else:
        return {"ok": False, "engine": engine_name, "rejected": rejected,
                "error": ("候補の素材がすべてゲートで不採用になりました"
                          f"（{len(rejected)} 本）。最後の理由: {last_error}")}

    credit = _credit_name(clip_cfg, source)
    source_url = source.source_url()
    privacy = privacy or (channel_raw.get("publish_settings") or {}).get("default_privacy") or "public"

    # 海外バイラル枠だけタイトル・説明欄・タグを差し替える（同居先 clip-lab の
    # 「本編はこちら」テンプレは Reddit 投稿には合わない）。
    meta_over = vs.metadata_cfg(clip_cfg) if is_viral else {}
    yt_cfg = ((channel_raw.get("video_format") or {}).get("youtube") or {})

    results: List[Dict[str, Any]] = []
    for clip in clips:
        hook = clip.get("hook") or source.video_title
        meta = {
            **clip,
            "channel_id": channel_id,
            "source_channel_id": source.source_channel_id,
            "source_title": source.title,
            "source_video_title": source.video_title,
            "source_url": source_url,
            "credit_name": credit,
            "engine": used_engine,
            "is_external": source.is_external,
            "permission": source.permission,
            "title": build_title(hook, channel_raw, overrides=meta_over),
            "description": build_description(
                channel_raw, source_url=source_url,
                source_title=source.video_title, credit_name=credit,
                attribution=source.attribution, overrides=meta_over,
            ),
            "tags": meta_over.get("tags") or yt_cfg.get("default_tags"),
            "category_id": (meta_over.get("category_id")
                            or yt_cfg.get("default_category") or "24"),
            # エンジンが force_privacy を返したらそれを優先する。海外バイラルの
            # 目視レビュー運用（content_gate.require_manual_review）で、
            # チャンネル既定が public でも private で上げるための口。
            # 2026-08-30 の運用決定でレビューは無し＝ここは None のまま流れ、
            # チャンネル既定の public で上がる。
            "privacy": clip.get("force_privacy") or privacy,
            "upload": None,
        }

        if upload and not dry_run and meta.get("video_path"):
            meta["upload"] = _upload(meta, channel_raw)

        if not dry_run and meta.get("video_path"):
            src_mod.record_clip(
                source, clip.get("segment") or {},
                clip_id=clip.get("clip_id") or "",
                upload=meta.get("upload"),
            )
        results.append(meta)

    meta_path = out_base / f"_clip_meta_{int(time.time())}.json"
    meta_path.write_text(
        json.dumps({"source": source.to_dict(), "clips": results},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"📝 meta: {meta_path}")

    return {
        "ok": True,
        "channel_id": channel_id,
        "engine": used_engine,
        "source": source.to_dict(),
        "clips": results,
        "rejected": rejected,
        "meta_path": str(meta_path),
    }


def _upload(meta: Dict[str, Any], channel_raw: Dict[str, Any]) -> Dict[str, Any]:
    """YouTube へショートとして投稿する。"""
    try:
        from pipeline import youtube_uploader as yu  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"youtube_uploader を読み込めません: {e}"}
    try:
        res = yu.upload_video(
            video_path=meta["video_path"],
            title=meta["title"],
            description=meta["description"],
            tags=meta.get("tags"),
            thumbnail_path=meta.get("thumbnail_path"),
            privacy=meta.get("privacy") or "public",
            category_id=meta.get("category_id") or "24",
            is_short=True,
            channel_id=channel_raw.get("youtube_channel_id") or None,
            auth_channel_id=meta["channel_id"],
        )
        print(f"  ✅ uploaded: {res.get('url')}")
        return res
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}
