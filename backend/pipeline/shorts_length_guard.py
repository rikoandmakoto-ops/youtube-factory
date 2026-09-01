"""ショート動画の完視聴率最適化ガード。

【2026-08-27 実測ベースに改訂】
以前のこのモジュールは「30〜45秒が解説ショートの最適帯／30秒未満はリーチが減る」
という 2026-08-19 時点の仮説をハードコードしていた。その仮説は 08-25 の実測で
否定され、channel JSON 側の `short_format`（6行175〜225字 ≒ 26秒）と
generator 側の SHORT_TARGET_CHARS=200 は短尺に差し戻されたが、このガードだけが
旧帯（30〜55秒）に取り残されていた。結果、規約どおりに書かれた台本が毎回
「最適帯の下限を下回る」と警告され、suggestion が「40字加筆しろ」と
実測で否定された方向を勧め続けていた。

実測（日次 n=14、2026-08-19〜25）:
  - 6行193字 → 8行372字 に伸ばした結果、維持率中央値 54.3% → 29.8% に半減
  - 平均視聴秒数は前後とも 15〜16 秒で不変（＝視聴者は尺に関係なく15秒で離脱）
  - 公開3日後の再生中央値は全5chで 24〜80% 減
  - 台本字数 × 維持率 の相関 r = -0.849
  - 回帰 維持率(%) = 89.0 - 0.1612 × 字数
  - 維持率が最も高かったのは 173〜202 字帯

したがって最適帯の一次情報は「秒」ではなく「台本の総文字数」であり、その値は
すでに channel JSON の `short_format.total_chars_min/max` にある。このモジュールは
独自の帯を持たず、そこから帯を引く（＝二重管理をやめる）。channel JSON に
`short_format` が無いチャンネルだけ CHANNEL_CHAR_BAND / DEFAULT_CHAR_BAND に
フォールバックする。

このモジュールは:
1. 生成されたシナリオの文字数から推定尺・推定維持率を算出
2. チャンネルの最適文字数帯に収まっているか検証
3. 収まっていなければ警告を出し、修正ヒントを返す
4. video_generator から呼ばれ、尺が許容範囲外なら再生成を促す
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# VOICEVOX 1.3x の実効読み上げ速度（字/秒）
VOICEVOX_CHARS_PER_SEC = 8.9

# 話速・話者が既定（1.3x のゆっくり系）と違うチャンネルの実効読み上げ速度。
# ここを外すと推定尺が実尺の 6 割になり、ガードが逆方向の加筆を勧めてくる。
# akashic-librarian: 離途(101) speed=1.15 を実測して 5.43 字/秒。
CHANNEL_CHARS_PER_SEC: Dict[str, float] = {
    "akashic-librarian": 5.43,
}


def chars_per_sec_for(channel_id: str) -> float:
    """チャンネルの実効読み上げ速度（字/秒）。未登録なら既定値。"""
    return CHANNEL_CHARS_PER_SEC.get(channel_id, VOICEVOX_CHARS_PER_SEC)


# エンドカードの秒数
ENDCARD_SECONDS = 1.6

# 行間のポーズ（秒/行）
PAUSE_SECONDS_PER_LINE = 0.3

# ── 最適帯（台本の総文字数） ──────────────────────────────────────
# 一次情報は channel JSON の `short_format.total_chars_min/max`。
# 以下は short_format を宣言していないチャンネル向けのフォールバックで、
# 08-25 実測の「維持率が最も高かった 173〜202 字帯」を中心に取る。
CHANNEL_CHAR_BAND: Dict[str, Tuple[int, int]] = {
    "daily-science": (175, 225),
    "scp-lab": (165, 210),
    "2ch-matome": (165, 210),
    "company-facts": (165, 225),
    "pokemon-lab": (175, 225),
    "yokai-watch": (175, 225),
    "akashic-librarian": (165, 195),
    "fake-paper": (235, 275),
}

# short_format も CHANNEL_CHAR_BAND も無いチャンネルの既定帯
DEFAULT_CHAR_BAND = (165, 235)

# 維持率の実測回帰（2026-08-25、日次 n=14、r=-0.849）:
#   維持率(%) = RETENTION_INTERCEPT - RETENTION_SLOPE × 台本総文字数
# 370字→29.4%（実測29.3〜29.8%）、180字→60.0%（実測60.2〜72.2%）を再現する。
RETENTION_INTERCEPT = 89.0
RETENTION_SLOPE = 0.1612

# 秒 → 字 の逆算に使う名目行数（estimate_completion_rate の後方互換用）。
# 実測帯の台本はほぼ 6 行なのでその固定オーバーヘッドで割り戻す。
_NOMINAL_LINE_COUNT = 6

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHANNELS_DIR = PROJECT_ROOT / "data" / "channels"

_short_format_cache: Dict[str, Dict[str, Any]] = {}


def _load_short_format(channel_id: str) -> Dict[str, Any]:
    """channel JSON の `short_format` を読む（見つからなければ空 dict）。"""
    if not channel_id:
        return {}
    if channel_id in _short_format_cache:
        return _short_format_cache[channel_id]
    sf: Dict[str, Any] = {}
    try:
        path = CHANNELS_DIR / f"{channel_id}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            cand = raw.get("short_format")
            if isinstance(cand, dict):
                sf = cand
    except Exception:
        sf = {}
    _short_format_cache[channel_id] = sf
    return sf


def char_band_for(channel_id: str) -> Tuple[int, int]:
    """チャンネルの最適台本文字数帯 (min, max)。

    優先順: channel JSON の short_format → CHANNEL_CHAR_BAND → DEFAULT_CHAR_BAND。
    """
    sf = _load_short_format(channel_id)
    lo = sf.get("total_chars_min")
    hi = sf.get("total_chars_max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi > lo > 0:
        return int(lo), int(hi)
    return CHANNEL_CHAR_BAND.get(channel_id, DEFAULT_CHAR_BAND)


def overhead_seconds(line_count: int, *, endcard_seconds: float = ENDCARD_SECONDS) -> float:
    """発話以外の固定尺（行間ポーズ + エンドカード）。"""
    return line_count * PAUSE_SECONDS_PER_LINE + endcard_seconds


def duration_band_for(
    channel_id: str,
    line_count: int,
    *,
    endcard_seconds: float = ENDCARD_SECONDS,
) -> Tuple[float, float]:
    """文字数帯を、その行数での推定秒数帯に変換する。"""
    lo_chars, hi_chars = char_band_for(channel_id)
    cps = chars_per_sec_for(channel_id)
    over = overhead_seconds(line_count, endcard_seconds=endcard_seconds)
    return lo_chars / cps + over, hi_chars / cps + over


def estimate_duration(
    scenario: List[Dict[str, Any]],
    *,
    endcard_seconds: float = ENDCARD_SECONDS,
    chars_per_sec: float = VOICEVOX_CHARS_PER_SEC,
) -> float:
    """シナリオの推定再生時間（秒）を返す。"""
    total_chars = sum(len(line.get("text", "")) for line in scenario)
    speech_seconds = total_chars / chars_per_sec
    return speech_seconds + overhead_seconds(len(scenario), endcard_seconds=endcard_seconds)


def estimate_completion_rate_from_chars(total_chars: int) -> float:
    """台本総文字数から推定維持率を返す（0.0〜1.0）。

    08-25 実測の回帰式そのもの。維持率の主因は秒ではなく字数（＝情報量）で、
    視聴者は尺に関係なく 15 秒前後で離脱するため、字数を増やすほど
    「見られた割合」が薄まる、という観測に対応する。
    """
    pct = RETENTION_INTERCEPT - RETENTION_SLOPE * max(0, total_chars)
    return max(0.0, min(1.0, pct / 100.0))


def estimate_completion_rate(
    duration_seconds: float,
    *,
    chars_per_sec: float = VOICEVOX_CHARS_PER_SEC,
) -> float:
    """推定完視聴率を返す（0.0〜1.0）。

    後方互換のため秒を受けるが、中身は字数ベースの実測回帰。名目6行の
    固定オーバーヘッドを引いてから字数に割り戻す。
    """
    speech = duration_seconds - overhead_seconds(_NOMINAL_LINE_COUNT)
    return estimate_completion_rate_from_chars(int(max(0.0, speech) * chars_per_sec))


def check_scenario(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    *,
    endcard_seconds: float = ENDCARD_SECONDS,
) -> Dict[str, Any]:
    """シナリオの尺を検証し、結果を返す。

    判定は「台本の総文字数」で行い、秒は表示・ログ用に併記する
    （実測で維持率と相関していたのは字数のほうであるため）。

    Returns:
        {
            "ok": bool,
            "estimated_seconds": float,
            "estimated_completion_rate": float,
            "total_chars": int,
            "line_count": int,
            "chars_min": int,
            "chars_max": int,
            "range_min": float,   # chars_min をこの行数で秒に直した値
            "range_max": float,
            "warning": Optional[str],
            "suggestion": Optional[str],
        }
    """
    chars_min, chars_max = char_band_for(channel_id)
    cps = chars_per_sec_for(channel_id)
    est_seconds = estimate_duration(
        scenario, endcard_seconds=endcard_seconds, chars_per_sec=cps,
    )
    total_chars = sum(len(line.get("text", "")) for line in scenario)
    est_cr = estimate_completion_rate_from_chars(total_chars)
    range_min, range_max = duration_band_for(
        channel_id, len(scenario), endcard_seconds=endcard_seconds,
    )

    result: Dict[str, Any] = {
        "ok": True,
        "estimated_seconds": round(est_seconds, 1),
        "estimated_completion_rate": round(est_cr, 2),
        "total_chars": total_chars,
        "line_count": len(scenario),
        "chars_min": chars_min,
        "chars_max": chars_max,
        "range_min": round(range_min, 1),
        "range_max": round(range_max, 1),
        "warning": None,
        "suggestion": None,
    }

    if total_chars < chars_min:
        chars_needed = chars_min - total_chars
        result["ok"] = False
        result["warning"] = (
            f"{total_chars}字 / 推定 {est_seconds:.0f}秒 — 最適帯の下限 {chars_min}字 "
            f"({range_min:.0f}秒) を下回る"
        )
        result["suggestion"] = (
            f"総文字数を約 {chars_needed} 字増やして {chars_min}字以上にする。"
            f"1行あたり {chars_needed // max(1, len(scenario))} 字程度の加筆で達成可能。"
        )
    elif total_chars > chars_max:
        chars_over = total_chars - chars_max
        result["ok"] = False
        result["warning"] = (
            f"{total_chars}字 / 推定 {est_seconds:.0f}秒 — 最適帯の上限 {chars_max}字 "
            f"({range_max:.0f}秒) を超過 (推定維持率 {est_cr:.0%} に低下)"
        )
        result["suggestion"] = (
            f"総文字数を約 {chars_over} 字削って {chars_max}字以下にする。"
            f"1行あたり {chars_over // max(1, len(scenario))} 字程度の削減で達成可能。"
            f"（08-25 実測: 字数×維持率 r=-0.849。加筆ではなく削減が正しい方向）"
        )
    elif total_chars > chars_max - 15:
        # 上限に近い場合は注意喚起
        result["warning"] = (
            f"{total_chars}字 — 上限 {chars_max}字 に近い。"
            f"あと {chars_max - total_chars}字 余裕。"
        )

    return result


def guard(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    """パイプライン統合用エントリポイント。

    strict=True の場合、範囲外なら例外を送出する（再生成のトリガー用）。
    strict=False（デフォルト）の場合、警告をログに出すだけで通す。
    """
    result = check_scenario(channel_id, scenario)

    if result["warning"]:
        print(
            f"  ⏱️ ShortsLengthGuard [{channel_id}]: {result['warning']}"
        )
    if result["suggestion"]:
        print(
            f"     💡 {result['suggestion']}"
        )

    if not result["ok"] and strict:
        raise ValueError(
            f"ShortsLengthGuard: {channel_id} の台本 {result['total_chars']}字 が "
            f"最適帯 {result['chars_min']}〜{result['chars_max']}字 "
            f"({result['range_min']:.0f}〜{result['range_max']:.0f}秒) の範囲外。"
            f"{result.get('suggestion', '')}"
        )

    print(
        f"  ⏱️ ShortsLengthGuard [{channel_id}]: "
        f"{result['total_chars']}字 / {result['estimated_seconds']:.0f}秒 / "
        f"推定維持率 {result['estimated_completion_rate']:.0%} — "
        f"{'✅ OK' if result['ok'] else '⚠️ 範囲外'}"
    )

    return result


# ---------------------------------------------------------------------------
# 上限超過の実強制（2026-08-30 追加）
# ---------------------------------------------------------------------------
# 背景: 08-25 に channel JSON の short_format を 175〜225字 に差し戻したにも
# かかわらず、08-26〜29 に公開された台本の実測中央値は 238〜304字 と依然 13〜45%
# 超過していた。原因は 2 つ:
#   (1) 字数制約が LLM プロンプト内の日本語文字列でしか表現されておらず、
#       生成後の検証はすべて strict=False（警告printのみ／再生成もトリムも無し）。
#   (2) generator の Round6/7/8 エンハンサー群が短尺台本を **in-place で加筆** し、
#       しかもその実行が check_scenario の後に来るため、ガードを通過した台本に
#       後から 24〜103字（scp-lab では総字数の 33.9%）が積み増しされていた。
# 実測回帰 維持率 = 89.0 - 0.1612×字数 では、250字→48.7%、300字→40.6% に対し
# 200字→56.8%。08-19〜29 の実測維持率中央値は 26〜33% まで落ちている。
# ここでは「生成をやり直さず、決定論的に帯へ戻す」最終段を提供する。再生成は
# API コストと失敗リスクを伴い、深夜の無人実行で動画本数がゼロになりうるため、
# 常に出力を返すトリムを選ぶ。
# ---------------------------------------------------------------------------

# 行の途中で切らないための区切り文字（優先度順）。
_SENTENCE_BREAKS = ("。", "！", "？", "!", "?")
# エンハンサー注入の連結に使われる記号。
_INJECT_SEP = "…"
# トリム後もこの字数は各行に残す（短すぎる行は読み上げが不自然になる）。
_MIN_LINE_CHARS = 14


def _strip_injected_tail(text: str) -> str:
    """行末に連結されたエンハンサー注入句を 1 つ落とす。

    Round6/7/8 の injector は本文に「…追記」の形で連結する。最後の「…」以降を
    落とすと、LLM が生成した本体に近づく。先頭セグメントは常に残す。
    """
    if _INJECT_SEP not in text:
        return text
    head, _, _tail = text.rpartition(_INJECT_SEP)
    head = head.rstrip(_INJECT_SEP).rstrip()
    return head if len(head) >= _MIN_LINE_CHARS else text


def _drop_last_sentence(text: str) -> str:
    """行末の 1 文を落とす（文境界が無ければ変更しない）。"""
    best = -1
    for br in _SENTENCE_BREAKS:
        idx = text.rstrip().rfind(br)
        # 末尾そのものの句点は「最後の文の終わり」なので 1 つ内側を探す
        if idx == len(text.rstrip()) - 1:
            idx = text.rstrip()[:idx].rfind(br)
        best = max(best, idx)
    if best <= 0:
        return text
    cand = text[: best + 1].rstrip()
    return cand if len(cand) >= _MIN_LINE_CHARS else text


def _drop_last_clause(text: str) -> str:
    """行末の 1 節を読点「、」で落とす。

    【2026-08-31 追加】注入句除去・末尾文除去だけでは削り切れない台本が残っていた。
    08-24〜30 の実台本76本に適用した回帰では、この2段だけだと 62本中33本が
    上限超過のまま残る（1行が読点だけで繋がった長い一文になっている場合、
    文境界が見つからず両方とも「変更なし」を返してループが止まるため）。
    最後の手段として読点で節を落とし、それでも駄目なら諦めて警告を出す。
    """
    stripped = text.rstrip()
    idx = stripped.rfind("、")
    if idx <= 0:
        return text
    cand = stripped[:idx].rstrip()
    if len(cand) < _MIN_LINE_CHARS:
        return text
    # 文末が体言止め・読点切れにならないよう句点で締める
    if not cand.endswith(_SENTENCE_BREAKS):
        cand += "。"
    return cand


def enforce_band(
    channel_id: str,
    scenario: List[Dict[str, Any]],
    *,
    protect_first: bool = True,
    protect_last: bool = True,
) -> Dict[str, Any]:
    """短尺台本を文字数帯の **上限以下** に決定論的に収める（in-place）。

    下限割れは何もしない（加筆は実測で否定された方向のため）。上限超過のみ、
    以下の順で削る。どの段階でも下限 chars_min を割らないよう停止する。

      1. 中間行に連結されたエンハンサー注入句（「…」以降）を、長い行から除去
      2. まだ超過していれば、中間行の末尾 1 文を長い行から順に除去
      3. それでも超過し protect_last=False なら最終行にも同じ処理を適用

    1行目（フック）は最初の 3 秒を決めるため既定で保護。最終行（CTA）は登録
    導線のため既定で保護する。

    Args:
        scenario: 行 dict のリスト（"text" キー）。**破壊的に変更される**。
        protect_first: 1行目を削らない。
        protect_last: 最終行を削らない。

    Returns:
        {"applied": bool, "before_chars": int, "after_chars": int,
         "chars_min": int, "chars_max": int, "removed_chars": int,
         "steps": [str], "lines_changed": int}
    """
    chars_min, chars_max = char_band_for(channel_id)
    texts = [str(line.get("text", "")) for line in scenario]
    before = sum(len(t) for t in texts)
    report: Dict[str, Any] = {
        "applied": False,
        "before_chars": before,
        "after_chars": before,
        "chars_min": chars_min,
        "chars_max": chars_max,
        "removed_chars": 0,
        "steps": [],
        "lines_changed": 0,
    }
    n = len(texts)
    if n == 0 or before <= chars_max:
        return report

    lo = 1 if (protect_first and n > 1) else 0
    hi = (n - 1) if (protect_last and n > 2) else n
    editable = list(range(lo, hi))
    if not editable:
        return report

    def total() -> int:
        return sum(len(t) for t in texts)

    for label, op in (
        ("注入句除去", _strip_injected_tail),
        ("末尾文除去", _drop_last_sentence),
        ("末尾節除去", _drop_last_clause),
    ):
        changed = True
        while total() > chars_max and changed:
            changed = False
            # 長い行から削る（維持率への寄与が大きい順）
            for i in sorted(editable, key=lambda k: len(texts[k]), reverse=True):
                if total() <= chars_max:
                    break
                new = op(texts[i])
                if new == texts[i]:
                    continue
                # 下限を割るなら、この削除は行わない
                if total() - (len(texts[i]) - len(new)) < chars_min:
                    continue
                report["steps"].append(
                    f"L{i + 1} {label}: {len(texts[i])}字→{len(new)}字"
                )
                texts[i] = new
                changed = True

    after = total()
    if after == before:
        return report

    original = [str(line.get("text", "")) for line in scenario]
    changed_lines = sum(1 for a, b in zip(original, texts) if a != b)
    for line, t in zip(scenario, texts):
        line["text"] = t

    report.update(
        applied=True,
        after_chars=after,
        removed_chars=before - after,
        lines_changed=changed_lines,
    )
    print(
        f"  ✂️ ShortsLengthGuard [{channel_id}]: エンハンサー後 {before}字 → {after}字 "
        f"(上限 {chars_max}字 / 推定維持率 "
        f"{estimate_completion_rate_from_chars(before):.0%} → "
        f"{estimate_completion_rate_from_chars(after):.0%})"
    )
    if after > chars_max:
        print(
            f"     ⚠️ 下限 {chars_min}字 の制約により上限まで削り切れず（{after}字）。"
            f"プロンプト側の短縮が必要。"
        )
    return report
