"""
ABTestGenerator — Phase C: タイトル・サムネ AB テスト

1つのテーマ／シナリオに対して、タイトル 3 パターン + サムネキャッチコピー 3 パターンを
生成し、それぞれに CTR 予測スコア (1-10) を付け、最高スコアの組み合わせを返す。

役割分担:
  - 生成（クリエイティブ）: GPT-4o（タイトル＋サムネキャッチコピー）
  - 採点（CTR 予測スコアリング）: Claude Sonnet 4（分析・評価系のため Claude に集約）

パターン定義:
  - question : 疑問形（「なぜ〜なのか」「〜は本当か？」）
  - number   : 数字入り（「99%が知らない〜」「3分で分かる〜」「1923年の〜」）
  - surprise : 意外性フック（「実は〜だった」「衝撃の事実」など）

評価軸（Claude に採点させる）:
  - 好奇心喚起度
  - 具体性（数字・固有名詞）
  - ターゲット層マッチ
  - 文字数の読みやすさ（タイトルは 32 字前後が理想）

成果は data/ab_tests/<test_id>.json に保存し、後で実績 CTR と照合できるよう
{ test_id, theme, generated_at, variants:[{pattern, title, thumb_copy, score, breakdown}],
  best:{...}, channel_id } の形にする。

公開関数:
  - generate_ab_test(theme_title, theme_angle, channel_id=None, scenario_summary=None) -> Dict
  - load_ab_test(test_id) -> Dict
  - list_ab_tests(channel_id=None, limit=50) -> List[Dict]

OPENAI_API_KEY / ANTHROPIC_API_KEY 未設定でもクラッシュしない（フォールバック: ローカル簡易生成 + ゼロスコア）。
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from pipeline import api_usage
except ImportError:  # pragma: no cover
    api_usage = None

from pipeline import claude_client


GPT_MODEL = "gpt-4.1"
GPT_MODEL_LIGHT = "gpt-4.1-mini"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

_AB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ab_tests"

PATTERNS = [
    {
        "id": "question",
        "label": "疑問形",
        "guidance": (
            "疑問形のタイトル。「なぜ〇〇なのか」「〇〇は本当か？」など、"
            "視聴者に問いかけて好奇心を刺激する。"
        ),
    },
    {
        "id": "number",
        "label": "数字入り",
        "guidance": (
            "具体的な数字・年号・割合を含むタイトル。"
            "「99%が知らない〇〇」「実は3分で分かる〇〇」「1923年に〇〇」など、"
            "数字で具体性を出してクリック率を上げる。"
        ),
    },
    {
        "id": "surprise",
        "label": "意外性フック",
        "guidance": (
            "意外性・常識破りのフックを冒頭に置く。"
            "「実は〇〇だった」「衝撃の事実」「あなたの常識は間違い」など、"
            "ギャップで指を止めさせる。"
        ),
    },
]


# ---------------------------------------------------------------------
# 補助
# ---------------------------------------------------------------------

def _ensure_dir() -> Path:
    _AB_DIR.mkdir(parents=True, exist_ok=True)
    return _AB_DIR


def _call_gpt(messages: List[Dict[str, str]], *, model: str = GPT_MODEL,
              temperature: float = 0.85, max_tokens: int = 1500,
              json_mode: bool = True,
              channel_id: Optional[str] = None,
              purpose: Optional[str] = None) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    if api_usage is not None:
        try:
            usage = data.get("usage", {}) or {}
            api_usage.record_chat_usage(
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                channel_id=channel_id,
                purpose=purpose or "ab_test",
            )
        except Exception:
            pass
    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(content) if json_mode else {"content": content}
    except Exception:
        return None


# ---------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------

def _generate_variants(
    theme_title: str,
    theme_angle: str,
    scenario_summary: Optional[str],
    channel_id: Optional[str],
) -> List[Dict[str, Any]]:
    """3 パターンのタイトル + サムネキャッチコピーを1リクエストで生成。"""
    patterns_block = "\n".join(
        f"- {p['id']} ({p['label']}): {p['guidance']}" for p in PATTERNS
    )
    summary_block = f"\n# シナリオ要約:\n{scenario_summary}" if scenario_summary else ""

    learning_block = ""
    try:
        from pipeline.analytics.ab_reconciler import build_ab_learning_addendum
        addendum = build_ab_learning_addendum(channel_id)
        if addendum:
            learning_block = "\n" + addendum + "\n"
    except Exception:
        pass

    user_prompt = (
        f"YouTube動画のタイトルとサムネキャッチコピーを 3 パターン生成。\n\n"
        f"# テーマ: {theme_title} / 切り口: {theme_angle or '自由'}\n"
        f"{summary_block}\n"
        f"{learning_block}\n"
        f"# パターン仕様（必ず 3 パターンとも返す）\n{patterns_block}\n\n"
        f"# 出力 JSON（厳守）\n"
        '{ "variants": [\n'
        '  {"pattern":"question","title":"...","thumb_copy":["1行目","2行目"]},\n'
        '  {"pattern":"number","title":"...","thumb_copy":["1行目","2行目"]},\n'
        '  {"pattern":"surprise","title":"...","thumb_copy":["1行目","2行目"]}\n'
        "]}\n\n"
        "# ルール\n"
        "- title は 32 字前後（28〜40 字）が読みやすい。\n"
        "- thumb_copy は 2 行（1行 9〜14 字目安）。指を止める強いワード。\n"
        "- 各パターンの特徴を必ず満たす（数字入りパターンは数字必須、など）。\n"
        "- 同じ言い回しのコピペは不可。"
    )
    messages = [
        {"role": "system", "content": "YouTube タイトル設計者。JSON のみ返す。"},
        {"role": "user", "content": user_prompt},
    ]
    out = _call_gpt(messages, channel_id=channel_id, purpose="ab_test_generate")
    if not out:
        return _fallback_variants(theme_title)

    variants = out.get("variants") if isinstance(out, dict) else None
    if not isinstance(variants, list) or not variants:
        return _fallback_variants(theme_title)

    # パターンを正規化（不足があれば fallback で補う）
    by_pattern: Dict[str, Dict[str, Any]] = {}
    for v in variants:
        if not isinstance(v, dict):
            continue
        pid = (v.get("pattern") or "").strip().lower()
        if pid not in {p["id"] for p in PATTERNS}:
            continue
        title = (v.get("title") or "").strip()
        thumb = v.get("thumb_copy") or []
        if isinstance(thumb, str):
            thumb = [thumb]
        thumb = [str(t).strip() for t in thumb if str(t).strip()][:2]
        if not title:
            continue
        by_pattern[pid] = {
            "pattern": pid,
            "title": title,
            "thumb_copy": thumb,
        }

    fallback = {v["pattern"]: v for v in _fallback_variants(theme_title)}
    final: List[Dict[str, Any]] = []
    for p in PATTERNS:
        final.append(by_pattern.get(p["id"]) or fallback[p["id"]])
    return final


def _fallback_variants(theme_title: str) -> List[Dict[str, Any]]:
    """OPENAI_API_KEY 未設定時 / GPT 失敗時の簡易テンプレ生成。"""
    base = theme_title.strip() or "新しい動画"
    return [
        {
            "pattern": "question",
            "title": f"なぜ{base}のか？科学が解き明かす真実",
            "thumb_copy": [f"なぜ", f"{base[:10]}?"],
        },
        {
            "pattern": "number",
            "title": f"99%が知らない{base}の3つの事実",
            "thumb_copy": ["99%が", "知らない"],
        },
        {
            "pattern": "surprise",
            "title": f"実は{base}だった！知ると驚く衝撃の事実",
            "thumb_copy": ["実は", "衝撃の事実"],
        },
    ]


# ---------------------------------------------------------------------
# 採点
# ---------------------------------------------------------------------

def _score_variants(
    variants: List[Dict[str, Any]],
    theme_title: str,
    theme_angle: str,
    channel_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Claude (Sonnet 4) に CTR 予測スコア(1-10) を付けさせる。"""
    payload_variants = [
        {
            "index": i,
            "pattern": v["pattern"],
            "title": v["title"],
            "thumb_copy": v.get("thumb_copy", []),
        }
        for i, v in enumerate(variants)
    ]
    user_prompt = (
        f"以下の YouTube タイトル＋サムネキャッチコピーを CTR 予測スコア (1〜10) で採点。\n\n"
        f"# テーマ: {theme_title} / 切り口: {theme_angle or '自由'}\n"
        f"# 採点基準（各 1〜10）\n"
        f"- curiosity   : 好奇心を喚起できるか\n"
        f"- specificity : 具体性（数字・固有名詞・年号など）\n"
        f"- target_fit  : ターゲット層（科学・教育 / 一般視聴者）にマッチしているか\n"
        f"- readability : 文字数の読みやすさ（タイトルは 32 字前後・サムネは 1 行 9〜14 字）\n"
        f"- score       : 総合 CTR 予測スコア（上記 4 つの加重平均、最終は 1.0〜10.0）\n\n"
        f"# 候補:\n{json.dumps(payload_variants, ensure_ascii=False, indent=2)}\n\n"
        "# 出力 JSON（厳守）\n"
        '{ "scores": [\n'
        '  {"index":0, "curiosity":8.0, "specificity":7.0, "target_fit":8.5, "readability":9.0, "score":8.1, "comment":"短評"},\n'
        "  ...\n"
        "]}\n"
        "- index は入力と同じ順序で全件返す。\n"
        "- score は加重: curiosity*0.35 + specificity*0.25 + target_fit*0.25 + readability*0.15。"
    )
    out = claude_client.call_claude_json(
        system="YouTube CTR を読み解くアナリスト。JSON のみ返す。",
        user=user_prompt,
        temperature=0.3,
        max_tokens=1500,
        channel_id=channel_id,
        purpose="ab_test_score",
    )

    scored: List[Dict[str, Any]] = []
    raw_scores = (out or {}).get("scores") if isinstance(out, dict) else None
    by_index: Dict[int, Dict[str, Any]] = {}
    if isinstance(raw_scores, list):
        for s in raw_scores:
            if not isinstance(s, dict):
                continue
            try:
                idx = int(s.get("index"))
            except Exception:
                continue
            by_index[idx] = s

    for i, v in enumerate(variants):
        s = by_index.get(i, {})
        # フォールバック: GPT が失敗 / 欠損なら 0.0 とパターン baseline
        breakdown = {
            "curiosity": _safe_float(s.get("curiosity"), default=0.0),
            "specificity": _safe_float(s.get("specificity"), default=0.0),
            "target_fit": _safe_float(s.get("target_fit"), default=0.0),
            "readability": _safe_float(s.get("readability"), default=0.0),
        }
        score = _safe_float(s.get("score"), default=None)
        if score is None:
            # 加重平均でフォールバック
            score = round(
                breakdown["curiosity"] * 0.35
                + breakdown["specificity"] * 0.25
                + breakdown["target_fit"] * 0.25
                + breakdown["readability"] * 0.15,
                2,
            )
        scored.append({
            **v,
            "score": round(score, 2),
            "breakdown": breakdown,
            "comment": str(s.get("comment") or "").strip()[:200],
        })
    return scored


