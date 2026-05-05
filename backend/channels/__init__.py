"""
Channel Manager — マルチチャンネルプロファイル管理

data/channels/*.json からチャンネル設定を読み込み、
パイプラインにキャラクター・スタイル・デフォルト値を供給する。
"""

from .channel_manager import ChannelManager
from .video_format import VideoFormat, LayoutConfig, ColorConfig, AudioConfig, BrandingConfig, OutputConfig, YouTubeConfig, AnalyticsConfig

__all__ = ["ChannelManager", "VideoFormat", "LayoutConfig", "ColorConfig", "AudioConfig", "BrandingConfig", "OutputConfig", "YouTubeConfig", "AnalyticsConfig"]
