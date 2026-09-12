"""指揮者 2026-09-12 の修正に対する回帰テスト。

1. theme_queue の補充がタイトル機械ゲートを通ること（`_annotate_title_gate`）。
   09-12 時点で補充は `title_constraints` を一度も通っておらず、
   各chが自分で設定したゲートに自分のキューが落ちていた（111件中 合格24件）。
2. 切り抜き3ch の `hard_constraints` が実際に `is_enforced()` を True にすること。
   未設定chは検査が丸ごとスキップされるので「設定したのに何も起きない」になる。
3. キューの機械修復に `title_constraints.repair()` を使わないこと。
   長さ違反の末尾切り落とし・数字違反の数字削除で日本語が壊れる。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import title_constraints as tc  # noqa: E402
from pipeline.auto_scenario import theme_queue as tq  # noqa: E402

DATA = ROOT.parent / "data" / "channels"

CLIP_CHANNELS = ["clip-lab", "clip-fukada", "clip-kaneko"]
GATED_CHANNELS = [
    "scp-lab", "daily-science", "pokemon-lab", "yokai-watch", "2ch-matome",
    "company-facts", "fake-paper", "akashic-librarian",
] + CLIP_CHANNELS


class _FakeChannel:
    """ChannelProfile の最小スタブ（生 JSON を `_raw` に持つ）。"""

    def __init__(self, raw):
        self._raw = raw
        self.id = raw.get("id", "test")


def _load(ch):
    return json.loads((DATA / f"{ch}.json").read_text(encoding="utf-8"))


class TestQueueReplenishPassesThroughTitleGate:
    def test_violating_title_is_flagged_not_dropped(self):
        """違反タイトルは印が付くだけで、キューから消えてはいけない。

        弾くと「キュー全件ブロック」（09-11 に発生）を再発させる。
        """
        raw = _load("company-facts")
        item = {"title": "💸任天堂の年収988万円、実は開発職の正体"}
        out = tq._annotate_title_gate(item, _FakeChannel(raw))

        assert out is item, "項目を差し替えず、その場に印を付けること"
        assert out["title"] == "💸任天堂の年収988万円、実は開発職の正体", (
            "検査は書き換えをしない"
        )
        assert out["title_gate_ok"] is False
        assert "絵文字" in out["title_gate_violations"]

    def test_passing_title_is_marked_ok(self):
        raw = _load("company-facts")
        item = {"title": "任天堂の年収988万円、実は開発職の正体"}
        out = tq._annotate_title_gate(item, _FakeChannel(raw))
        assert out["title_gate_ok"] is True
        assert "title_gate_violations" not in out

    def test_unenforced_channel_is_left_untouched(self):
        """ゲート未設定chでは印を付けない（挙動不変を保つ）。"""
        item = {"title": "なんでもいい"}
        out = tq._annotate_title_gate(item, _FakeChannel({"id": "no-rules"}))
        assert "title_gate_ok" not in out

    def test_annotation_failure_does_not_break_replenish(self):
        """検査が壊れても補充そのものは落とさない。"""
        item = {"title": "テスト"}
        out = tq._annotate_title_gate(item, object())  # _raw も dict も無い
        assert out is item

    def test_replenish_calls_the_annotator(self):
        """配線が外れたら気付けるように、呼び出し自体を固定する。"""
        src = (
            ROOT / "pipeline" / "auto_scenario" / "theme_queue.py"
        ).read_text(encoding="utf-8")
        body = src.split("def replenish(", 1)[1]
        assert "_annotate_title_gate(item, channel)" in body, (
            "replenish() が _annotate_title_gate を呼んでいない"
        )


class TestClipChannelsAreEnforced:
    @pytest.mark.parametrize("ch", CLIP_CHANNELS)
    def test_clip_channel_gate_is_active(self, ch):
        raw = _load(ch)
        assert tc.is_enforced(raw), (
            f"{ch}: hard_constraints が無く検査がスキップされる"
        )

    @pytest.mark.parametrize("ch", CLIP_CHANNELS)
    def test_clip_channel_has_no_quote_breaking_rules(self, ch):
        """切り抜きはタイトルが発言の引用。下限文字数と必須語は入れない。"""
        hc = _load(ch)["title_rules"]["hard_constraints"]
        assert "min_effective_chars" not in hc, (
            f"{ch}: 引用に文字数下限を課すと誤引用を作りうる"
        )
        assert "require_any_of" not in hc, (
            f"{ch}: 引用に語を足すことになる"
        )

    @pytest.mark.parametrize("ch", CLIP_CHANNELS)
    def test_clip_channel_blocks_known_losers(self, ch):
        raw = _load(ch)
        for bad in ["これが成功の秘密です", "99%が知らない話", "🔥ヤバい話"]:
            assert not tc.check(bad, raw)["ok"], f"{ch}: '{bad}' が素通りした"

    @pytest.mark.parametrize("ch", GATED_CHANNELS)
    def test_all_analyzed_channels_are_enforced(self, ch):
        assert tc.is_enforced(_load(ch)), f"{ch}: ゲートが無効"


class TestRepairIsNotUsedOnQueueTitles:
    def test_repair_is_destructive_on_length_violations(self):
        """repair を使ってはいけない理由を固定しておく（09-12 実測）。

        違反数は減るのに日本語が壊れる。このテストが落ちたら repair の挙動が
        変わったということなので、キューへの適用可否を**測り直す**こと。
        """
        raw = _load("scp-lab")
        original = "SCP-1048「ビルダーベア」、愛らしい外見が起こした財団史上最恐の収容違反"
        repaired = tc.repair(original, raw)
        assert repaired != original
        assert len(repaired) < len(original), "末尾切り落としで通そうとする"
        assert not repaired.endswith("収容違反"), (
            "元の文末が失われる＝意味が変わっている"
        )

    def test_apply_script_does_not_call_repair(self):
        src = (
            ROOT.parent / "scripts" / "orch_apply_20260912.py"
        ).read_text(encoding="utf-8")
        body = src.split("def clean_queues", 1)[1].split("\ndef ", 1)[0]
        # コメントでの言及（「なぜ使わないか」の記録）は残してよいので、
        # 実行されるコード行だけを見る。
        code = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )
        assert "tc.repair(" not in code, (
            "キュー修復に repair を使うと日本語が壊れる（09-12 実測）"
        )
