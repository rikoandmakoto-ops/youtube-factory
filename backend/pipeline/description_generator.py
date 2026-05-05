"""
YouTube Description Generator for Auto-Yukkuri Movie Pipeline
Generates YouTube descriptions with video summary, timestamps, channel info, and hashtags
"""

from typing import Optional, Dict, List
from datetime import datetime
import re


# Hardcoded channel defaults
CHANNEL_NAME = "リコとマコトのゆっくり日常科学"
CHANNEL_CONCEPT = "日常のふとした疑問を科学の視点からゆっくり解説するチャンネル"
CHANNEL_TAGS = ["科学", "ゆっくり解説", "日常科学", "教育"]


def generate_description(
    video_title: str,
    video_summary: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    timestamps: Optional[List[Dict[str, str]]] = None,
    additional_info: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a complete YouTube description for a yukkuri video.

    Args:
        video_title: The title of the video
        video_summary: 2-3 sentence summary of the video content (optional)
        duration_seconds: Duration of the video in seconds (optional)
        timestamps: List of dicts with 'time' and 'title' keys (optional)
        additional_info: Any additional information to include (optional)

    Returns:
        Dict with keys:
        - 'full_description': Complete formatted YouTube description
        - 'summary': The summary section
        - 'timestamps': The timestamps section
        - 'channel_info': The channel information section
        - 'hashtags': The hashtags section
    """

    # Generate or use provided summary
    summary_section = _generate_summary(video_title, video_summary)

    # Generate timestamps section
    timestamps_section = _generate_timestamps(duration_seconds, timestamps)

    # Generate channel info section
    channel_section = _generate_channel_info()

    # Generate hashtags
    hashtags_section = _generate_hashtags(video_title)

    # Combine all sections
    full_description = "\n".join(
        section for section in [
            summary_section,
            timestamps_section,
            channel_section,
            additional_info if additional_info else "",
            hashtags_section,
        ] if section.strip()
    )

    return {
        'full_description': full_description,
        'summary': summary_section,
        'timestamps': timestamps_section,
        'channel_info': channel_section,
        'hashtags': hashtags_section,
    }


def _generate_summary(video_title: str, custom_summary: Optional[str] = None) -> str:
    """Generate the video summary section."""
    if custom_summary:
        return custom_summary.strip()

    # If no summary provided, generate a basic one based on title
    summary = f"{video_title}についての動画です。\n\n"
    summary += "このチャンネルでは、日常の疑問を科学の視点から分かりやすく解説します。\n"
    summary += "ぜひ最後までご視聴ください。"

    return summary


def _generate_timestamps(
    duration_seconds: Optional[int] = None,
    timestamps: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Generate the timestamps/table of contents section."""
    if not timestamps:
        return ""

    lines = ["【もくじ】"]

    for ts in timestamps:
        time_str = ts.get('time', '')
        title = ts.get('title', '')

        if time_str and title:
            lines.append(f"{time_str} {title}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _generate_channel_info() -> str:
    """Generate the channel information section."""
    section = "\n【チャンネルについて】\n"
    section += f"チャンネル名: {CHANNEL_NAME}\n"
    section += f"コンセプト: {CHANNEL_CONCEPT}\n"
    section += "\n"
    section += "日常生活の中で出てくる様々な疑問を、科学や心理学など"
    section += "様々な視点からゆっくり丁寧に解説していきます。\n"
    section += "音楽・物理・心理学・食べ物など身近なテーマを扱っています。\n"
    section += "\n"
    section += "チャンネル登録をぜひお願いします！"

    return section


def _generate_hashtags(video_title: str) -> str:
    """Generate relevant hashtags based on video title."""
    hashtags = set(CHANNEL_TAGS)

    # Extract potential keywords from title
    keywords = _extract_keywords(video_title)
    hashtags.update(keywords)

    # Format hashtags
    hashtag_str = " ".join(f"#{tag}" for tag in sorted(hashtags))

    return hashtag_str


def _extract_keywords(text: str) -> List[str]:
    """Extract potential keywords from text for hashtags."""
    # Simple keyword extraction - removes common words and formatting
    stop_words = {
        'とは', 'です', 'ある', 'いる', 'する', 'される', 'ない',
        'なる', 'いく', 'くる', 'みる', 'おく', 'まう', 'もう',
        '何', 'どうして', 'なぜ', 'こと', 'ため', 'もの',
    }

    # Split text into potential keywords (removing punctuation)
    cleaned = re.sub(r'[？？！!「」『』・\-〜～\(\)（）]', ' ', text)
    words = cleaned.split()

    # Filter and deduplicate
    keywords = [
        word for word in words
        if word and len(word) > 1 and word not in stop_words
    ]

    return keywords[:5]  # Limit to 5 keywords


def generate_short_description(
    video_title: str,
    full_video_title: Optional[str] = None,
    buzz_lines: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    Generate YouTube Shorts description and title.

    Returns:
        Dict with keys:
        - 'short_title': Catchy title for the short
        - 'short_description': Full description for the short
        - 'hashtags': Hashtag string
    """
    # Generate catchy short title (under 40 chars ideally)
    short_title = _generate_short_title(video_title)

    # Short description
    desc_lines = []
    if buzz_lines and len(buzz_lines) > 0:
        desc_lines.append(buzz_lines[0])  # Hook line
    desc_lines.append("")
    desc_lines.append(f"フル動画はこちら👇")
    if full_video_title:
        desc_lines.append(f"「{full_video_title}」をチャンネルで検索！")
    desc_lines.append("")
    desc_lines.append(f"📺 {CHANNEL_NAME}")
    desc_lines.append(CHANNEL_CONCEPT)
    desc_lines.append("")

    # Shorts-optimized hashtags
    hashtags = _generate_short_hashtags(video_title)
    desc_lines.append(hashtags)

    short_description = "\n".join(desc_lines)

    return {
        'short_title': short_title,
        'short_description': short_description,
        'hashtags': hashtags,
    }


def _generate_short_title(video_title: str) -> str:
    """Generate a punchy short title from the full video title."""
    # Extract core topic and make it punchy
    # Remove common prefixes
    title = video_title
    for prefix in ["【ゆっくり解説】", "【ゆっくり日常科学】"]:
        title = title.replace(prefix, "")
    title = title.strip()

    # Keep it short and punchy - add hook if needed
    if len(title) > 35:
        # Truncate at a natural break
        for sep in ["？", "！", "の", "を"]:
            idx = title.find(sep)
            if 10 < idx < 35:
                title = title[:idx + 1]
                break

    return f"#shorts {title}"


def _generate_short_hashtags(video_title: str) -> str:
    """Generate hashtags optimized for Shorts discovery."""
    base_tags = ["shorts", "ゆっくり解説", "雑学", "豆知識"]
    keywords = _extract_keywords(video_title)
    all_tags = base_tags + keywords[:3]
    return " ".join(f"#{tag}" for tag in all_tags)


def generate_description_from_job(job_data: Dict) -> Dict[str, str]:
    """
    Generate description from a job/compose data structure.

    Expected job_data structure:
    {
        'title': 'video title',
        'scenario': 'video content/script',
        'duration_seconds': int,
        'timestamps': [{'time': 'MM:SS', 'title': 'section title'}, ...],
        'custom_summary': 'optional custom summary'
    }
    """
    return generate_description(
        video_title=job_data.get('title', 'Untitled'),
        video_summary=job_data.get('custom_summary'),
        duration_seconds=job_data.get('duration_seconds'),
        timestamps=job_data.get('timestamps'),
        additional_info=job_data.get('additional_info'),
    )
