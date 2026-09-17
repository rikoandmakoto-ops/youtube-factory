"""
ChannelManager — チャンネルプロファイルの読み込み・管理・パイプライン連携

Usage:
    from channels import ChannelManager

    cm = ChannelManager()
    ch = cm.get("daily-science")
    char_config = ch.char_config()      # video_generator用 CHAR_CONFIG形式
    defaults = ch.defaults               # speed, target_duration, etc.
    seeds = ch.theme_seeds               # シナリオ自動生成用テーマ候補
"""

import copy
import json
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

from .video_format import VideoFormat
from .config_validation import validate_channel_config, ConfigIssue

# ============================================================
# Image acquisition mode
# ============================================================

IMAGE_MODES = ("generate", "collect", "mix")
DEFAULT_IMAGE_MODE = "generate"

DEFAULT_IMAGE_COLLECT_SETTINGS: Dict[str, Any] = {
    "provider": "auto",          # "auto" | "pixabay" | "pexels" | "unsplash" | "google_cse"
    "safe_search": True,
    "license_filter": "cc",      # "cc" | "any"
    "max_per_query": 5,
    "attribution_template": "出典: {source}",
    "mix_strategy": "heuristic", # "heuristic" | "always_collect" | "always_generate"
}


def normalize_image_mode(value: Optional[str]) -> str:
    """Coerce any incoming value to a valid image_mode (defaults to generate)."""
    if not value:
        return DEFAULT_IMAGE_MODE
    v = str(value).strip().lower()
    return v if v in IMAGE_MODES else DEFAULT_IMAGE_MODE


# ============================================================
# theme_seeds の正規化
# ============================================================

