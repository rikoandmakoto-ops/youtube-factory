"""clip_factory の単体テスト（ffmpeg を叩かない純粋ロジックのみ）。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_clip_factory -v

守りたい性質:
  - 台本行と検出境界の数がズレても、行のタイムラインが単調かつ全尺を覆うこと
    （scp-lab は画面エフェクトで境界が 90行に対し 820個検出される）
  - フック文が語の途中で切れないこと
  - 字幕の折り返しが英数字・カタカナ・漢字熟語を分断しないこと
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.clip_factory.align import align_lines  # noqa: E402
from pipeline.clip_factory.renderer import wrap_text  # noqa: E402
from pipeline.clip_factory.segments import (  # noqa: E402
    Segment,
    heuristic_hook,
    _tidy,
)
from pipeline.clip_factory.align import LineTiming  # noqa: E402


def _lines(texts):
    return [{"speaker": "理子", "text": t} for t in texts]


class TestAlignLines(unittest.TestCase):
    def test_boundaries_match_line_count(self):
        lines = _lines(["あ" * 10, "い" * 20, "う" * 10])
        boundaries = [0.0, 10.0, 30.0]
        timings = align_lines(boundaries, lines, 40.0)
        self.assertEqual(len(timings), 3)
        self.assertEqual(timings[0].start, 0.0)
        self.assertAlmostEqual(timings[-1].end, 40.0)

    def test_more_boundaries_than_lines(self):
        """エフェクトで境界が過剰検出されても行数どおりに畳めること。"""
        lines = _lines(["あ" * 10, "い" * 10, "う" * 10])
        boundaries = [float(i) for i in range(0, 30, 2)]  # 15個
        timings = align_lines(boundaries, lines, 30.0)
        self.assertEqual(len(timings), 3)
        for prev, nxt in zip(timings, timings[1:]):
            self.assertLessEqual(prev.end, nxt.start + 1e-6)
        self.assertAlmostEqual(timings[-1].end, 30.0)

    def test_fewer_boundaries_falls_back_to_proportional(self):
        lines = _lines(["あ" * 30, "い" * 10])
        timings = align_lines([0.0], lines, 40.0)
        self.assertEqual(len(timings), 2)
        # 文字数比 3:1 で按分される
        self.assertAlmostEqual(timings[0].duration, 30.0, places=1)
        self.assertAlmostEqual(timings[1].duration, 10.0, places=1)

    def test_timeline_is_monotonic_and_covers_duration(self):
        lines = _lines([f"テスト{i}" * 4 for i in range(12)])
        boundaries = [i * 3.0 for i in range(20)]
        timings = align_lines(boundaries, lines, 60.0)
        self.assertEqual(len(timings), 12)
        self.assertEqual(timings[0].start, 0.0)
        self.assertAlmostEqual(timings[-1].end, 60.0)
        for prev, nxt in zip(timings, timings[1:]):
            self.assertLessEqual(prev.start, nxt.start)


class TestHook(unittest.TestCase):
    def _segment(self, texts):
        timings = [
            LineTiming(index=i, speaker="理子", text=t, start=i * 5.0, end=(i + 1) * 5.0)
            for i, t in enumerate(texts)
        ]
        return Segment(
            start=0.0, end=len(texts) * 5.0,
            line_indices=[t.index for t in timings], lines=timings, score=1.0,
        )

    def test_prefers_conclusion_clause_over_attribution(self):
        seg = self._segment([
            "2011年のピサ大学の研究では、家族間でのあくび伝染率は約50%だったんだ。",
        ])
        hook = heuristic_hook(seg)
        self.assertIn("50%", hook)
        self.assertFalse(hook.startswith("2011年のピサ大学"))

    def test_strips_character_sentence_endings(self):
        seg = self._segment(["伝染率はわずか33%だったの。"])
        self.assertEqual(heuristic_hook(seg), "伝染率はわずか33%だった")

    def test_does_not_cut_word_in_half(self):
        seg = self._segment([
            "成功例の戦闘能力は通常人間の50倍から200倍に達するという報告があるんだ。",
        ])
        hook = heuristic_hook(seg)
        self.assertFalse(hook.endswith("達す"), hook)

    def test_noun_de_is_not_treated_as_conjunction(self):
        """『飲み込んだもので』の「ので」を接続助詞と誤認して削らないこと。"""
        self.assertEqual(
            _tidy("この空気の約70%は口から飲み込んだもので"),
            "この空気の約70%は口から飲み込んだもので",
        )

    def test_verb_node_is_treated_as_conjunction(self):
        self.assertEqual(_tidy("収容違反が発生しているので"), "収容違反が発生している")

    def test_date_only_clause_is_not_chosen(self):
        seg = self._segment([
            "1998年3月12日、財団の記録では17名の犠牲者が確認されたんだ。",
        ])
        hook = heuristic_hook(seg)
        self.assertNotEqual(hook, "1998年3月12日")


class TestWrap(unittest.TestCase):
    def test_does_not_split_ascii_token(self):
        lines = wrap_text("SCP-914がUltraFineで処理した金属片", 10, 3)
        self.assertTrue(all("Ultra" not in l or l.count("Ultra") == 1 for l in lines))
        joined = "".join(lines)
        self.assertIn("UltraFine", joined)
        for line in lines[:-1]:
            self.assertFalse(line.endswith("Ultr"), lines)

    def test_does_not_split_kanji_compound(self):
        lines = wrap_text("人間の社会性を測る重要な指標として注目されている", 12, 3)
        self.assertFalse(any(l.endswith("指") for l in lines[:-1]), lines)

    def test_respects_max_lines_with_ellipsis(self):
        lines = wrap_text("あ" * 200, 10, 2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))


if __name__ == "__main__":
    unittest.main()
