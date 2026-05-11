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

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .video_format import VideoFormat

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

    def get_hashtags(self) -> List[str]:
        return self.defaults.get("hashtags", [])

    def get_category(self) -> str:
        return self.defaults.get("category", "27")

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
        return ps

    def to_dict(self) -> Dict:
        """API用JSON変換"""
        vf = self.video_format
        return {
            "id": self.id,
            "name": self.name,
            "concept": self.concept,
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
        self.reload()

    def reload(self):
        """チャンネルJSONを再読み込み"""
        self._channels.clear()
        if not self._data_dir.exists():
            print(f"⚠️ Channel data dir not found: {self._data_dir}")
            return

        for f in sorted(self._data_dir.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                # VideoFormat: video_format セクションがあればパース、なければdefaultsからマージ
                vf = VideoFormat.from_dict(raw.get("video_format", {}))
                vf.merge_channel_defaults(raw.get("defaults", {}))
                profile = ChannelProfile(
                    id=raw["id"],
                    name=raw["name"],
                    concept=raw["concept"],
                    style=raw.get("style", "yukkuri"),
                    youtube_channel_id=raw.get("youtube_channel_id"),
                    characters=raw.get("characters", {}),
                    thumbnail_template=raw.get("thumbnail_template", {}),
                    defaults=raw.get("defaults", {}),
                    content_policy=raw.get("content_policy", {}),
                    theme_seeds=raw.get("theme_seeds", []),
                    video_format=vf,
                    publish_settings=raw.get("publish_settings", {}),
                    _raw=raw,
                )
                self._channels[profile.id] = profile
                print(f"  📺 Channel loaded: {profile.id} ({profile.name})")
            except Exception as e:
                print(f"  ❌ Failed to load {f.name}: {e}")

        print(f"✅ {len(self._channels)} channels loaded")

    def get(self, channel_id: str) -> Optional[ChannelProfile]:
        return self._channels.get(channel_id)

    def list_channels(self) -> List[ChannelProfile]:
        return list(self._channels.values())

    def list_ids(self) -> List[str]:
        return list(self._channels.keys())

    def get_by_style(self, style: str) -> List[ChannelProfile]:
        return [ch for ch in self._channels.values() if ch.style == style]

    def add_channel(self, profile_data: Dict) -> ChannelProfile:
        """新チャンネルをJSONファイルとして保存し、メモリにも追加"""
        channel_id = profile_data["id"]
        file_path = self._data_dir / f"{channel_id}.json"
        file_path.write_text(
            json.dumps(profile_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.reload()
        return self._channels[channel_id]

    def update_channel(self, channel_id: str, updates: Dict) -> Optional[ChannelProfile]:
        """チャンネル設定を更新してJSONに保存"""
        ch = self._channels.get(channel_id)
        if not ch:
            return None
        file_path = self._data_dir / f"{channel_id}.json"
        raw = ch._raw.copy()
        # トップレベルフィールド更新
        for key in ("name", "concept", "style", "youtube_channel_id",
                     "characters", "thumbnail_template", "defaults",
                     "content_policy", "theme_seeds", "publish_settings"):
            if key in updates:
                raw[key] = updates[key]
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
        file_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self.reload()
        return self._channels.get(channel_id)

    def remove_channel(self, channel_id: str) -> bool:
        """チャンネルJSONを削除"""
        file_path = self._data_dir / f"{channel_id}.json"
        if file_path.exists():
            file_path.unlink()
            self._channels.pop(channel_id, None)
            return True
        return False
