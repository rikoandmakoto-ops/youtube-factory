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
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.clip_factory.align import align_lines  # noqa: E402
from pipeline.clip_factory.renderer import wrap_text  # noqa: E402
from pipeline.clip_factory.segments import (  # noqa: E402
    Segment,
    build_candidates,
    heuristic_hook,
    _tidy,
)
from pipeline.clip_factory.align import LineTiming  # noqa: E402
from pipeline.clip_factory import visual_guard  # noqa: E402
from pipeline.clip_factory.acquisition import (  # noqa: E402
    USE_CLIPPABLE,
    USE_THEME_ONLY,
    _matched_exclude_pattern,
    classify,
)
from pipeline.clip_factory.captions import parse_vtt  # noqa: E402
from pipeline.clip_factory.engines.local import safe_clip_id  # noqa: E402
from pipeline.clip_factory.pipeline import build_title  # noqa: E402


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


# ---------------------------------------------------------------------
# 外部素材（許諾済みチャンネルの切り抜き）
# ---------------------------------------------------------------------

class TestCaptionParsing(unittest.TestCase):
    """YouTube 自動字幕の重複表示を語タイムコードで解けているか。"""

    VTT = (
        "WEBVTT\n\n"
        "00:00:00.880 --> 00:00:03.590 align:start position:0%\n"
        " \n"
        "えっと<00:00:01.120><c>、</c><00:00:01.319><c>これ</c><00:00:02.320><c>は</c>\n\n"
        "00:00:03.590 --> 00:00:03.600 align:start position:0%\n"
        "えっと、これは\n \n\n"
        "00:00:03.600 --> 00:00:08.589 align:start position:0%\n"
        "えっと、これは\n"
        "実験<00:00:04.080><c>です</c><00:00:04.359><c>。</c>\n\n"
    )

    def test_rolling_duplicates_are_not_repeated(self):
        timings = parse_vtt(self.VTT, total_duration=10.0)
        joined = "".join(t.text for t in timings)
        self.assertEqual(joined.count("えっと"), 1, joined)

    def test_uses_inline_word_timecodes(self):
        timings = parse_vtt(self.VTT, total_duration=10.0)
        self.assertTrue(timings)
        self.assertAlmostEqual(timings[0].start, 0.88, places=2)

    def test_line_duration_is_not_inflated_by_silence(self):
        """無音を跨いだ行が何十秒にもならないこと。"""
        vtt = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "はい<00:00:00.500><c>そうです</c><00:00:01.000><c>。</c>\n\n"
            "00:01:00.000 --> 00:01:02.000\n"
            "続き<00:01:00.500><c>です</c><00:01:01.000><c>。</c>\n\n"
        )
        timings = parse_vtt(vtt, total_duration=70.0)
        self.assertTrue(all(t.duration < 15.0 for t in timings),
                        [(t.text, t.duration) for t in timings])