def normalize_theme_seeds(seeds: Any, channel_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """theme_seeds を「全件 dict・title 必須」に揃える。

    受け付ける形:
        {"title": "...", "angle": "..."}   … 正
        "..."                              … 文字列 → {"title": "...", "angle": ""}
    捨てる形（声を出して捨てる）:
        title が空の dict、dict でも str でもないもの

    消費側（generator / autopilot / run_*.py / trend_fetcher / comment_demand …）
    は 10 箇所以上あり、全部が `s.get("title")` 前提。ここで揃えれば
    設定の書き方（文字列で列挙）で機能が黙って死ぬことがなくなる。
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(seeds, list):
        if seeds:
            print(f"  ⚠️ [{channel_id or '?'}] theme_seeds はリストである必要があります"
                  f"（{type(seeds).__name__} を無視）")
        return out
    dropped = 0
    coerced = 0
    for s in seeds:
        if isinstance(s, str):
            t = s.strip()
            if not t:
                dropped += 1
                continue
            out.append({"title": t, "angle": ""})
            coerced += 1
        elif isinstance(s, dict):
            t = str(s.get("title") or "").strip()
            if not t:
                dropped += 1
                continue
            item = dict(s)
            item["title"] = t
            item["angle"] = str(item.get("angle") or "")
            out.append(item)
        else:
            dropped += 1
    if coerced or dropped:
        print(f"  ⚠️ [{channel_id or '?'}] theme_seeds: 文字列 {coerced} 件を dict に正規化、"
              f"不正 {dropped} 件を無視（JSON 側も dict 形式に直してください）")
    return out


# ============================================================
# Channel Profile dataclass
# ============================================================

@dataclass
class ChannelProfile:
    """1チャンネル分のプロファイル"""
    id: str
    name: str
    concept: str
    style: str  # "yukkuri" or "monologue"
    youtube_channel_id: Optional[str]
    characters: Dict[str, Any]
    thumbnail_template: Dict[str, Any]
    defaults: Dict[str, Any]
    content_policy: Dict[str, Any]
    theme_seeds: List[Dict[str, str]] = field(default_factory=list)
    video_format: VideoFormat = field(default_factory=VideoFormat)
    publish_settings: Dict[str, Any] = field(default_factory=dict)
    voice_style: Dict[str, Any] = field(default_factory=dict)
    image_mode: str = DEFAULT_IMAGE_MODE
    image_collect: Dict[str, Any] = field(default_factory=dict)
    tiktok: Dict[str, Any] = field(default_factory=dict)
    _raw: Dict = field(default_factory=dict, repr=False)

    # ── Pipeline integration helpers ──

    def char_config(self) -> Dict[str, Dict]:
        """
        video_generator.py の CHAR_CONFIG 互換形式に変換。
        色はタプル化、expressionsはリスト維持。
        """
        config = {}
        for name, cfg in self.characters.items():
            entry = {
                "side": cfg.get("side", "left"),
                "speaker_id": cfg["speaker_id"],
                "text_color": tuple(cfg.get("text_color", [255, 255, 255])),
            }
            if "expressions" in cfg:
                entry["expressions"] = cfg["expressions"]
            if "role" in cfg:
                entry["role"] = cfg["role"]
            if "appearance" in cfg:
                entry["appearance"] = cfg["appearance"]
            # Optional asset-folder override (assets/characters/<dir>/<expr>.png)
            if "dir" in cfg:
                entry["dir"] = cfg["dir"]
            if "slug" in cfg:
                entry["slug"] = cfg["slug"]
            config[name] = entry
        return config

    def narrator_config(self) -> Optional[Dict]:
        """モノローグスタイル用ナレーター設定を返す"""
        if self.style != "monologue":
            return None
        narrator = self.characters.get("narrator", {})
        return {
            "speaker_id": narrator.get("speaker_id", 13),
            "text_color": tuple(narrator.get("text_color", [240, 240, 240])),
            "role": narrator.get("role", "ナレーター"),
        }

    def get_speed(self) -> float:
        return self.defaults.get("speed", 1.3)

    def get_target_duration(self) -> int:
        """目標尺（秒）。デフォルト 720秒 = 12分目安（フル動画、最低10分=600秒を割らない）"""
        return self.defaults.get("target_duration", 720)

    def get_bg_type(self) -> str:
        return self.defaults.get("bg_type", "auto")

    def get_bg_video_path(self) -> Optional[str]:
        """Background image/video path from defaults.

        Returns the configured `bg_path`, resolved against the repo root if it
        is a relative path (so callers can pass it straight through to the
        video generator, which checks `Path.exists()` directly).
        """
        bg_rel = self.defaults.get("bg_path")
        if not bg_rel:
            return None
        p = Path(bg_rel)
        if not p.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent.parent
            p = repo_root / bg_rel
        return str(p) if p.exists() else None

    def get_use_illustrations(self) -> bool:
        return self.defaults.get("use_illustrations", True)

    def get_image_mode(self) -> str:
        """Image acquisition mode: 'generate' | 'collect' | 'mix' (default: 'generate')."""
        return normalize_image_mode(self.image_mode)

    def get_image_collect_settings(self) -> Dict[str, Any]:
        """Merged collect settings: channel overrides on top of defaults.

        The pipeline always gets a fully populated dict, so it never has to
        worry about missing keys (e.g. attribution_template).
        """
        merged = dict(DEFAULT_IMAGE_COLLECT_SETTINGS)
        merged.update(self.image_collect or {})
        return merged

    def get_hashtags(self) -> List[str]:
        return self.defaults.get("hashtags", [])

    def get_category(self) -> str:
        return self.defaults.get("category", "27")

    def get_upload_tags(
        self,
        extra: Optional[List[str]] = None,
        is_short: bool = False,
        max_chars: int = 450,
        title: Optional[str] = None,
    ) -> List[str]:
        """videos.insert の snippet.tags に渡すタグ列。

        検索用の広いセット（video_format.youtube.default_tags）と表示用の
        少数（defaults.hashtags）をマージする。以前は defaults.hashtags だけを
        使っていたため 4〜6 個しかタグが付かず、default_tags が死に設定だった。

        `title` を渡すと、その動画固有の固有名詞（SCP番号・ポケモン名・妖怪名
        など）をタグ末尾に足す。2026-08-23 時点では全動画がチャンネル共通の
        15〜17 個の同一タグだけで投稿されており（450文字の枠に対し実使用は
        90〜110文字）、ロングテール検索に一切引っかかっていなかった。
        各チャンネルの title_style が「固有名を必ず出す（検索性が高い）」と
        指定しているのに、その固有名がタグ側に渡っていなかった。

        YouTube のタグは合計 500 文字が上限（区切り文字込み）なので余裕をみて
        450 文字で打ち切る。'#' は除去（タグに含めると検索対象がずれる）。
        """
        vf_tags = list(self.video_format.youtube.default_tags or [])
        hash_tags = list(self.get_hashtags() or [])
        head = ["Shorts"] if is_short else []

        title_tags: List[str] = []
        if title:
            try:
                from pipeline.hashtag_optimizer import _extract_title_keywords
                title_tags = _extract_title_keywords(title, max_keywords=6)
            except Exception:
                title_tags = []

        ordered: List[str] = []
        seen = set()
        for tag in head + vf_tags + hash_tags + list(extra or []) + title_tags:
            t = str(tag or "").lstrip("#＃").strip()
            if not t or t.lower() in seen:
                continue
            seen.add(t.lower())
            ordered.append(t)

        out: List[str] = []
        total = 0
        for t in ordered:
            cost = len(t) + 1  # カンマ区切り1文字分
            if total + cost > max_chars:
                break
            out.append(t)
            total += cost
        return out

    def illustration_style_config(self) -> Dict[str, Any]:
        """イラスト生成スタイル設定（DALL-E + フレーム）を dict で返す。

        video_generator は dict 経由で受け取るので、ここで dict 化しておく。
        """
        ill = self.video_format.illustration_style
        return {
            "style": ill.style,
            "format": ill.format,
            "art_style": ill.art_style,
            "background": ill.background,
            "include_characters": ill.include_characters,
            "frame_style": ill.frame_style,
            "extra_prompt": ill.extra_prompt,
            "allow_text_labels": ill.allow_text_labels,
            "allow_frame": ill.allow_frame,
        }

    def thumb_config(self) -> Dict[str, Any]:
        """サムネイルテンプレート設定"""
        t = self.thumbnail_template
        return {
            "badge_text": t.get("badge_text", ""),
            "badge_color": tuple(t.get("badge_color", [220, 40, 40])),
            "hook_color": tuple(t.get("hook_color", [255, 255, 50])),
            "subtitle_color": tuple(t.get("subtitle_color", [80, 220, 255])),
            "bg_tone": t.get("bg_tone", "dark"),
        }

    def policy_guidelines(self) -> List[str]:
        """コンテンツポリシーのガイドライン一覧"""
        return self.content_policy.get("guidelines", [])

    def policy_avoid(self) -> List[str]:
        """避けるべきコンテンツ一覧"""
        return self.content_policy.get("avoid", [])

    def get_publish_settings(self) -> Dict[str, Any]:
        """公開時のデフォルト設定（ペア公開・自動公開・遅延・テンプレなど）。

        欠損時はサーバ側のデフォルトを返すので呼び出し側は安心してアクセスできる。
        """
        ps = dict(self.publish_settings or {})
        ps.setdefault("auto_publish", False)
        ps.setdefault("default_privacy", "public")
        ps.setdefault("short_delay_minutes", 10)
        ps.setdefault(
            "short_description_template",
            "▼ 関連動画 / Related video\n"
            "🎬 フル解説はこちら！\n"
            "{main_url}\n\n"
            "{original_description}",
        )
        # 自動公開の投稿先。"youtube" / "tiktok" の組み合わせ。
        ps.setdefault("publish_targets", ["youtube"])
        return ps

    def get_tiktok_settings(self) -> Dict[str, Any]:
        """TikTok 投稿のデフォルト設定（接続状態とは独立した投稿挙動）。

        欠損時はサーバ側のデフォルトを返すので呼び出し側は安心してアクセスできる。
        """
        tt = dict(self.tiktok or {})
        tt.setdefault("enabled", False)            # TikTok 投稿を使うか
        tt.setdefault("privacy_level", "SELF_ONLY")  # 未審査アプリは SELF_ONLY 強制
        tt.setdefault("disable_comment", False)
        tt.setdefault("disable_duet", False)
        tt.setdefault("disable_stitch", False)
        tt.setdefault("extra_hashtags", [])        # YouTube タグに加えて付与
        return tt

    def wants_tiktok_post(self) -> bool:
        """自動公開時に TikTok へも投稿すべきか。"""
        targets = self.get_publish_settings().get("publish_targets") or []
        return "tiktok" in targets and self.get_tiktok_settings().get("enabled", False)

    def wants_youtube_post(self) -> bool:
        """自動公開時に YouTube へ投稿すべきか（デフォルト True）。"""
        targets = self.get_publish_settings().get("publish_targets") or ["youtube"]
        return "youtube" in targets

    def to_dict(self) -> Dict:
        """API用JSON変換"""
        vf = self.video_format
        return {
            "id": self.id,
            "name": self.name,
            "concept": self.concept,
            "short_series_name": self._raw.get("short_series_name", ""),
            "main_title_prefix": self._raw.get("main_title_prefix", ""),
            "next_video_genre_hint": self._raw.get("next_video_genre_hint", ""),
            "style": self.style,
            "youtube_channel_id": self.youtube_channel_id,
            "character_names": list(self.characters.keys()),
            "characters": self.characters,
            "defaults": self.defaults,
            "content_policy": {
                "tone": self.content_policy.get("tone", "friendly"),
                "age_rating": self.content_policy.get("age_rating", "all_ages"),
                "guidelines": self.content_policy.get("guidelines", []),
                "avoid": self.content_policy.get("avoid", []),
            },
            "theme_seed_count": len(self.theme_seeds),
            "theme_seeds": self.theme_seeds,
            "thumbnail_template": self.thumbnail_template,
            "publish_settings": self.get_publish_settings(),
            "description_template": self._raw.get("description_template", {}),
            "video_format": vf.to_dict(),
            "youtube": {
                "channel_id": vf.youtube.channel_id,
                "default_tags": vf.youtube.default_tags,
                "default_category": vf.youtube.default_category,
                "privacy_status": vf.youtube.privacy_status,
                "upload_schedule": vf.youtube.upload_schedule,
                "playlist_id": vf.youtube.playlist_id,
            },
            "analytics": {
                "enabled": vf.analytics.enabled,
                "performance_threshold": vf.analytics.performance_threshold,
                "auto_adjust": vf.analytics.auto_adjust,
            },
            "tiktok": self.get_tiktok_settings(),
        }


# ============================================================
# ChannelManager
# ============================================================

class ChannelManager:
    """
    data/channels/*.json を読み込み、チャンネルプロファイルを管理。
    Singleton的に使う想定。
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            # backend/channels/ → ../../data/channels/
            self._data_dir = Path(__file__).parent.parent.parent / "data" / "channels"
        self._channels: Dict[str, ChannelProfile] = {}
        self._config_issues: List[ConfigIssue] = []
        # 読み込んだ時点のファイル更新時刻（ns）。get() で外部編集を検知するのに使う。
        self._mtimes: Dict[str, int] = {}
        # ディスク変更で読み直したあとに呼ぶフック（2026-09-17）。
        # autopilot のスケジューラ再登録に使う。
        self._reload_hooks: List[Any] = []
        self._hook_running: Set[str] = set()
        # 書き込みの直列化（同一プロセス内）。autopilot のテーマ取り出しと
        # UI の設定更新が同時に走っても read-modify-write が交錯しない。
        self._write_lock = threading.RLock()
        self.reload()

    # ------------------------------------------------------------
    # 読み込み
    # ------------------------------------------------------------

    def _path_of(self, channel_id: str) -> Path:
        return self._data_dir / f"{channel_id}.json"

    @staticmethod
    def _mtime_ns(path: Path) -> Optional[int]:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def _build_profile(self, raw: Dict[str, Any]) -> ChannelProfile:
        """生 JSON から ChannelProfile を組み立てる（設定の形の吸収もここ）。"""
        # VideoFormat: video_format セクションがあればパース、なければdefaultsからマージ
        vf = VideoFormat.from_dict(raw.get("video_format", {}))
        vf.merge_channel_defaults(raw.get("defaults", {}))
        return ChannelProfile(
            id=raw["id"],
            name=raw["name"],
            concept=raw["concept"],
            style=raw.get("style", "yukkuri"),
            youtube_channel_id=raw.get("youtube_channel_id"),
            characters=raw.get("characters", {}),
            thumbnail_template=raw.get("thumbnail_template", {}),
            defaults=raw.get("defaults", {}),
            content_policy=raw.get("content_policy", {}),
            # 【2026-09-12】素の文字列の seed を {"title": ...} に正規化する。
            # 09-11 に daily-science 6件 / scp-lab 3件が文字列で入っており、
            # `s.get("title")` で suggest_themes / _pick_seed_avoiding_past が落ち、
            # 呼び出し元の握り潰しで genre_blacklist が無効化された。読み込みで
            # 形を揃えれば、消費側 10 箇所すべてが dict 前提のままで壊れない。
            theme_seeds=normalize_theme_seeds(raw.get("theme_seeds", []), raw.get("id")),
            video_format=vf,
            publish_settings=raw.get("publish_settings", {}),
            voice_style=raw.get("voice_style", {}),
            image_mode=normalize_image_mode(raw.get("image_mode")),
            image_collect=raw.get("image_collect", {}),
            tiktok=raw.get("tiktok", {}),
            _raw=raw,
        )

    def _load_file(self, f: Path, *, verbose: bool = True) -> Optional[ChannelProfile]:
        """1ファイルを読み込んでメモリに載せる。壊れていれば None（既存はそのまま）。"""
        try:
            mtime = self._mtime_ns(f)
            raw = json.loads(f.read_text(encoding="utf-8"))
            profile = self._build_profile(raw)
        except Exception as e:
            print(f"  ❌ Failed to load {f.name}: {e}")
            return None
        self._channels[profile.id] = profile
        if mtime is not None:
            self._mtimes[profile.id] = mtime
        if verbose:
            print(f"  📺 Channel loaded: {profile.id} ({profile.name})")
        # 設定整合性チェック（autopilot有効 × 非公開 などの矛盾を検知）
        self._config_issues = [i for i in self._config_issues if i.channel_id != profile.id]
        for issue in validate_channel_config(raw, channel_id=profile.id):
            self._config_issues.append(issue)
            if verbose:
                icon = "❌" if issue.is_error else "⚠️"
                print(f"  {icon} CONFIG {issue.level.upper()} [{profile.id}]: {issue.message}")
                if issue.fix:
                    print(f"      → 対処: {issue.fix}")
        return profile

    def reload(self):
        """チャンネルJSONを再読み込み"""
        self._channels.clear()
        self._config_issues = []
        self._mtimes.clear()
        if not self._data_dir.exists():
            print(f"⚠️ Channel data dir not found: {self._data_dir}")
            return

        for f in sorted(self._data_dir.glob("*.json")):
            self._load_file(f)

        print(f"✅ {len(self._channels)} channels loaded")
        n_err = sum(1 for i in self._config_issues if i.is_error)
        n_warn = len(self._config_issues) - n_err
        if n_err or n_warn:
            print(f"🩺 Channel config check: {n_err} error(s), {n_warn} warning(s)")

    def _refresh_if_changed(self, channel_id: str) -> None:
        """ディスクのファイルがメモリより新しければ、そのチャンネルだけ読み直す。

        【2026-09-12】稼働中の backend は起動時の JSON をメモリに抱えたまま動く。
        指揮者（別プロセス）が data/channels/*.json を直しても、backend は古い
        写しで動き続け、次に何かを保存した瞬間に古い写しで上書きしていた
        （「設定変更が消える」の真因の半分。もう半分は _save_autopilot が
        メモリを土台にしていたこと → patch_channel_file）。
        get() のたびに stat する（数µs）。読み直しは変わったときだけ。
        """
        f = self._path_of(channel_id)
        cur = self._mtime_ns(f)
        if cur is None or cur == self._mtimes.get(channel_id):
            return
        print(f"🔄 Channel config changed on disk — reloading {channel_id}.json")
        self._load_file(f, verbose=False)
        # 【2026-09-17】読み直しただけでは APScheduler のジョブは変わらない。
        # 指揮者がディスクへ書いた autopilot.enabled / schedule.times は、
        # 従来は backend 再起動まで一切効かなかった（2ch-matome が 09-13 以降
        # enabled=true のまま3日間ぶん発火しなかった真因）。
        # 読み直しの直後にフックを呼び、スケジューラを同じ内容へ揃える。
        self._fire_reload_hooks(channel_id)

    # ------------------------------------------------------------
    # リロードフック — ディスク変更を検知して読み直した直後に呼ばれる
    # ------------------------------------------------------------

    def add_reload_hook(self, fn: "Callable[[str], None]") -> None:
        """ディスク由来の再読み込み後に channel_id を渡して呼ぶ関数を登録する。

        同一関数の二重登録は無視する（restore_all が複数回走っても増えない）。
        """
        for existing in self._reload_hooks:
            if existing is fn:
                return
        self._reload_hooks.append(fn)

    def _fire_reload_hooks(self, channel_id: str) -> None:
        if not self._reload_hooks:
            return
        # フックの中で cm.get() が呼ばれても、_mtimes は _load_file で
        # 更新済みなので _refresh_if_changed は即 return する。
        # それでも取りこぼしがないよう再入だけは明示的に止める。
        if channel_id in self._hook_running:
            return
        self._hook_running.add(channel_id)
        try:
            for fn in list(self._reload_hooks):
                try:
                    fn(channel_id)
                except Exception as e:
                    print(f"⚠️ reload hook failed for {channel_id}: {e}")
        finally:
            self._hook_running.discard(channel_id)

    def get(self, channel_id: str) -> Optional[ChannelProfile]:
        if channel_id in self._channels:
            self._refresh_if_changed(channel_id)
        return self._channels.get(channel_id)

    def list_channels(self) -> List[ChannelProfile]:
        for cid in list(self._channels):
            self._refresh_if_changed(cid)
        return list(self._channels.values())

    def list_ids(self) -> List[str]:
        return list(self._channels.keys())

    def get_by_style(self, style: str) -> List[ChannelProfile]:
        return [ch for ch in self._channels.values() if ch.style == style]

    def config_issues(self) -> List[ConfigIssue]:
        """直近の reload で検出した設定整合性の問題一覧。"""
        return list(self._config_issues)

    def has_config_errors(self) -> bool:
        return any(i.is_error for i in self._config_issues)

    # ------------------------------------------------------------
    # 書き込み — ここ以外で data/channels/*.json を書かない
    # ------------------------------------------------------------

    def read_raw(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """ディスク上の**現在の**生 JSON。壊れていればメモリの写し（声を出す）。"""
        file_path = self._path_of(channel_id)
        if file_path.exists():
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                # ディスクが読めない/壊れているときだけメモリの写しに退避する。
                # 黙って古い値で上書きしないよう、必ず声を出す。
                print(f"⚠️ read_raw: {file_path.name} を読めないので "
                      f"メモリ上の写しを土台にします — {e}")
        ch = self._channels.get(channel_id)
        return copy.deepcopy(ch._raw) if ch else None

    def _atomic_write(self, file_path: Path, raw: Dict[str, Any]) -> None:
        """tmp に書いて rename。途中で落ちても半端な JSON を残さない。"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = file_path.with_name(file_path.name + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, file_path)

    def patch_channel_file(
        self,
        channel_id: str,
        mutate: Callable[[Dict[str, Any]], Any],
        *,
        reason: str = "",
    ) -> Optional[Dict[str, Any]]:
        """ディスクの現在の JSON を土台に `mutate(raw)` を適用して書き戻す。

        【2026-09-12】data/channels/*.json への書き込みはすべてここを通す。

        「autopilot がテーマを1件取り出して保存する」たびに、メモリ上の古い
        写しを丸ごと書き戻していたため、指揮者がディスク側に入れた設定変更
        （title_rules / theme_blacklist / genre_blacklist …）が**次の発火で
        黙って消えていた**。update_channel は 09-10 に直したが、autopilot の
        `_save_autopilot` は ch._raw.copy() のままだった。書き込み経路が
        4つ（update_channel / _save_autopilot / api_phase2 の config・persona /
        effects_researcher）あり、1つ直しても残りが同じ事故を起こす構造なので、
        read-modify-write を1関数に集約する。

        - 読み込み → mutate → 書き込み を `_write_lock` の中で行う（同一プロセス）
        - 土台は必ずディスク（メモリの写しは読めないときの退避のみ）
        - 書き込みは tmp + os.replace（アトミック）
        - 書いた直後にそのチャンネルだけ読み直す（全 reload の副作用を避ける）

        `mutate` は raw を in-place で書き換える。戻り値は無視する。
        戻り値: 書き込んだ raw（チャンネルが無ければ None）。
        """
        with self._write_lock:
            if channel_id not in self._channels and not self._path_of(channel_id).exists():
                return None
            raw = self.read_raw(channel_id)
            if raw is None:
                return None
            mutate(raw)
            file_path = self._path_of(channel_id)
            self._atomic_write(file_path, raw)
            self._load_file(file_path, verbose=False)
            if reason:
                print(f"💾 {channel_id}.json updated ({reason})")
            return raw

    def set_section(self, channel_id: str, key: str, value: Any, *,
                    reason: str = "") -> Optional[Dict[str, Any]]:
        """トップレベルの1キーだけ差し替える（他のキーはディスクの値を維持）。"""
        def _m(raw: Dict[str, Any]) -> None:
            raw[key] = value
        return self.patch_channel_file(channel_id, _m, reason=reason or f"set {key}")

    def add_channel(self, profile_data: Dict) -> ChannelProfile:
        """新チャンネルをJSONファイルとして保存し、メモリにも追加"""
        channel_id = profile_data["id"]
        with self._write_lock:
            self._atomic_write(self._path_of(channel_id), profile_data)
        self.reload()
        return self._channels[channel_id]

    def update_channel(self, channel_id: str, updates: Dict) -> Optional[ChannelProfile]:
        """チャンネル設定を更新してJSONに保存

        【2026-09-10 修正】土台を **ディスクの現在の中身**にした。

        以前は `ch._raw`（＝最後に reload した時点のメモリ上の写し）を土台に
        ファイルを丸ごと書き直していた。稼働中の backend は起動時のJSONを
        メモリに抱えたままなので、指揮者がディスク側を直した後にこの経路が
        1回でも走ると、**更新キー以外の全ての変更が黙って巻き戻る**。
        09-08 に「バックエンドが設定を上書きして消す」として観測された症状が
        これで、原因は再起動忘れではなく、この関数が古い写しを正としていたこと。

        【2026-09-12】実体を patch_channel_file に移した（他の書き込み経路と同じ
        ロック・アトミック書き込み・部分再読込を使う）。
        """
        if channel_id not in self._channels:
            return None

        def _m(raw: Dict[str, Any]) -> None:
            # トップレベルフィールド更新
            for key in ("name", "concept", "style", "youtube_channel_id",
                        "characters", "thumbnail_template", "defaults",
                        "content_policy", "theme_seeds", "publish_settings",
                        "voice_style", "image_collect", "tiktok"):
                if key in updates:
                    raw[key] = updates[key]
            if "image_mode" in updates:
                raw["image_mode"] = normalize_image_mode(updates["image_mode"])
            # video_format 更新（部分更新対応）
            if "video_format" in updates:
                existing_vf = raw.get("video_format", {})
                for section, vals in updates["video_format"].items():
                    if isinstance(vals, dict):
                        if section not in existing_vf:
                            existing_vf[section] = {}
                        existing_vf[section].update(vals)
                    else:
                        existing_vf[section] = vals
                raw["video_format"] = existing_vf

        self.patch_channel_file(channel_id, _m, reason="update_channel")
        return self._channels.get(channel_id)

    def remove_channel(self, channel_id: str) -> bool:
        """チャンネルJSONを削除"""
        file_path = self._path_of(channel_id)
        with self._write_lock:
            if file_path.exists():
                file_path.unlink()
                self._channels.pop(channel_id, None)
                self._mtimes.pop(channel_id, None)
                return True
        return False
