"""narration_video のタイムライン組み立ての単体テスト（ffmpeg / 画像APIは叩かない）。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_narration_video -v

守りたい性質:
  - オーバーレイの区間が音声の全尺を隙間なく覆うこと
    （concat demuxer は区間の合計をそのまま尺にするため、隙間 = 映像と音声のズレ）
  - 章の頭ではタイトルカードが出て、字幕がその裏に重ならないこと
  - カードのフェードが 0 から立ち上がり 0 に戻ること
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.narration_video import (  # noqa: E402
    CARD_FADE,
    CARD_SECONDS,
    build_timeline,
    kanji_chapter,
)

DURATION = 300.0
CHAPTERS = [
    {"index": 1, "title": "はじまりの記録", "start": 0.0, "end": 100.0},
    {"index": 2, "title": "二つ目の記録", "start": 100.0, "end": 220.0},
    {"index": 3, "title": "最後の記録", "start": 220.0, "end": DURATION},
]
CUES = [
    {"start": 0.0, "end": 40.0, "text": "第一章の話をする。"},
    {"start": 40.0, "end": 100.0, "text": "まだ第一章である。"},
    {"start": 100.0, "end": 160.0, "text": "第二章に入った。"},
    {"start": 160.0, "end": 220.0, "text": "第二章の続き。"},
    {"start": 220.0, "end": DURATION, "text": "最後の章である。"},
]


class TestBuildTimeline(unittest.TestCase):
    def setUp(self):
        self.frames = build_timeline(CUES, CHAPTERS, DURATION)

    def test_covers_full_duration_without_gaps(self):
        """区間が連続していないと、その分だけ映像が音声より短く（長く）なる。"""
        t = 0.0
        for f in self.frames:
            self.assertAlmostEqual(f["start"], t, places=3,
                                   msg=f"区間に隙間/重なり: {t} → {f['start']}")
            t += f["dur"]
        self.assertAlmostEqual(t, DURATION, places=3)

    def test_all_durations_positive(self):
        for f in self.frames:
            self.assertGreater(f["dur"], 0.0)

    def test_card_shown_at_every_chapter_start(self):
        for ch in CHAPTERS:
            cards = [f for f in self.frames
                     if f["kind"] == "card" and f["chapter"]["index"] == ch["index"]]
            self.assertTrue(cards, f"第{ch['index']}章のカードが無い")
            total = sum(f["dur"] for f in cards)
            self.assertAlmostEqual(total, CARD_SECONDS, places=2)
            self.assertAlmostEqual(cards[0]["start"], ch["start"], places=3)

    def test_no_subtitle_behind_card(self):
        """カード表示中に字幕を出すと、暗幕の上に二重で文字が乗る。"""
        for f in self.frames:
            if f["kind"] != "card":
                continue
            mid = f["start"] + f["dur"] / 2
            for ch in CHAPTERS:
                if ch["start"] <= mid < ch["start"] + CARD_SECONDS:
                    break
            else:
                self.fail("カードが章の頭以外に出ている")
        subs_in_card = [
            f for f in self.frames
            if f["kind"] == "sub"
            and any(ch["start"] <= f["start"] < ch["start"] + CARD_SECONDS - 1e-6
                    for ch in CHAPTERS)
        ]
        self.assertEqual(subs_in_card, [])

    def test_card_fades_in_and_out(self):
        cards = [f for f in self.frames
                 if f["kind"] == "card" and f["chapter"]["index"] == 2]
        alphas = [f["alpha"] for f in cards]
        self.assertLess(alphas[0], 0.3, "フェードインが立ち上がっていない")
        self.assertLess(alphas[-1], 0.3, "フェードアウトが落ちていない")
        self.assertAlmostEqual(max(alphas), 1.0, places=3)

    def test_card_clipped_to_short_chapter(self):
        """章がカード尺より短くても、区間が次章へはみ出さないこと。"""
        chapters = [
            {"index": 1, "title": "短い章", "start": 0.0, "end": 3.0},
            {"index": 2, "title": "次の章", "start": 3.0, "end": 20.0},
        ]
        cues = [{"start": 0.0, "end": 20.0, "text": "短い章の本文。"}]
        frames = build_timeline(cues, chapters, 20.0)
        ch1_cards = [f for f in frames
                     if f["kind"] == "card" and f["chapter"]["index"] == 1]
        self.assertLessEqual(max(f["start"] + f["dur"] for f in ch1_cards), 3.0 + 1e-6)
        t = 0.0
        for f in frames:
            self.assertAlmostEqual(f["start"], t, places=3)
            t += f["dur"]
        self.assertAlmostEqual(t, 20.0, places=3)

    def test_subtitle_text_matches_cue(self):
        sub = next(f for f in self.frames
                   if f["kind"] == "sub" and f["start"] >= CARD_SECONDS)
        self.assertEqual(sub["text"], CUES[0]["text"])
        self.assertEqual(sub["chapter"]["index"], 1)

    def test_fade_length(self):
        cards = [f for f in self.frames
                 if f["kind"] == "card" and f["chapter"]["index"] == 1]
        rising = [f for f in cards if f["alpha"] < 1.0
                  and f["start"] < CHAPTERS[0]["start"] + CARD_FADE]
        self.assertTrue(rising)
        self.assertLessEqual(sum(f["dur"] for f in rising), CARD_FADE + 1e-6)


class TestKanjiChapter(unittest.TestCase):
    def test_known(self):
        self.assertEqual(kanji_chapter(1), "第一章")
        self.assertEqual(kanji_chapter(8), "第八章")
        self.assertEqual(kanji_chapter(10), "第十章")

    def test_out_of_range_falls_back_to_digits(self):
        self.assertEqual(kanji_chapter(11), "第11章")


if __name__ == "__main__":
    unittest.main()