class TestSilenceGate(unittest.TestCase):
    """自動字幕由来の区間選定で無音だらけの窓を弾けているか。

    字幕から起こした行は沈黙を含まないので、素朴に窓を作ると
    『冒頭に数秒喋って以降ほぼ無音』の区間が最高スコアで選ばれる。
    """

    def _lines_with_early_gap(self):
        rows = [(0.0, 2.2, "そうなんだ。すごいね。")]
        t = 11.0
        for i in range(12):
            rows.append((t, t + 2.6, f"実は{i}割の人が知らない話で50%です。"))
            t += 2.8
        return [LineTiming(index=i, speaker="", text=r[2], start=r[0], end=r[1])
                for i, r in enumerate(rows)], t + 5

    def _max_gap(self, seg):
        gaps = [seg.lines[k + 1].start - seg.lines[k].end
                for k in range(len(seg.lines) - 1)]
        return max(gaps) if gaps else 0.0

    def test_gate_off_reproduces_the_silent_window(self):
        lines, total = self._lines_with_early_gap()
        cands = build_candidates(
            lines, total_duration=total, min_sec=30, max_sec=59,
            exclude_head_sec=0, exclude_tail_sec=0,
        )
        self.assertTrue(any(self._max_gap(c) > 5.0 for c in cands))

    def test_gate_rejects_windows_containing_long_silence(self):
        lines, total = self._lines_with_early_gap()
        cands = build_candidates(
            lines, total_duration=total, min_sec=30, max_sec=59,
            exclude_head_sec=0, exclude_tail_sec=0,
            min_speech_ratio=0.72, max_line_gap_sec=2.5,
        )
        self.assertTrue(cands, "ガードが強すぎて候補が全滅している")
        for c in cands:
            self.assertLessEqual(self._max_gap(c), 2.5)
            speech = sum(l.duration for l in c.lines)
            self.assertGreaterEqual(speech / c.duration, 0.72)

    def test_gate_is_checked_before_min_duration(self):
        """min_sec 未満の段階にある無音が素通りしないこと（実測バグの再発防止）。

        無音チェックを尺チェックの後ろに置くと、窓がまだ短い間の穴が
        `continue` で見逃され、窓の内側に取り残される。
        """
        lines, total = self._lines_with_early_gap()
        cands = build_candidates(
            lines, total_duration=total, min_sec=30, max_sec=59,
            exclude_head_sec=0, exclude_tail_sec=0, max_line_gap_sec=2.5,
        )
        self.assertFalse(any(c.lines[0].index == 0 and len(c.lines) > 1
                             for c in cands),
                         "冒頭の8.8秒の無音を含む窓が残っている")


class TestBuildTitle(unittest.TestCase):
    def test_strips_newlines_from_hook(self):
        """LLM は2行に割るつもりで改行を返す。YouTube のタイトルに改行は入らない。"""
        channel = {"defaults": {"short_title_hashtags": "#shorts #切り抜き"}}
        title = build_title("残業が多くても\n年収アップならアリ", channel)
        self.assertNotIn("\n", title)
        self.assertIn("年収アップならアリ", title)


class TestSafeClipId(unittest.TestCase):
    def test_colon_is_removed(self):
        """clip_id はファイル名になる。`yt:` は ffmpeg にプロトコルと解釈される。"""
        self.assertNotIn(":", safe_clip_id("yt:UC0yQ2h4gQXmVUFWZSqlMVOA_123_0"))


class TestPermissionGate(unittest.TestCase):
    """許諾文言ゲート。ここが緩むと無許諾の切り抜きが生成される。"""

    CFG = {
        "external_sources": {
            "allowlist_channels": [
                {"channel_id": "UC_ok", "permission_phrases": ["切り抜きを黙認します"]},
                {"channel_id": "UC_note", "require_permission_phrase": False,
                 "permission_note": "メールで許諾"},
                {"channel_id": "UC_empty", "permission_phrases": []},
            ]
        }
    }

    def _use(self, **kw):
        return classify(clip_cfg=self.CFG, **kw)[0]

    def test_allowlisted_video_with_phrase_is_clippable(self):
        self.assertEqual(
            self._use(license_value="youtube", channel_id="UC_ok",
                      description="本編です。この動画の切り抜きを黙認します。"),
            USE_CLIPPABLE)

    def test_allowlisted_video_without_phrase_is_blocked(self):
        """チャンネル単位の許諾を回単位に拡大解釈しないこと。"""
        self.assertEqual(
            self._use(license_value="youtube", channel_id="UC_ok",
                      description="ゲスト回です。"),
            USE_THEME_ONLY)

    def test_explicit_opt_out_of_phrase_check_is_honoured(self):
        self.assertEqual(
            self._use(license_value="youtube", channel_id="UC_note", description=""),
            USE_CLIPPABLE)

    def test_empty_phrase_list_is_not_a_free_pass(self):
        """根拠が空のまま通してしまうと allowlist が無検証の宣言になる。"""
        self.assertEqual(
            self._use(license_value="youtube", channel_id="UC_empty",
                      description="なんでも切り抜いてOK"),
            USE_THEME_ONLY)

    def test_unlisted_standard_license_is_theme_only(self):
        self.assertEqual(
            self._use(license_value="youtube", channel_id="UC_other",
                      description="この動画の切り抜きを黙認します"),
            USE_THEME_ONLY)

    def test_creative_commons_is_clippable(self):
        self.assertEqual(
            self._use(license_value="creativeCommon", channel_id="UC_other",
                      description=""),
            USE_CLIPPABLE)


