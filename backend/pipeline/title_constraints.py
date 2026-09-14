"""title_constraints — タイトルの**機械ゲート**（正規表現バリデータ）。

背景（2026-09-04）:
    `short_format.extra_rules` / `theme_priority.title_style` に自然文で書いた
    タイトル規約は LLM に無視されることが実測で確定した。さらに
    `title_rules.require_*` は backend が一切読んでいない（09-03 の検証）。
    ＝「設定したのに何も起きていない」状態が続いていた。

    そこで規約を**決定論的な検査＋修復**に移す。ここを通らないタイトルは
    公開されない（LLM の再生成 → それでも駄目なら機械的に書き換える）。

チャンネル JSON のスキーマ（`title_rules.hard_constraints`）:

    "title_rules": {
      "enforced_by_backend": true,
      "hard_constraints": {
        "forbid_digits": true,            // 数字（半角・全角）を一切禁止
        "max_digit_groups": 1,            // 数字の「かたまり」の最大数
        "forbid_prefixes": ["なぜ"],      // この語で始まるタイトルを禁止
        "banned_words": ["〜について"],   // 含んではいけない語
        "forbid_patterns": [              // 任意の正規表現
          {"pattern": "#\\\\d+", "label": "連番"}
        ],
        "require_any_of": {               // 「必ず含む」制約（2026-09-09 追加）
          "label": "答え提示語",
          "words": ["理由", "正体", "本当の"],   // どれか1つを含むこと
          "repair_with": ["正体", "理由"]        // 機械修復で語尾に足す候補（名詞のみ）
        },
        "max_chars": 48,
        "min_effective_chars": 20        // ハッシュタグ・【】を除いた実効長の下限
      }
    }

    未設定のチャンネルは検査なし（挙動不変）。

`min_effective_chars` について（2026-09-11）:
    09-08 スナップショット n=330（views>0・全12ch）を実効文字数で刻むと、
    登録/千再生 は 0-14字 0.242 / 15-19字 0.279 / 20-24字 0.400 /
    **25-29字 0.637** / 30字以上 0.355 だった。短すぎるタイトルが最も弱く、
    25〜29字が頂点の逆U字。`title_rules.min_effective_chars_target` に
    自然文で書いてあった「実質20字以上」は backend が読まないため
    1本も効いていなかった（実測: 全330本中 112本＝34% が20字未満）。

    実効長は「ハッシュタグ（#〜）と【〜】を除いた残り」で数える。
    `#shorts #SCP #SCP解説` のような固定タグは全本に付くので、
    素の len() だと短いタイトルが長く見えてしまう。

    **機械修復はしない**（`repair` は触らない）。文字を足す修復は意味の
    ない水増しになるため、検査と advice（再生成）だけに留める。再生成2回で
    通らなければ違反として記録したまま公開される（呼び出し側の既存挙動）。

`require_any_of` について（2026-09-09）:
    09-08 の指揮者が `title_rules.require_answer_marker` に書いた「答え提示語を
    必ず入れる」は、**このモジュールが hard_constraints しか読まない**ため
    1行も効いていなかった（実測適合 61%）。禁止系しか表現できなかった
    スキーマに「必ず含む」を足す。

    照合は `jp_wordmatch` の語境界判定を使う。素の部分一致だと「理不尽」の
    「理」で『理由』が満たされたことになってしまう。

    機械修復は**語尾に足すだけ**。語順も助詞も動かさない（数字除去のときに
    「はで」「でずつ」のような助詞連結を3回作った前科があるため）。
    直前が動詞・形容詞の連体形なら直に、名詞なら「の」を挟んで繋ぐ。
    「なぜ」「実は」「本当の」のように語尾に置けない語は `repair_with` に
    入れないこと（検査側の `words` には入れてよい）。

公開 API:
    check(title, channel_dict)  -> {"ok": bool, "violations": [...], "advice": [...]}
    repair(title, channel_dict) -> str   # 機械的に直せる範囲で直した文字列
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:  # 語境界つきの語彙照合（→ pipeline/jp_wordmatch.py）
    from pipeline import jp_wordmatch as _jw
except ImportError:  # pragma: no cover
    import jp_wordmatch as _jw

# 半角・全角の数字。漢数字は「数字」に数えない（「一石二鳥」まで弾くのは行き過ぎ）。
#
# 2026-09-07 修正: 桁区切りコンマ・小数点・ハイフンで割れていた数字を1個に数える。
#   旧実装では「1,590円」「0.3秒」「SCP-2006」がそれぞれ2個の数字として数えられ、
#   max_digit_groups=1 のチャンネル（company-facts / daily-science / scp-lab）で
#   通常のタイトルが軒並み違反になっていた。「982万円」と「1,590円」は人間には
#   どちらも数字1つなので、区切り文字を跨いだ連なりを1グループとして扱う。
_DIGIT_RE = re.compile(r"[0-9０-９]")
_DIGIT_GROUP_RE = re.compile(r"[0-9０-９]+(?:[,，.．\-−―ー/／:：][0-9０-９]+)*")

# 数字を消すときに一緒に落とす助数詞・単位（残すと「つの妖怪」のような残骸になる）。
# 2026-09-07: 「名」を追加（「12名」→「名」が残っていた）。さらに序数の「目」を
# 助数詞のあとに許す（「3回目」→「目」が残っていた）。
_COUNTER = (r"(?:つ|個|件|人|名|匹|体|回|本|年|ヶ月|か月|カ月|ヵ月|月|日|時間|分|秒|"
            r"倍|割|％|%|パーセント|位|選|大|億|万|千|円|km|kg|cm|m|℃|度)?目?")
_DIGIT_PHRASE_RE = re.compile(
    r"[0-9０-９]+(?:[,，.．\-−―ー/／:：][0-9０-９]+)*" + _COUNTER + r"(?:の|は|が|を|も)?")

# 「なぜ」始まりの機械的な言い換えに使う。
_WHY_PREFIX_RE = re.compile(r"^\s*(?:なぜ|何故|なんで|どうして)\s*")
_WHY_TAIL_RE = re.compile(r"(?:のだろうか|のでしょうか|のだろう|のか|んだろう|んだ)?\s*[？?]?\s*$")

# 言い換え後に理由語が既にあるなら足さない。
# 「すでに答えを提示している」と見なす語。ここに入っている語がタイトルに
# あれば、機械修復は「本当の理由」を足さずにそのまま通す。
#
# 【2026-09-10】「秘密」を外した。09-09 の実測で 登録/千再生 0.120 と、
# 答え提示語あり全体（0.606）の 1/5・答え提示語なし（0.302）の 1/2.5 しかない。
# ここに残していると「…3つの秘密」で条件を満たしたことになり、効く語が
# 1つも足されないまま公開される。company-facts など6chは banned_words 側でも
# 「秘密」を禁止済みで、ここだけが素通し口になっていた。
_REASON_WORDS = ("理由", "正体", "真実", "からくり", "仕組み", "裏側")

# 動詞・形容詞の連体形で終わっているか（「出す」「多い」「消えた」）。
# 真なら「の」を挟まずに名詞を繋げる。
_RENTAI_TAIL_RE = re.compile(r"(?:[うくぐすつぬぶむる]|い|た|だ|ない|ている|てる)$")

# 実効長の計算で落とすもの: ハッシュタグ（#shorts 等）と【】ブロック（【ショート】等）。
# どちらも全本に機械的に付くため、素の len() では短いタイトルが長く見えてしまう。
#
# 2026-09-11 修正: `\S+` だと本文を巻き込んでいた。連番の「#5：あなたの操作は脳波で
# 読まれる」で `#5：あなたの操作は脳波で読まれる` が丸ごと消え、実効38字が21字と
# 数えられていた（analytics 上の実タイトル31本が影響）。ハッシュタグに全角/半角の
# コロンは入らないので、コロンと空白で止める。「#5」だけが落ちて本文は残る。
_HASHTAG_RE = re.compile(r"[#＃][^\s：:]*")
_BRACKET_RE = re.compile(r"【[^】]*】")

_WS_RE = re.compile(r"[ 　]{2,}")
_PUNCT_DUP_RE = re.compile(r"[、，,]{2,}")


# ---------------------------------------------------------------------
# 設定の読み出し
# ---------------------------------------------------------------------

def constraints_of(channel_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """チャンネル JSON から hard_constraints を取り出す。無ければ空 dict。"""
    tr = ((channel_dict or {}).get("title_rules") or {})
    hc = tr.get("hard_constraints")
    return hc if isinstance(hc, dict) else {}


def is_enforced(channel_dict: Optional[Dict[str, Any]]) -> bool:
    return bool(constraints_of(channel_dict))


# `repair()` が原理的に直せない規則（2026-09-11）。
#
# 文字数の**下限**は機械的に埋められない。埋めれば意味のない水増しになるので、
# min_effective_chars は検査と advice（LLM 再生成）だけに留めてある。
# 「repair の出力が全制約を満たすか」「キューの題材が制約を満たすか」を見る
# テストは、この集合を除外して判定すること（題材は最終タイトルではないため、
# 20字下限を題材に課すのは意味が無い — require_any_of と同じ理由）。
UNREPAIRABLE_RULES = frozenset({"min_effective_chars"})


def effective_len(title: str) -> int:
    """ハッシュタグと【】ブロックを除いたタイトルの実効文字数。

    2026-09-11 追加。`min_effective_chars` の判定に使う。
    """
    t = _BRACKET_RE.sub("", title or "")
    t = _HASHTAG_RE.sub("", t)
    # 2026-09-11: 文中のタグを抜いた跡に空白が残り、実効長を水増ししていた
    # （「あ×10 #tag あ×10」が 22 字と数えられた）。空白は1つに畳んでから数える。
    t = re.sub(r"[\s　]+", " ", t)
    return len(t.strip())


def _require_any_of(hc: Dict[str, Any]) -> Optional[Tuple[str, List[str], List[str]]]:
    """`require_any_of` を (ラベル, 必須語, 修復に使う語) に正規化する。

    リストだけの略記 `"require_any_of": ["理由", "正体"]` も受ける。その場合
    `repair_with` は必須語と同じ並びになる（語尾に置けない語が混ざっている
    ときは明示的に dict 形式で書くこと）。
    """
    spec = hc.get("require_any_of")
    if isinstance(spec, (list, tuple)):
        words = [str(w).strip() for w in spec if str(w or "").strip()]
        return ("必須語", words, list(words)) if words else None
    if not isinstance(spec, dict):
        return None
    words = [str(w).strip() for w in (spec.get("words") or []) if str(w or "").strip()]
    if not words:
        return None
    label = str(spec.get("label") or "必須語")
    repair_with = [str(w).strip() for w in (spec.get("repair_with") or [])
                   if str(w or "").strip()]
    return label, words, (repair_with or list(words))


# ---------------------------------------------------------------------
# 検査
# ---------------------------------------------------------------------

def check(title: str, channel_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """タイトルが hard_constraints を満たすか判定する。

    Returns:
        {"ok": bool, "violations": [{"rule","label","detail"}...], "advice": [str]}
    """
    hc = constraints_of(channel_dict)
    t = (title or "").strip()
    violations: List[Dict[str, str]] = []
    advice: List[str] = []
    if not hc or not t:
        return {"ok": True, "violations": [], "advice": []}

    if hc.get("forbid_digits"):
        found = _DIGIT_GROUP_RE.findall(t)
        if found:
            violations.append({"rule": "forbid_digits", "label": "数字禁止",
                               "detail": "/".join(found)})
            advice.append("タイトルに数字（半角・全角）を一切入れないこと。"
                          "本数・年号・パーセントも書かない。")
    else:
        try:
            max_groups = int(hc.get("max_digit_groups"))
        except (TypeError, ValueError):
            max_groups = -1
        if max_groups >= 0:
            found = _DIGIT_GROUP_RE.findall(t)
            if len(found) > max_groups:
                violations.append({"rule": "max_digit_groups",
                                   "label": f"数字は{max_groups}個まで",
                                   "detail": "/".join(found)})
                advice.append(f"タイトル内の数字は最大 {max_groups} 個。"
                              f"今は {len(found)} 個あるので余分な数字を削ること。")

    prefixes = hc.get("forbid_prefixes")
    if isinstance(prefixes, (list, tuple)):
        for p in prefixes:
            p = str(p or "").strip()
            if p and t.startswith(p):
                violations.append({"rule": "forbid_prefixes", "label": f"「{p}」始まり禁止",
                                   "detail": p})
                advice.append(f"「{p}」で始めないこと。断定形の名詞句で始める"
                              f"（例:「◯◯の本当の理由」）。")
                break

    banned = hc.get("banned_words")
    if isinstance(banned, (list, tuple)):
        hits = [str(w) for w in banned if str(w or "").strip() and str(w) in t]
        if hits:
            violations.append({"rule": "banned_words", "label": "禁止語",
                               "detail": "/".join(hits)})
            advice.append("次の語を使わないこと: " + " / ".join(hits))

    for spec in (hc.get("forbid_patterns") or []):
        if isinstance(spec, str):
            spec = {"pattern": spec}
        if not isinstance(spec, dict):
            continue
        pat = str(spec.get("pattern") or "")
        if not pat:
            continue
        try:
            if re.search(pat, t):
                label = str(spec.get("label") or pat)
                violations.append({"rule": "forbid_patterns", "label": label,
                                   "detail": pat})
                advice.append(f"「{label}」に当たる書き方をしないこと。")
        except re.error:
            continue

    req = _require_any_of(hc)
    if req is not None:
        label, words, _ = req
        if not _jw.any_word(t, words):
            violations.append({"rule": "require_any_of", "label": f"{label}が必須",
                               "detail": "/".join(words)})
            advice.append(
                f"{label}を必ず1つ入れること（{' / '.join(words)} のいずれか）。"
                f"語を入れるだけでなく、本編でその答えを言い切ること。"
                f"語順や助詞は自然な日本語のまま組み立て、不自然に貼り付けないこと。")

    try:
        max_chars = int(hc.get("max_chars"))
    except (TypeError, ValueError):
        max_chars = 0
    if max_chars > 0 and len(t) > max_chars:
        violations.append({"rule": "max_chars", "label": f"{max_chars}文字以内",
                           "detail": str(len(t))})
        advice.append(f"{max_chars}文字以内に収めること（今 {len(t)} 文字）。")

    # 短すぎるタイトルの下限（2026-09-11 追加）。ハッシュタグ・【】を除いた実効長で見る。
    try:
        min_eff = int(hc.get("min_effective_chars"))
    except (TypeError, ValueError):
        min_eff = 0
    if min_eff > 0:
        eff = effective_len(t)
        if eff < min_eff:
            violations.append({"rule": "min_effective_chars",
                               "label": f"実質{min_eff}文字以上",
                               "detail": str(eff),
                               "repairable": False})
            advice.append(
                f"ハッシュタグと【】を除いた本文が {min_eff} 文字以上になるまで書くこと"
                f"（今 {eff} 文字）。水増しではなく、具体名・数字・答えの手がかりを"
                f"1つ足して情報量を増やす。25〜29文字が最も登録に繋がる。")

    return {"ok": not violations, "violations": violations, "advice": advice}


# ---------------------------------------------------------------------
# 機械的な修復
# ---------------------------------------------------------------------

def _tidy(t: str) -> str:
    t = _WS_RE.sub(" ", t)
    t = _PUNCT_DUP_RE.sub("、", t)
    # 数字を抜いた跡に残る記号（#／第／No. の残骸、空の括弧、連続コロン）を掃除する。
    t = re.sub(r"[#＃]\s*(?=[：:、，,。\s]|$)", "", t)
    t = re.sub(r"第\s*(?=[：:、，,。\s]|$)", "", t)
    t = re.sub(r"(?i)no\.?\s*(?=[：:、，,。\s]|$)", "", t)
    t = re.sub(r"[（(【\[]\s*[)）】\]]", "", t)
    t = re.sub(r"[：:]{2,}", "：", t)
    t = re.sub(r"\s*([：:])\s*", r"\1", t)
    t = re.sub(r"\s*[：:]\s*(?=[、，,。]|$)", "", t)
    t = re.sub(r"^[、，,。・：:\-—！!？?\s]+", "", t)
    # 末尾に取り残された助詞・接続詞（「〜と」「〜の」）も落とす。
    t = re.sub(r"[、，,・：:\-—\s]+$", "", t)
    t = re.sub(r"(?:と|や|の|は|が|を|に|で)$", "", t)
    t = re.sub(r"[、，,・：:\-—\s]+$", "", t)
    return t.strip()


def strip_digits(title: str) -> str:
    """数字（と直後の助数詞）を落とす。"""
    return _tidy(_DIGIT_PHRASE_RE.sub("", title or ""))


def limit_digit_groups(title: str, max_groups: int) -> str:
    """先頭から `max_groups` 個の数字だけ残し、それ以降の数字句を落とす。"""
    t = title or ""
    kept = 0
    out: List[str] = []
    pos = 0
    for m in _DIGIT_PHRASE_RE.finditer(t):
        out.append(t[pos:m.start()])
        if kept < max_groups:
            out.append(m.group(0))
            kept += 1
        pos = m.end()
    out.append(t[pos:])
    return _tidy("".join(out))


def rewrite_why(title: str) -> str:
    """「なぜ〜のか？」を断定形の名詞句に機械的に言い換える。

    例: 「なぜ妖怪は夜に出るのか？」→「妖怪が夜に出る本当の理由」
    """
    t = (title or "").strip()
    if not _WHY_PREFIX_RE.match(t):
        return t
    body = _WHY_PREFIX_RE.sub("", t)
    body = _WHY_TAIL_RE.sub("", body).strip()
    # 「〜するの」の余った「の」を落としてから理由句を足す（「出すの本当の理由」対策）。
    body = re.sub(r"[のん]$", "", body).strip()
    if not body:
        return t
    # 主題の「は」は名詞句にすると座りが悪い。既に「が」がある文は「の」に、
    # 無ければ「が」に寄せる（「イーブイが進化先が多い」のような二重ガ格を避ける）。
    if "は" in body:
        body = body.replace("は", "の" if "が" in body else "が", 1)
    if not any(w in body for w in _REASON_WORDS):
        # 動詞・形容詞で終わる連体形にはそのまま繋ぐ（「出すの本当の理由」を防ぐ）。
        body += ("本当の理由" if _RENTAI_TAIL_RE.search(body) else "の本当の理由")
    return _tidy(body)


# 語尾の記号（疑問符・句点・感嘆符）。必須語を足す前に落とす。
_TAIL_MARK_RE = re.compile(r"[。．\.！!？?〜~…・\s]+$")

# 末尾に半端に残ったハッシュタグ（「#s」「#shor」）。
_PARTIAL_HASHTAG_RE = re.compile(r"\s*[#＃][^\s#＃]*$")


def _trim_to(t: str, limit: int) -> str:
    """`limit` 文字に詰める。ハッシュタグの途中で切らない。

    ここに来るタイトルは通常ハッシュタグを含まない（本文とタグは
    description_generator が後段で合成する）。ただし手動経路や再投稿で
    タグ込みの文字列が渡ることがあり、素朴な `t[:limit]` は「#shor」
    「#sの真相」のような残骸を作る。
    """
    if limit <= 0:
        return ""
    cut = (t or "")[:limit]
    if len(t or "") > limit and _PARTIAL_HASHTAG_RE.search(cut):
        cut = _PARTIAL_HASHTAG_RE.sub("", cut)
    return _tidy(cut)


def append_required_word(title: str, word: str) -> str:
    """`word` をタイトルの**語尾に足すだけ**の修復。語順も助詞も動かさない。

    「氷が水に浮く」＋「理由」→「氷が水に浮く理由」（連体形に直付け）
    「猫の瞳孔」    ＋「正体」→「猫の瞳孔の正体」  （名詞なので「の」を挟む）

    「の」を機械的に挟むと「出すの理由」になり、挟まないと「瞳孔正体」になる。
    どちらも実際に出た壊れ方なので、直前が用言の連体形かどうかだけで分ける。
    """
    t = _TAIL_MARK_RE.sub("", (title or "").strip())
    # 「〜とは？」型の語尾に名詞を足すと「とはの処方箋」になる。「とは」は落とす。
    t = re.sub(r"(?:とは|って)$", "", t).rstrip("、，,")
    w = (word or "").strip()
    if not t or not w:
        return (title or "").strip()
    if _jw.contains_word(t, w):
        return t
    # 既に「の」で終わっているならもう一度「の」は足さない（「本当のの正体」）。
    if t.endswith("の"):
        return t + w
    return t + (w if _RENTAI_TAIL_RE.search(t) else "の" + w)


def repair(title: str, channel_dict: Optional[Dict[str, Any]] = None) -> str:
    """違反を機械的に直せる範囲で直した文字列を返す（直せなければ元のまま）。

    LLM 再生成が失敗した場合の最終手段。意味は多少痩せるが、規約違反のまま
    公開するよりは良い、という判断。
    """
    hc = constraints_of(channel_dict)
    t = (title or "").strip()
    if not hc or not t:
        return t

    prefixes = [str(p) for p in (hc.get("forbid_prefixes") or [])]
    if any(t.startswith(p) for p in prefixes if p):
        if any(p in ("なぜ", "何故", "なんで", "どうして") for p in prefixes):
            t = rewrite_why(t)
        else:
            for p in prefixes:
                if p and t.startswith(p):
                    t = _tidy(t[len(p):])
                    break

    if hc.get("forbid_digits"):
        t = strip_digits(t)
    else:
        try:
            max_groups = int(hc.get("max_digit_groups"))
        except (TypeError, ValueError):
            max_groups = -1
        if max_groups >= 0 and len(_DIGIT_GROUP_RE.findall(t)) > max_groups:
            t = limit_digit_groups(t, max_groups)

    for w in (hc.get("banned_words") or []):
        w = str(w or "")
        if w and w in t:
            t = _tidy(t.replace(w, ""))

    # 2026-09-14 追加: forbid_patterns を repair が一切見ていなかった。
    # 実測: company-facts「コメダ珈琲がFC比率99%にする本当の理由とは」が
    # `check` で ok:false（99%が知らない型の希少性ワード）と判定されながら、
    # LLM再生成2回も repair も 99% を落とせず、違反したまま 09-13 23:15 に公開された。
    # （data/scenarios/company-facts/…json の title_constraints に記録が残っている）
    # 一致箇所を落として掃除する。落とした結果が壊れた日本語なら、この関数の
    # 末尾の `_is_broken_japanese` ガードが原文を返すので、最悪でも現状維持。
    for spec in (hc.get("forbid_patterns") or []):
        pat = (spec or {}).get("pattern") if isinstance(spec, dict) else spec
        if not pat:
            continue
        try:
            rx = re.compile(pat)
        except re.error:
            continue
        if rx.search(t):
            stripped = _tidy(rx.sub("", t))
            if len(stripped) >= 8:
                t = stripped

    try:
        max_chars = int(hc.get("max_chars"))
    except (TypeError, ValueError):
        max_chars = 0

    # 「必ず含む」は最後に処理する。先に足すと max_chars のトリムで語尾ごと
    # 削られて、また違反に戻ってしまう。
    req = _require_any_of(hc)
    if req is not None:
        _, words, repair_with = req
        if not _jw.any_word(t, words):
            for w in repair_with:
                # 足したぶんが max_chars を超えないよう、本体を先に詰めておく。
                body = t
                if max_chars > 0 and len(body) + len(w) + 1 > max_chars:
                    body = _trim_to(body, max_chars - len(w) - 1)
                cand = append_required_word(body, w)
                if not cand or len(cand) < 8:
                    continue
                if _is_broken_japanese(cand, t):
                    continue
                sub = check(cand, channel_dict)
                # 追加した語自体が他の制約（禁止語・数字・パターン）に触れたら次の候補へ。
                #
                # 2026-09-11: 許容する規則に UNREPAIRABLE_RULES を足した。
                # min_effective_chars（実効長の下限）を入れた直後、語を足した候補が
                # 「まだ20字に届かない」だけで棄却され、repair が原文を返すように
                # なっていた（＝答え提示語の修復が全chで死んだ）。長さ不足は語を
                # 足しても解消しないので、ここで候補を棄却する理由にはならない。
                _ignorable = {"require_any_of"} | set(UNREPAIRABLE_RULES)
                if sub["ok"] or all(v["rule"] in _ignorable for v in sub["violations"]):
                    t = cand
                    break

    if max_chars > 0 and len(t) > max_chars:
        t = _trim_to(t, max_chars)

    # 削りすぎて意味を成さなくなったら元に戻す（違反のままだが空よりまし）。
    if len(t) < 8:
        return (title or "").strip()
    if _is_broken_japanese(t, title or ""):
        # 2026-09-07 追加。数字を抜いた跡に助詞が衝突して日本語として壊れる例が
        # 実測で出た（「ピカチュウは10%なのに」→「ピカチュウはなのに」、
        # 「元ネタは3つある」→「元ネタはある」、「3回目の店」→「目の店」）。
        # 規約違反のタイトルより壊れた日本語のほうが視聴者への害が大きいので、
        # そのときは修復を諦めて原文を返す（呼び出し側は「未解消」として記録する）。
        return (title or "").strip()
    return t


# 数字を抜いた跡に残りやすい壊れ方（助詞の直後に助詞・述語が来る、文頭が助数詞）。
_BROKEN_PATTERNS = (
    re.compile(r"[はがをにでとも](?:ある|いる|なの|だっ|する|した|なっ|より|など|くらい|ほど)"),
    re.compile(r"[はがをにでとも][はがをにでとも、，,。]"),
    re.compile(r"^(?:つ|個|件|人|匹|体|回|本|年|月|日|時間|分|秒|倍|割|位|選|億|万|千|円)"),
    re.compile(r"[、，,][はがをにでとも]"),
)


def _broken_spans(t: str) -> List[str]:
    spans: List[str] = []
    for p in _BROKEN_PATTERNS:
        spans.extend(m.group(0) for m in p.finditer(t or ""))
    return spans


def _is_broken_japanese(repaired: str, original: str) -> bool:
    """**修復が壊した**なら True（元から入っていた並びは咎めない）。

    完全な文法判定はしない。数字除去で実際に起きた壊れ方だけを見る:
      1) 助詞のあとに述語や助詞が直接続く（「元ネタはある」「ピカチュウはなのに」）
      2) 助数詞から始まってしまう（「目の店謎の予約名」）

    削れた量そのものは判定に使わない。forbid_digits のチャンネルでは大きく削るのが
    正常なので、長さ比で弾くと本来きれいに直せる修復まで捨ててしまう。

    2026-09-09 修正: `original` を受け取っておきながら見ていなかったため、
    **元の文に普通に入っている並び**で誤爆していた。「子どもを」は規則2
    （も＋を）に、「になった」は規則1（に＋なっ）に当たる。結果として
    「ドラパルト、子どもを音速超えで撃ち出す」「鬼の角が目印になった千年前の
    変化」のような正常なタイトルは**どんな修復も一律に捨てられていた**
    （数字除去の修復も同様に効いていなかった）。原文に無い並びが
    新しく生まれたときだけ壊れたと見なす。
    """
    r = (repaired or "").strip()
    if not r:
        return True
    new = _broken_spans(r)
    if not new:
        return False
    old = _broken_spans((original or "").strip())
    for span in old:
        if span in new:
            new.remove(span)
    return bool(new)


def violation_summary(result: Dict[str, Any]) -> str:
    return " / ".join(f"{v['label']}({v['detail']})" for v in result.get("violations") or [])
