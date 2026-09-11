"""2026-09-11 指揮者タスクの修正点の回帰テスト。

  1. title_constraints.min_effective_chars — 短すぎるタイトルの機械ゲート
  2. effective_len — ハッシュタグ・【】を実効長から除く
  3. 未設定チャンネルの挙動不変（既存chを壊さない）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import title_constraints as tc  # noqa: E402


# ---------------------------------------------------------------------
# 1. effective_len
# ---------------------------------------------------------------------

def test_effective_len_strips_hashtags_and_brackets():
    # 素の len() なら 40 文字を超えるが、実効は本文だけ
    t = "下りだけ段が消える #shorts #架空論文"
    assert tc.effective_len(t) == len("下りだけ段が消える")

    t2 = "なぜ座ると腰だけ痛い？圧力1.4倍【ショート】"
    assert tc.effective_len(t2) == len("なぜ座ると腰だけ痛い？圧力1.4倍")

    t3 = "SCP-3288 大雨の真相 あなたの部屋も沈む #shorts #SCP #SCP解説"
    assert tc.effective_len(t3) == len("SCP-3288 大雨の真相 あなたの部屋も沈む")


def test_effective_len_does_not_swallow_body_after_a_serial_number():
    """`#5：本文` の形で本文を巻き込まないこと（2026-09-11 の検証で発覚）。

    旧実装 `[#＃]\\S+` は空白まで貪欲に食うため、
    「#5：あなたの操作は脳波で読まれる」が丸ごと消えて実効38字が21字になっていた。
    ハッシュタグに全角/半角コロンは入らないので、コロンで止める。
    連番の `#5` 自体は本文ではない（連番プレフィックスは禁止済み）ので落として良い。
    """
    t = "架空論文ファイル #5：あなたの操作は脳波で読まれる — 2,184人の記録【ショート】"
    # 【ショート】と "#5" だけが落ち、本文は残る
    assert tc.effective_len(t) == len("架空論文ファイル ：あなたの操作は脳波で読まれる — 2,184人の記録")
    assert tc.effective_len(t) > 30, "本文が巻き込まれている"


def test_effective_len_collapses_whitespace_left_by_a_midstring_tag():
    """文中タグを抜いた跡の空白で実効長が水増しされないこと。

    旧実装では strip() が両端しか落とさないため「あ×10 #tag あ×10」が 22 字だった。
    語を隔てる空白1つは本文の一部として残す（= 21 字）。
    """
    t = "あ" * 10 + " #tag " + "あ" * 10
    assert tc.effective_len(t) == 21
    # 末尾タグだけの通常ケースは影響を受けない
    assert tc.effective_len("あ" * 20 + " #shorts") == 20
    assert tc.effective_len("あ" * 20 + "　#shorts　#SCP") == 20


def test_effective_len_empty_and_none():
    assert tc.effective_len("") == 0
    assert tc.effective_len(None) == 0
    assert tc.effective_len("#shorts #SCP") == 0


# ---------------------------------------------------------------------
# 2. min_effective_chars ゲート
# ---------------------------------------------------------------------

CH = {"title_rules": {"hard_constraints": {"min_effective_chars": 20}}}


def test_min_effective_chars_rejects_short_title():
    # 09-08 実測で最弱だった帯（0-14字・登録/千 0.242）の実例
    v = tc.check("下りだけ段が消える #shorts #架空論文", CH)
    assert not v["ok"]
    assert [x["rule"] for x in v["violations"]] == ["min_effective_chars"]
    assert "9" in v["violations"][0]["detail"]


def test_min_effective_chars_accepts_sweet_spot_title():
    # 最強だった帯（25-29字・登録/千 0.637）の実例
    v = tc.check("なぜ600年も読めない？存在しない植物だけが描かれた手稿 #shorts #都市伝説", CH)
    assert v["ok"], v["violations"]


def test_min_effective_chars_boundary_is_inclusive():
    twenty = "あ" * 20
    assert tc.check(twenty + " #shorts", CH)["ok"]
    nineteen = "あ" * 19
    assert not tc.check(nineteen + " #shorts", CH)["ok"]


def test_min_effective_chars_advice_mentions_sweet_spot():
    v = tc.check("最後尾だけ9%短い #shorts", CH)
    assert not v["ok"]
    assert any("25" in a for a in v["advice"])


# ---------------------------------------------------------------------
# 3. 挙動不変
# ---------------------------------------------------------------------

def test_unset_channel_is_unaffected():
    # min_effective_chars を持たないチャンネルは短いタイトルでも通る
    ch = {"title_rules": {"hard_constraints": {"max_chars": 30}}}
    assert tc.check("下りだけ段が消える #shorts", ch)["ok"]


def test_repair_does_not_pad_short_titles():
    """min_effective_chars は検査のみ。repair が文字を足して水増ししないこと。"""
    short = "下りだけ段が消える"
    assert tc.repair(short, CH) == short


def test_min_effective_chars_combines_with_other_rules():
    ch = {"title_rules": {"hard_constraints": {
        "min_effective_chars": 20,
        "banned_words": ["秘密"],
    }}}
    v = tc.check("秘密だった #shorts", ch)
    rules = sorted(x["rule"] for x in v["violations"])
    assert rules == ["banned_words", "min_effective_chars"]
