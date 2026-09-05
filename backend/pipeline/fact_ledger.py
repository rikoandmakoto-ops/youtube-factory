"""fact_ledger — 同じ会社の同じ指標を、回ごとに違う数字で公開しないための台帳。

なぜ必要か（2026-09-06）:
    `company-facts` は「有価証券報告書を根拠にする」ことが売りのチャンネルなのに、
    日本マクドナルドの年収を **576万円**（2023年有報）と **670万円**（2024年12月期）で
    別々に公開していた。どちらの数字も出典上は正しいが、視聴者から見れば
    同じ会社の年収が回によって食い違う。根拠を売りにするチャンネルで信頼を直接削る。

    テーマ重複ゲート（`theme_dedup`）はタイトルの語彙しか見ないので、
    「別の切り口の別回」として正しく通してしまう。数字の整合性は別の軸で見るしかない。

やること:
    1. 公開したシナリオから (会社, 指標, 値, 期) を抜いて台帳に積む
    2. 新しいシナリオを台帳と突き合わせる
       - 同じ会社・同じ指標・**同じ期**で値が違う → 矛盾（`conflict`）
       - 同じ会社・同じ指標・**期が違う** → 矛盾ではないが、画面に期が出ていないと
         視聴者には矛盾に見える → 期を注記して開示する（`disclosed`）

`fact_consistency.enabled` がチャンネル設定にあるときだけ働く。
自然文のルールではなく機械ゲートなので、LLM が守るかどうかに依存しない。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = Path(os.environ.get("FACT_LEDGER_DIR") or (ROOT / "data" / "fact_ledger"))

CONFIG_KEY = "fact_consistency"

# 追跡する指標。`fact_main` に現れる表記をそのまま拾う。
# (正規名, 検出パターン, 単位パターン) — 単位まで見ないと「年収576万円」と
# 「年収576人」のような別物を同じ指標として比べてしまう。
_METRICS: List[Tuple[str, str, str]] = [
    ("年収",     r"年収|平均年収|給与|年俸",       r"万円|億円|円"),
    ("平均年齢", r"平均年齢",                      r"歳"),
    ("平均勤続", r"平均勤続|勤続年数|勤続",        r"年"),
    ("賞与",     r"賞与|ボーナス",                 r"カ月|ヶ月|か月|万円"),
    ("年間休日", r"年間休日|休日",                 r"日"),
    ("残業",     r"残業",                          r"時間"),
    ("有給消化", r"有給消化|有給取得|有給",        r"%|％|日"),
    ("離職率",   r"離職率",                        r"%|％"),
    ("店舗数",   r"店舗数|店舗",                   r"店"),
    ("従業員数", r"従業員数|社員数",               r"人|名"),
]

_NUM_RE = r"[0-9][0-9,]*(?:\.[0-9]+)?"

# 会社名の正規化で落とす法人格・組織種別。「日本マクドナルド株式会社」と
# 「日本マクドナルドホールディングス株式会社」を同じ会社として扱うために要る
# （576万円 / 670万円 の食い違いはまさにこの2つの表記で起きた）。
_ENTITY_SUFFIXES = [
    "ホールディングス", "ホールディング", "hd", "グループ",
    "株式会社", "有限会社", "合同会社", "(株)", "（株）",
]

# 期（会計年度・調査時点）。`fact_sub` から拾う。
_PERIOD_RE = re.compile(r"(20[0-9]{2})\s*年(?:\s*([0-9]{1,2})\s*月期)?")


def _norm_entity(name: str) -> str:
    t = (name or "").strip().lower()
    t = re.sub(r"\s+", "", t)
    for suf in _ENTITY_SUFFIXES:
        t = t.replace(suf.lower(), "")
    return t


def _norm_num(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", ""))
    except Exception:
        return None


def extract_period(text: str) -> str:
    """`2023年有価証券報告書` / `2024年12月期・平均` → `2023` / `2024-12`。"""
    m = _PERIOD_RE.search(text or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) else m.group(1)


def extract_entity(scenario: Dict[str, Any]) -> str:
    """このシナリオが扱っている会社名。`bg_query` の先頭語が最も安定している。

    `bg_query` は「<会社名> 店舗 外観」の形で生成されるので、先頭のトークンが
    会社名そのもの。タイトルは煽り文が混ざるので当てにしない。
    """
    for entry in scenario.get("short_scenario") or []:
        if not isinstance(entry, dict):
            continue
        q = (entry.get("bg_query") or "").strip()
        if q:
            return q.split()[0]
    return ""


def extract_claims(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    """シナリオから (会社, 指標, 値, 単位, 期) を抜く。

    会社は**行ごと**の `bg_query` から採る。「退職金・3社で最大2000万円差」の
    ように 1 本で複数社を扱う回があり、シナリオ単位で1社に決め打つと
    別の会社の数字を同じ会社のものとして台帳に積んでしまう。
    """
    fallback = _norm_entity(extract_entity(scenario))
    out: List[Dict[str, Any]] = []
    for idx, entry in enumerate(scenario.get("short_scenario") or []):
        if not isinstance(entry, dict) or entry.get("is_cta"):
            continue
        q = (entry.get("bg_query") or "").strip()
        entity = _norm_entity(q.split()[0]) if q else fallback
        if not entity:
            continue
        main = (entry.get("fact_main") or "").strip()
        sub = (entry.get("fact_sub") or "").strip()
        if not main:
            continue
        for metric, mpat, upat in _METRICS:
            m = re.search(rf"(?:{mpat})\D{{0,6}}({_NUM_RE})\s*({upat})", main)
            if not m:
                continue
            value = _norm_num(m.group(1))
            if value is None:
                continue
            out.append({
                "entity": entity,
                "metric": metric,
                "value": value,
                "unit": m.group(2),
                "period": extract_period(sub) or extract_period(main),
                "line": idx,
                "fact_main": main,
                "fact_sub": sub,
            })
            break  # 1 行につき 1 指標。最初にヒットしたものを採る
    return out


# ---------------------------------------------------------------------------
# 台帳の読み書き
# ---------------------------------------------------------------------------
def _ledger_path(channel_id: str) -> Path:
    return LEDGER_DIR / f"{channel_id}.json"


def load_ledger(channel_id: str) -> List[Dict[str, Any]]:
    path = _ledger_path(channel_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_ledger(channel_id: str, rows: List[Dict[str, Any]]) -> None:
    path = _ledger_path(channel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def record(channel_id: str, scenario: Dict[str, Any], *,
           title: str = "", source: str = "") -> int:
    """シナリオの数値主張を台帳に積む。同じ (会社,指標,値,期) は積み直さない。"""
    rows = load_ledger(channel_id)
    seen = {(r.get("entity"), r.get("metric"), r.get("value"), r.get("period"))
            for r in rows}
    added = 0
    for c in extract_claims(scenario):
        key = (c["entity"], c["metric"], c["value"], c["period"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "entity": c["entity"], "metric": c["metric"], "value": c["value"],
            "unit": c["unit"], "period": c["period"],
            "title": title or scenario.get("title") or "",
            "fact_main": c["fact_main"], "fact_sub": c["fact_sub"],
            "source": source,
        })
        added += 1
    if added:
        save_ledger(channel_id, rows)
    return added


# ---------------------------------------------------------------------------
# 照合
# ---------------------------------------------------------------------------
def check(channel_id: str, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    """台帳と突き合わせて矛盾を返す。

    `kind`:
      "conflict"  — 同じ期で値が違う。どちらかが誤り。人が直すしかない。
      "restate"   — 期が違うので両立するが、画面に期が無いと矛盾に見える。
    """
    rows = load_ledger(channel_id)
    if not rows:
        return []
    issues: List[Dict[str, Any]] = []
    for c in extract_claims(scenario):
        same_metric = [
            r for r in rows
            if r.get("entity") == c["entity"]
            and r.get("metric") == c["metric"]
            and r.get("unit") == c["unit"]
        ]
        if not same_metric:
            continue
        # 同じ期の記録が優先。台帳を先頭から舐めて最初の相違で打ち切ると、
        # たまたま先に並んでいた別の期の行を拾って「期違い」と誤判定する。
        same_period = [r for r in same_metric
                       if (r.get("period") or "") == (c["period"] or "")]
        if same_period:
            if any(r.get("value") == c["value"] for r in same_period):
                continue  # 同じ期・同じ値＝ただの再掲
            hit, kind = same_period[0], "conflict"
        else:
            diff = [r for r in same_metric if r.get("value") != c["value"]]
            if not diff:
                continue
            hit, kind = diff[0], "restate"
        issues.append({
            "kind": kind,
            "entity": c["entity"], "metric": c["metric"], "line": c["line"],
            "new_value": c["value"], "new_period": c["period"],
            "old_value": hit.get("value"), "old_period": hit.get("period"),
            "old_title": hit.get("title") or "",
            "unit": c["unit"],
        })
    return issues


def disclose_period(scenario: Dict[str, Any], issues: List[Dict[str, Any]]) -> int:
    """`restate` の行に期を注記して、視聴者から見た食い違いを解消する。

    「マクド 年収670万円」→「マクド 年収670万円（2024年12月期）」。
    期が違うから値が違うのだ、と画面上で分かるようにするだけで、値には触らない。
    """
    entries = scenario.get("short_scenario") or []
    fixed = 0
    for issue in issues:
        if issue["kind"] != "restate" or not issue.get("new_period"):
            continue
        i = issue["line"]
        if not (0 <= i < len(entries)) or not isinstance(entries[i], dict):
            continue
        period = issue["new_period"]
        label = (f"{period[:4]}年{int(period[5:])}月期"
                 if "-" in period else f"{period}年度")
        main = entries[i].get("fact_main") or ""
        if label in main:
            continue
        entries[i]["fact_main"] = f"{main}（{label}）"
        fixed += 1
    return fixed


def is_enforced(channel_raw: Dict[str, Any]) -> bool:
    cfg = (channel_raw or {}).get(CONFIG_KEY)
    return bool(isinstance(cfg, dict) and cfg.get("enabled"))
