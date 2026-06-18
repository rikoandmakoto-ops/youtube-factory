"""
VideoFormat — チャンネル別ビデオフォーマット定義

各チャンネルのJSON profileの "video_format" セクションから読み込み、
FrameRenderer / generate_all に注入するフォーマット設定。

全パラメータにデフォルト値があるため、未設定項目はデフォルトで動く。
チャンネルごとに一度設定すれば、以降の動画は全て統一フォーマットで出力される。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class LayoutConfig:
    """フレームレイアウト設定"""
    # メイン動画
    width: int = 1920
    height: int = 1080
    fps: int = 24
    # ショート動画
    short_width: int = 1080
    short_height: int = 1920
    short_fps: int = 24

    # キャラクター配置
    char_canvas_w_ratio: float = 0.418  # キャラ表示幅（画面比率）
    char_y_offset: int = 130            # キャラY位置オフセット（px）
    char_x_inset_ratio: float = 0.15    # キャラ左右はみ出し率
    speaker_glow: bool = True           # 発話者グロー効果
    nonspeaker_opacity: float = 0.5     # 非発話者の透明度
    char_scale_short: float = 1.0       # ショート用キャラスケール

    # テキストボックス
    text_box_height_ratio: float = 0.20   # テキストボックスの高さ（画面比率）
    text_box_opacity: int = 180           # テキストボックス背景透明度 (0-255)
    text_font_size: int = 42              # 本文フォントサイズ
    text_stroke_width: int = 3            # テキスト縁取り幅
    text_line_spacing: int = 4            # 行間（px）
    text_margin_x: int = 60              # テキスト左右マージン

    # イラスト
    illustration_size: int = 360          # イラスト表示サイズ
    illustration_card_padding: int = 10   # イラストカード余白
    illustration_card_opacity: int = 200  # カード背景透明度
    illustration_y: int = 40              # イラストY位置
    illustration_interval: int = 30       # イラスト挿入間隔（秒）


@dataclass
class ColorConfig:
    """カラーテーマ設定"""
    bg_color: Tuple[int, int, int, int] = (15, 25, 50, 255)      # デフォルト背景色
    text_box_color: Tuple[int, int, int] = (0, 0, 0)              # テキストボックス色
    text_stroke_color: Tuple[int, int, int] = (0, 0, 0)           # テキスト縁取り色
    # サムネイル
    thumb_bg_gradient: Optional[List[Tuple[int, int, int]]] = None  # グラデーション色
    thumb_overlay_opacity: int = 180                                # サムネオーバーレイ


@dataclass
class AudioConfig:
    """音声設定"""
    speed: float = 1.3            # 話速倍率
    pause_between: float = 0.3     # セリフ間ポーズ（秒）
    bgm_volume: float = 0.30      # BGM音量（0.0-1.0）
    bgm_path: Optional[str] = None  # チャンネル固定BGM（指定時はシーンごと切替を無効化）
    bgm_per_scene: bool = True    # シーンごと(雰囲気タグ)にBGMを切替えるか
    bgm_crossfade: float = 1.5    # シーン境界のクロスフェード秒数


@dataclass
class BrandingConfig:
    """ブランディング設定"""
    watermark_text: Optional[str] = None   # 透かしテキスト
    watermark_opacity: int = 30            # 透かし透明度
    watermark_position: str = "bottom_right"  # 位置
    intro_duration: float = 0.0            # イントロ秒数（0=なし）
    outro_duration: float = 0.0            # アウトロ秒数
    cta_style: str = "casual"              # CTA表示スタイル
    # 常時表示する出典/クレジット文字列（フレーム右下、控えめサイズ）
    source_credit: Optional[str] = None
    source_credit_opacity: int = 160       # 0-255
    source_credit_font_size: int = 20      # フル動画のフォントサイズ
    source_credit_font_size_short: int = 26  # 縦長ショート用


@dataclass
class OutputConfig:
    """出力設定"""
    target_duration: int = 720      # 目標尺（秒）— 720=12分目安(フル, 最低10分=600), 30=ショート
    gen_type: str = "both"          # デフォルト生成タイプ
    bg_type: str = "auto"           # 背景タイプ
    bg_path: Optional[str] = None   # 固定背景パス
    use_illustrations: bool = True  # イラスト生成
    codec: str = "libx264"          # 映像コーデック
    audio_codec: str = "aac"        # 音声コーデック
    bitrate: str = "8000k"          # ビットレート


@dataclass
class YouTubeConfig:
    """YouTube連携設定"""
    channel_id: Optional[str] = None          # YouTubeチャンネルID (UC...)
    default_tags: List[str] = field(default_factory=list)
    default_category: str = "27"              # Education
    default_language: str = "ja"
    privacy_status: str = "private"           # デフォルト公開設定
    upload_schedule: Optional[str] = None     # cron式スケジュール（例: "0 18 * * MON,THU"）
    shorts_schedule: Optional[str] = None
    playlist_id: Optional[str] = None         # 自動追加先プレイリスト


@dataclass
class IllustrationStyleConfig:
    """イラスト生成スタイル（DALL-E + 表示フレーム）設定

    art_style と background は自由記述。プロンプトに直接埋め込まれるため、
    雰囲気を変えたい場合はここを書き換えるだけで済む。
    """
    style: str = "vivid"                # DALL-E 3 style: "vivid" or "natural"
    format: str = "landscape"           # "landscape" / "square" / "portrait"
    art_style: str = (                  # 自由記述のアートスタイル
        "colorful hand-drawn cartoon illustration in the style of popular Japanese "
        "educational YouTube explainer videos. Bright pop colors, thick clean "
        "outlines, playful flat-color shading with light gradients, friendly "
        "anime/manga aesthetic"
    )
    background: str = "soft pastel background with subtle decorative shapes"
    include_characters: bool = True     # チャンネルキャラを画に含めるか
    frame_style: str = "wooden"         # "wooden" / "blackboard" / "whiteboard" / "comic-red-border" / "none"
    extra_prompt: str = ""              # 追加プロンプト指示（任意）
    allow_text_labels: bool = False     # True にすると Japanese ラベル・矢印・吹き出し等の文字を許可
    allow_frame: bool = False           # True にすると "NO frames" 制約を外して赤枠などのコミック風枠を許可


@dataclass
class AnalyticsConfig:
    """アナリティクス連携設定"""
    enabled: bool = False
    track_metrics: List[str] = field(default_factory=lambda: [
        "views", "watch_time", "ctr", "retention"
    ])
    performance_threshold: Dict[str, float] = field(default_factory=lambda: {
        "min_ctr": 4.0,          # CTR下限(%)
        "min_retention": 40.0,   # 平均視聴維持率下限(%)
        "min_views_7d": 1000,    # 7日間最低再生数
    })
    auto_adjust: bool = False    # パフォーマンスに基づく自動調整


@dataclass
class PersonaConfig:
    """ターゲット視聴者のペルソナ設定。

    シナリオ生成時にプロンプトへ注入され、口調・語彙・解説の深さが切り替わる。
    全フィールド任意。未設定なら従来どおり content_policy.tone がそのまま使われる。
    """
    age_group: str = ""              # "10代" / "20代" / "30代" / "40代+"
    gender: str = ""                 # "男性" / "女性" / "全般"
    interest_categories: List[str] = field(default_factory=list)  # 例: ["科学", "雑学"]
    tone_style: str = ""             # "カジュアル" / "丁寧" / "フランク" / "ゆるい"
    content_depth: str = ""          # "ライト" / "ミドル" / "ディープ"
    custom_notes: str = ""           # 自由記述の追加指示

    def is_configured(self) -> bool:
        """少なくとも1つでも設定があれば True"""
        return any([
            self.age_group, self.gender, self.tone_style,
            self.content_depth, self.custom_notes,
            bool(self.interest_categories),
        ])

    def to_prompt_block(self) -> str:
        """シナリオ生成プロンプトに差し込む日本語ブロックを返す。

        未設定項目は省略する。中身が空なら空文字。
        """
        if not self.is_configured():
            return ""

        lines: List[str] = ["# ターゲット視聴者ペルソナ（このペルソナに刺さるシナリオを書け）"]
        if self.age_group:
            lines.append(f"- 年齢層: {self.age_group}")
        if self.gender:
            lines.append(f"- 性別傾向: {self.gender}")
        if self.interest_categories:
            lines.append(f"- 興味カテゴリ: {', '.join(self.interest_categories)}")
        if self.tone_style:
            lines.append(f"- 口調スタイル: {self.tone_style}")
        if self.content_depth:
            lines.append(f"- コンテンツ深さ: {self.content_depth}")
        if self.custom_notes:
            lines.append(f"- 追加指示: {self.custom_notes}")

        guide = self._style_guide()
        if guide:
            lines.append("# 口調・深さガイド（厳守）")
            lines.extend(f"- {g}" for g in guide)

        return "\n".join(lines)

    def _style_guide(self) -> List[str]:
        """ペルソナの組み合わせから具体的な書き方ルールを生成する。

        例: 10代×カジュアル → 若者言葉/テンポ重視
            40代+×ディープ → 専門用語OK/根拠重視
        """
        guide: List[str] = []

        # 口調
        if self.tone_style == "カジュアル":
            guide.append("砕けた口語。「マジで」「やばい」「めっちゃ」など若者寄りの言い回しを散りばめる")
        elif self.tone_style == "丁寧":
            guide.append("敬語ベース。「〜です/ます」「〜しましょう」を基調に、共感の相槌を多めに")
        elif self.tone_style == "フランク":
            guide.append("親しい友人に話すようなフランクな口調。タメ口寄りだが下品にはしない")
        elif self.tone_style == "ゆるい":
            guide.append("肩の力を抜いた、ゆるく抜け感のある語り。長文を避け短く軽快に")

        # 年齢層
        if self.age_group == "10代":
            guide.append("テンポ最優先。1行を短く、結論を前倒し。例え話はSNS/ゲーム/学校文化から取る")
        elif self.age_group == "20代":
            guide.append("仕事/恋愛/お金/健康など20代の関心事に紐付けて解説する")
        elif self.age_group == "30代":
            guide.append("仕事のキャリア/家庭/育児/健康など、30代の生活実感に寄せた具体例を入れる")
        elif self.age_group == "40代+":
            guide.append("人生経験を踏まえた重みのある解説。歴史・経済・健康など落ち着いた切り口で")

        # 深さ
        if self.content_depth == "ライト":
            guide.append("専門用語は極力避け、使う時は必ず一言で言い換える。雑学・あるある中心")
        elif self.content_depth == "ミドル":
            guide.append("基本概念は丁寧に説明しつつ、研究データや具体的数字を要所に入れる")
        elif self.content_depth == "ディープ":
            guide.append("専門用語OK、論文名/研究者名/年代/数値などの根拠を厚めに盛る")

        # 性別傾向（強制ではなく雰囲気）
        if self.gender == "男性":
            guide.append("ロジック・データ・仕組み解説を厚めに")
        elif self.gender == "女性":
            guide.append("共感・ストーリー・実生活への落とし込みを厚めに")

        return guide


# ============================================================
# Effects — 画面演出（pipeline/video_effects.py で消費）
# ============================================================

@dataclass
class EffectsConfig:
    """画面演出（ズーム / シェイク / フラッシュ等）の有効化と強度プリセット。

    preset: "off" | "minimal" | "balanced" | "horror"
    細かな ON/OFF はプリセット適用後に boolean 上書きで指定する。
    """
    enabled: bool = True
    preset: str = "balanced"
    allow_zoom: bool = True
    allow_shake: bool = True
    allow_flash: bool = True
    allow_tint: bool = True
    allow_pixelate: bool = True
    allow_glitch: bool = True
    allow_transitions: bool = True
    max_effects_per_scene: int = 2
    shake_max_px: int = 14
    zoom_max: float = 0.06
    transition_duration: float = 0.35
    transition_min_gap: float = 6.0
    fade_in_first: bool = True
    fade_out_last: bool = True


# ============================================================
# VideoFormat — 統合フォーマット
# ============================================================

@dataclass
class VideoFormat:
    """
    1チャンネル分の完全なビデオフォーマット設定。
    channel JSONの "video_format" セクションから生成。
    """
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    colors: ColorConfig = field(default_factory=ColorConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    illustration_style: IllustrationStyleConfig = field(default_factory=IllustrationStyleConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    effects: EffectsConfig = field(default_factory=EffectsConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoFormat":
        """JSONの video_format セクションからVideoFormatを生成"""
        if not data:
            return cls()

        def _make(dc_class, section_data):
            """dataclass のフィールドだけ取り出してインスタンス化"""
            if not section_data:
                return dc_class()
            field_names = {f.name for f in dc_class.__dataclass_fields__.values()}
            filtered = {}
            for k, v in section_data.items():
                if k in field_names:
                    # タプル変換（JSONはリストで来る）
                    field_type = dc_class.__dataclass_fields__[k].type
                    if "Tuple" in str(field_type) and isinstance(v, list):
                        v = tuple(v)
                    filtered[k] = v
            return dc_class(**filtered)

        return cls(
            layout=_make(LayoutConfig, data.get("layout")),
            colors=_make(ColorConfig, data.get("colors")),
            audio=_make(AudioConfig, data.get("audio")),
            branding=_make(BrandingConfig, data.get("branding")),
            output=_make(OutputConfig, data.get("output")),
            illustration_style=_make(IllustrationStyleConfig, data.get("illustration_style")),
            youtube=_make(YouTubeConfig, data.get("youtube")),
            analytics=_make(AnalyticsConfig, data.get("analytics")),
            persona=_make(PersonaConfig, data.get("persona")),
            effects=_make(EffectsConfig, data.get("effects")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON用にシリアライズ"""
        import dataclasses

        def _serialize(obj):
            if dataclasses.is_dataclass(obj):
                result = {}
                for f in dataclasses.fields(obj):
                    val = getattr(obj, f.name)
                    if isinstance(val, tuple):
                        val = list(val)
                    elif dataclasses.is_dataclass(val):
                        val = _serialize(val)
                    result[f.name] = val
                return result
            return obj

        return _serialize(self)

    def merge_channel_defaults(self, channel_defaults: Dict):
        """channel.defaults のレガシー設定をマージ（後方互換）"""
        if "speed" in channel_defaults:
            self.audio.speed = channel_defaults["speed"]
        if "target_duration" in channel_defaults:
            self.output.target_duration = channel_defaults["target_duration"]
        if "bg_type" in channel_defaults:
            self.output.bg_type = channel_defaults["bg_type"]
        if "use_illustrations" in channel_defaults:
            self.output.use_illustrations = channel_defaults["use_illustrations"]
        if "category" in channel_defaults:
            self.youtube.default_category = channel_defaults["category"]
        if "hashtags" in channel_defaults:
            self.youtube.default_tags = channel_defaults["hashtags"]