def _safe_float(v: Any, *, default: Optional[float] = 0.0) -> Optional[float]:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception:
        return default


# ---------------------------------------------------------------------
# 公開エントリポイント
# ---------------------------------------------------------------------

def generate_ab_test(
    theme_title: str,
    theme_angle: str = "",
    *,
    channel_id: Optional[str] = None,
    scenario_summary: Optional[str] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """タイトル＋サムネキャッチコピーを 3 パターン生成 → CTR 採点 → 最高スコアを選択。"""
    variants = _generate_variants(theme_title, theme_angle, scenario_summary, channel_id)
    scored = _score_variants(variants, theme_title, theme_angle, channel_id)
    best = max(scored, key=lambda v: v.get("score", 0.0)) if scored else None

    test_id = f"abt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    result: Dict[str, Any] = {
        "test_id": test_id,
        "channel_id": channel_id,
        "theme": {"title": theme_title, "angle": theme_angle or ""},
        "scenario_summary": scenario_summary,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "variants": scored,
        "best": best,
        "openai_used": bool(os.environ.get("OPENAI_API_KEY", "").strip()),  # 生成（GPT-4o）
        "claude_used": claude_client.has_api_key(),  # 採点（Claude Sonnet 4）
        "actual_metrics": None,  # 後で実績 CTR / views を紐付ける枠
    }

    if save:
        try:
            _ensure_dir()
            (_AB_DIR / f"{test_id}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"⚠️ failed to save ab_test {test_id}: {e}")

    return result


def select_best_title(
    theme_title: str,
    theme_angle: str = "",
    *,
    channel_id: Optional[str] = None,
    scenario_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """最高スコアのタイトル+サムネコピーだけを返す薄いヘルパ。"""
    result = generate_ab_test(
        theme_title,
        theme_angle,
        channel_id=channel_id,
        scenario_summary=scenario_summary,
        save=True,
    )
    best = result.get("best") or {}
    return {
        "test_id": result["test_id"],
        "title": best.get("title", theme_title),
        "thumb_copy": best.get("thumb_copy", []),
        "pattern": best.get("pattern"),
        "score": best.get("score"),
        "ab_test": result,
    }


def load_ab_test(test_id: str) -> Optional[Dict[str, Any]]:
    p = _AB_DIR / f"{test_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_ab_tests(
    channel_id: Optional[str] = None, *, limit: int = 50
) -> List[Dict[str, Any]]:
    if not _AB_DIR.exists():
        return []
    out: List[Dict[str, Any]] = []
    files = sorted(_AB_DIR.glob("abt_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if channel_id and data.get("channel_id") != channel_id:
            continue
        out.append({
            "test_id": data.get("test_id"),
            "channel_id": data.get("channel_id"),
            "theme": data.get("theme"),
            "generated_at": data.get("generated_at"),
            "best_pattern": (data.get("best") or {}).get("pattern"),
            "best_title": (data.get("best") or {}).get("title"),
            "best_score": (data.get("best") or {}).get("score"),
            "variant_count": len(data.get("variants") or []),
            "has_actual_metrics": bool(data.get("actual_metrics")),
        })
        if len(out) >= limit:
            break
    return out


def attach_actual_metrics(test_id: str, metrics: Dict[str, Any]) -> bool:
    """投稿後の実績 CTR / views を ab_test JSON に書き込む（あとでバズ判定の照合に使う）。"""
    p = _AB_DIR / f"{test_id}.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    data["actual_metrics"] = {
        **(data.get("actual_metrics") or {}),
        **metrics,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
