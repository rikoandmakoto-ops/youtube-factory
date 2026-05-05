"""
YouTube Title Generator for Auto-Yukkuri Movie Pipeline
Generates title suggestions for yukkuri videos
"""

from typing import List, Dict, Optional
import re


def generate_titles(scenario: str, num_suggestions: int = 5) -> List[str]:
    """
    Generate YouTube title suggestions based on the video scenario.

    Args:
        scenario: The video script/scenario content
        num_suggestions: Number of title suggestions to generate (default 5)

    Returns:
        List of suggested titles
    """
    titles = []

    # Extract key concepts from the scenario
    key_phrases = _extract_key_phrases(scenario)

    # Generate different title patterns
    titles.extend(_generate_question_titles(key_phrases))
    titles.extend(_generate_descriptive_titles(key_phrases))
    titles.extend(_generate_curiosity_titles(key_phrases))

    # Deduplicate and limit
    titles = list(dict.fromkeys(titles))  # Remove duplicates while preserving order
    titles = titles[:num_suggestions]

    return titles


def _extract_key_phrases(text: str) -> List[str]:
    """Extract key phrases from the scenario text."""
    # Remove markdown-like formatting
    cleaned = re.sub(r'[#*_`【】「」『』]', '', text)

    # Split by sentence delimiters
    sentences = re.split(r'[。！？\n]', cleaned)

    key_phrases = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 3 and len(sentence) < 50:
            key_phrases.append(sentence)

    return key_phrases[:10]  # Limit to top 10 phrases


def _generate_question_titles(phrases: List[str]) -> List[str]:
    """Generate titles in question format."""
    titles = []
    for phrase in phrases[:3]:
        # Convert to question format
        if not phrase.endswith('？') and not phrase.endswith('?'):
            titles.append(f"{phrase}とは？")
            titles.append(f"{phrase}？")
            titles.append(f"なぜ{phrase}のか")

    return titles


def _generate_descriptive_titles(phrases: List[str]) -> List[str]:
    """Generate descriptive titles."""
    titles = []
    for phrase in phrases[:3]:
        titles.append(f"【科学】{phrase}")
        titles.append(f"【解説】{phrase}について")
        titles.append(f"{phrase}の秘密とは")

    return titles


def _generate_curiosity_titles(phrases: List[str]) -> List[str]:
    """Generate curiosity-driven titles."""
    titles = []
    curiosity_patterns = [
        "知ると驚く{}の真実",
        "実は{}だった",
        "{}を科学的に解説",
        "{}の仕組みが分かる",
    ]

    for i, phrase in enumerate(phrases[:len(curiosity_patterns)]):
        titles.append(curiosity_patterns[i].format(phrase))

    return titles


def select_best_title(titles: List[str], preference: Optional[str] = None) -> str:
    """
    Select the best title from suggestions.

    Args:
        titles: List of title suggestions
        preference: Optional preference ('question', 'descriptive', 'curiosity')

    Returns:
        Selected title
    """
    if not titles:
        return "新しい動画"

    if preference == 'question' and any('？' in t or '？' in t for t in titles):
        return next(t for t in titles if '？' in t or '？' in t)

    if preference == 'descriptive' and any('【' in t for t in titles):
        return next(t for t in titles if '【' in t)

    # Return the first (usually best) title
    return titles[0]
