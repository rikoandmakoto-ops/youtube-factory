"""
シナリオアーカイブ — 動画生成時にシナリオ原文をマークダウンで永続化する。

保存先: data/scenarios/<channel_id>/archive/<prefix>_<YYYYmmdd_HHMMSS>_scenario.md
（YouTube video_id が判明していない時点で生成するので prefix + 生成時刻でユニークにする）

フォーマット:
  - YAML frontmatter にメタデータ（title, channel_id, prefix, generated_at, prompt_hash 等）
  - 本文はセクション別: フック / 導入 / 展開1〜N / オチ / CTA / ショート

匹配時は title 照合（retention_analyzer._find_scenario_for と同じ流儀）で video_id と紐づける。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCENARIOS_BASE = PROJECT_ROOT / "data" / "scenarios"


def _archive_dir(channel_id: str) -> Path:
    p = SCENARIOS_BASE / channel_id / "archive"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(text: str) -> str:
    if not text:
        return ""
    return text.replace("---", "—")  # frontmatter delimiter 衝突回避


def _bucket_label(idx: int, total: int) -> str:
    if total <= 1:
        return "本文"
    ratio = idx / max(total - 1, 1)
    if ratio < 0.05:
        return "フック"
    if ratio < 0.20:
        return "導入"
    if ratio < 0.45:
        return "展開1"
    if ratio < 0.70:
        return "展開2"
    if ratio < 0.90:
        return "展開3 / オチ"
    return "CTA / クロージング"


def _scenario_to_sections(full_scenario: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """full_scenario を均等にバケット分けして section リストを返す。"""
    sections: List[Dict[str, Any]] = []
    cur_label = None
    cur_lines: List[Dict[str, Any]] = []
    total = len(full_scenario)
    for i, line in enumerate(full_scenario):
        label = _bucket_label(i, total)
        if label != cur_label:
            if cur_lines:
                sections.append({"section": cur_label, "lines": cur_lines})
            cur_label = label
            cur_lines = []
        cur_lines.append(line)
    if cur_lines:
        sections.append({"section": cur_label, "lines": cur_lines})
    return sections


def _format_lines(lines: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    for ln in lines:
        if not isinstance(ln, dict):
            out.append(f"- {str(ln)}")
            continue
        sp = ln.get("speaker") or ""
        tx = (ln.get("text") or "").strip()
        if not tx:
            continue
        if sp:
            out.append(f"- **{sp}**: {tx}")
        else:
            out.append(f"- {tx}")
    return "\n".join(out)


def _prompt_hash(scenario_data: Dict[str, Any]) -> str:
    """生成時の theme + style + applied_feedback から短いハッシュを作る。"""
    base = {
        "theme": scenario_data.get("theme") or {},
        "style": scenario_data.get("style") or "",
        "applied_feedback": scenario_data.get("applied_feedback") or [],
        "channel_id": scenario_data.get("channel_id") or "",
    }
    encoded = json.dumps(base, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def archive_scenario(
    *,
    channel_id: str,
    prefix: str,
    title: str,
    short_scenario: Optional[List[Dict[str, Any]]] = None,
    full_scenario: Optional[List[Dict[str, Any]]] = None,
    thumb_info: Optional[Dict[str, Any]] = None,
    theme: Optional[Dict[str, Any]] = None,
    style: Optional[str] = None,
    video_title: Optional[str] = None,
    applied_feedback: Optional[List[str]] = None,
    scenario_data: Optional[Dict[str, Any]] = None,
    generated_by: Optional[str] = None,
    selected_by: Optional[str] = None,
    compete: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """シナリオ原文を markdown ファイルとして書き出す。

    Returns:
        書き出した Path（失敗時は None）。
    """
    try:
        archive = _archive_dir(channel_id)
    except Exception as e:
        print(f"⚠️ scenario archive dir create failed: {e}")
        return None

    if scenario_data and theme is None:
        theme = scenario_data.get("theme")
    if scenario_data and style is None:
        style = scenario_data.get("style")
    if scenario_data and applied_feedback is None:
        applied_feedback = scenario_data.get("applied_feedback")
    if scenario_data and video_title is None:
        video_title = scenario_data.get("video_title")
    if scenario_data and short_scenario is None:
        short_scenario = scenario_data.get("short_scenario") or scenario_data.get("short")
    if scenario_data and full_scenario is None:
        full_scenario = scenario_data.get("full_scenario") or scenario_data.get("full")
    if scenario_data and generated_by is None:
        generated_by = scenario_data.get("generated_by")
    if scenario_data and compete is None:
        compete = scenario_data.get("compete")
    if compete and selected_by is None:
        selected_by = compete.get("selected_by")

    short_scenario = short_scenario or []
    full_scenario = full_scenario or []

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_prefix = re.sub(r"[^\w\-]", "_", prefix or "scenario")[:40] or "scenario"
    file_path = archive / f"{safe_prefix}_{ts}_scenario.md"

    h = _prompt_hash(
        {
            "theme": theme or {},
            "style": style or "",
            "applied_feedback": applied_feedback or [],
            "channel_id": channel_id,
        }
    )

    fm_lines = [
        "---",
        f"title: {_safe(title)}",
        f"video_title: {_safe(video_title or '')}",
        f"channel_id: {channel_id}",
        f"prefix: {prefix}",
        f"style: {style or 'yukkuri'}",
        f"generated_at: {datetime.utcnow().isoformat()}Z",
        f"prompt_hash: {h}",
    ]
    if theme:
        fm_lines.append(f"theme_title: {_safe(theme.get('title', ''))}")
        fm_lines.append(f"theme_angle: {_safe(theme.get('angle', ''))}")
    if applied_feedback:
        fm_lines.append(
            "applied_feedback: ["
            + ", ".join(json.dumps(x) for x in applied_feedback)
            + "]"
        )
    if generated_by:
        fm_lines.append(f"generated_by: {generated_by}")
    if selected_by:
        fm_lines.append(f"selected_by: {selected_by}")
    fm_lines.append("---\n")

    body: List[str] = []
    body.append(f"# {title}\n")
    if video_title:
        body.append(f"**公開タイトル案**: {video_title}\n")
    if generated_by:
        label = "GPT-5.6 terra" if generated_by == "gpt" else "Claude Sonnet 4"
        body.append(f"**生成モデル**: {label}")
        if selected_by:
            body.append(f"  (selected_by: {selected_by})\n")
        else:
            body.append("")

    if thumb_info:
        body.append("## サムネ情報")
        body.append("```json")
        body.append(json.dumps(thumb_info, ensure_ascii=False, indent=2))
        body.append("```\n")

    if short_scenario:
        body.append("## ショートシナリオ")
        body.append(_format_lines(short_scenario))
        body.append("")

    if full_scenario:
        body.append("## フルシナリオ（セクション別）")
        for sec in _scenario_to_sections(full_scenario):
            body.append(f"### {sec['section']}")
            body.append(_format_lines(sec["lines"]))
            body.append("")

    try:
        file_path.write_text("\n".join(fm_lines) + "\n".join(body), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ scenario archive write failed: {e}")
        return None

    # 軽量な index も同時更新（list 用）
    try:
        index_path = archive / "_index.json"
        if index_path.exists():
            try:
                existing = json.loads(index_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        else:
            existing = []
        existing.insert(
            0,
            {
                "file": file_path.name,
                "title": title,
                "video_title": video_title,
                "prefix": prefix,
                "theme": theme or {},
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "prompt_hash": h,
                "generated_by": generated_by,
                "selected_by": selected_by,
            },
        )
        existing = existing[:500]
        index_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ scenario archive index update failed: {e}")

    print(f"📝 シナリオアーカイブ: {file_path}")
    return file_path


def find_archive_for_title(channel_id: str, video_title: Optional[str]) -> Optional[Path]:
    """video の title から archive 内の markdown を緩くマッチ。なければ None。"""
    if not video_title:
        return None
    base = _archive_dir(channel_id)
    if not base.exists():
        return None
    target = _normalize(video_title)
    if not target:
        return None
    best: Optional[tuple] = None
    for f in base.glob("*_scenario.md"):
        head = ""
        try:
            with f.open("r", encoding="utf-8") as fh:
                for _ in range(20):
                    line = fh.readline()
                    if not line:
                        break
                    head += line
        except Exception:
            continue
        m = re.search(r"video_title:\s*(.+)", head)
        cand_title = m.group(1).strip() if m else ""
        if not cand_title:
            m2 = re.search(r"^title:\s*(.+)", head, re.MULTILINE)
            cand_title = m2.group(1).strip() if m2 else ""
        cand = _normalize(cand_title)
        if not cand:
            continue
        shared = 0
        for n in range(3, min(len(target), len(cand)) + 1):
            if target[:n] in cand or cand[:n] in target:
                shared = n
        score = shared / max(len(target), len(cand), 1)
        if score >= 0.4 and (best is None or score > best[0]):
            best = (score, f)
    return best[1] if best else None


_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥A-Za-z0-9]+")


def _normalize(s: str) -> str:
    if not s:
        return ""
    return "".join(_TOKEN_RE.findall(s)).lower()


def list_archives(channel_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    """archive index を返す（新しい順）。"""
    base = _archive_dir(channel_id)
    index_path = base / "_index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[:limit]
        except Exception:
            pass
    out: List[Dict[str, Any]] = []
    for f in sorted(base.glob("*_scenario.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        out.append({"file": f.name, "title": f.stem, "generated_at": None})
    return out