class TestExcludeTitlePatterns(unittest.TestCase):
    """ゲスト回・コラボ回のタイトル除外。

    自動字幕には話者情報が無いので、区間だけを見て「今喋っているのが本人か
    ゲストか」は判定できない。回ごと落とすのが唯一の確実な手段。
    """

    ENTRY = {"exclude_title_patterns": ["VS", "ゲスト", "【.*エレン.*】"]}

    def test_matching_title_is_reported(self):
        self.assertEqual(
            _matched_exclude_pattern(self.ENTRY, "ひろゆきVS石川典行 討論会"), "VS")

    def test_regex_pattern_matches(self):
        self.assertEqual(
            _matched_exclude_pattern(self.ENTRY, "夫への不満爆発【左ききのエレン】"),
            "【.*エレン.*】")

    def test_solo_stream_is_kept(self):
        self.assertEqual(
            _matched_exclude_pattern(self.ENTRY, "5月病のみんな元気ー？"), "")

    def test_no_patterns_means_no_filtering(self):
        self.assertEqual(_matched_exclude_pattern({}, "ひろゆきVS誰か"), "")

    def test_broken_regex_falls_back_to_substring(self):
        """設定ミスの正規表現で調達全体を止めないこと。"""
        entry = {"exclude_title_patterns": ["[未閉じ"]}
        self.assertEqual(_matched_exclude_pattern(entry, "これは[未閉じの回"), "[未閉じ")
        self.assertEqual(_matched_exclude_pattern(entry, "普通の回"), "")


class TestVisualGuardThresholds(unittest.TestCase):
    """映像ゲートの閾値。

    2026-08-24 に同一配信・同一画質の9区間で実測した値を回帰テストにしてある。
    閾値をいじって『マンガの画面共有』が通るようになったらここで落ちる。
    """

    #: (静止率, 差分中央値) の実測値
    REAL_TALKING_HEAD = [
        (0.068, 6.61), (0.034, 6.48), (0.305, 1.90), (0.407, 1.86),
        (0.034, 4.30), (0.017, 5.51), (0.000, 6.93), (0.034, 7.13),
    ]
    STATIC_SCREENSHARE = (1.000, 0.02)

    def _ok(self, static_ratio, median):
        return not (static_ratio >= visual_guard.MAX_STATIC_RATIO
                    or median < visual_guard.MIN_MEDIAN_DIFF)

    def test_real_footage_passes(self):
        for static_ratio, median in self.REAL_TALKING_HEAD:
            self.assertTrue(self._ok(static_ratio, median),
                            f"実写区間が落ちた: static={static_ratio} median={median}")

    def test_static_screenshare_is_rejected(self):
        self.assertFalse(self._ok(*self.STATIC_SCREENSHARE))

    def test_thresholds_keep_margin_over_worst_real_footage(self):
        """良判定の最悪値と閾値の間に余裕があること（ギリギリに詰めない）。"""
        worst_static = max(s for s, _ in self.REAL_TALKING_HEAD)
        worst_median = min(m for _, m in self.REAL_TALKING_HEAD)
        self.assertLess(worst_static + 0.2, visual_guard.MAX_STATIC_RATIO)
        self.assertGreater(worst_median, visual_guard.MIN_MEDIAN_DIFF * 2)

    def test_unmeasurable_segment_passes(self):
        """判定不能なら通す（ゲートが壊れて全部落ちると autopilot が止まる）。"""
        verdict = visual_guard.inspect(
            Path("/nonexistent/never.mp4"), start=0.0, duration=10.0)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.sampled_frames, 0)


if __name__ == "__main__":
    unittest.main()
