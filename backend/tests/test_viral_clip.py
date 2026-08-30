"""海外バイラル切り抜き（clip-lab の 20:45 枠）の単体テスト。

ネットワーク・ffmpeg・Whisper を叩かない純粋ロジックのみ。
pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_viral_clip -v

守りたい性質:
  - 内容ゲートが「既定で閉じている」こと。設定を空にしてもハードブロックが残る
  - 縦長素材（9:16）を置いてもフック帯・字幕帯が画面外に出ないこと
  - 海外用レンダラが国内用（renderer.py）と分離されたままであること
  - 翻訳が失敗したら指数バックオフで再試行し、無駄な待ちはしないこと
  - 翻訳結果のパースが、壊れた行を字幕に出さないこと
  - clip-lab に同居しても海外枠の設定（尺・公開設定）が国内枠に汚染されないこと
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.clip_factory import asr as asr_mod  # noqa: E402
from pipeline.clip_factory import translate as tr_mod  # noqa: E402
from pipeline.clip_factory import viral_sources as vs  # noqa: E402
from pipeline.clip_factory import renderer as domestic_renderer  # noqa: E402
from pipeline.clip_factory.renderer_overseas import (  # noqa: E402
    OverseasLayout,
    compute_layout,
)

CHANNEL_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "channels", "clip-lab.json",
)


def _cand(**kw):
    base = dict(post_id="abc123", platform="reddit", title="A funny cat",
                media_url="https://example.com/v", permalink="https://reddit.com/x",
                community="r/funny")
    base.update(kw)
    return vs.ViralCandidate(**base)


class ContentGateTest(unittest.TestCase):
    """内容ゲート。ここが緩むとチャンネルごと消えるので既定は閉じている。"""

    def test_over_18_is_blocked_by_default(self):
        cand = vs.apply_gate(_cand(over_18=True), {"viral_sources": {}})
        self.assertFalse(cand.gate_ok)
        self.assertIn("over_18", cand.gate_reason)

    def test_over_18_can_be_allowed_explicitly(self):
        cfg = {"viral_sources": {"content_gate": {"allow_over_18": True}}}
        self.assertTrue(vs.apply_gate(_cand(over_18=True), cfg).gate_ok)

    def test_hard_block_survives_empty_config(self):
        """block_title_patterns を空にしても既定のハードブロックは消えない。"""
        cfg = {"viral_sources": {"content_gate": {"block_title_patterns": []}}}
        cand = vs.apply_gate(_cand(title="Amateur porn compilation"), cfg)
        self.assertFalse(cand.gate_ok)

    def test_gore_is_blocked(self):
        cand = vs.apply_gate(_cand(title="Guy films a dead body in the river"), {})
        self.assertFalse(cand.gate_ok)

    def test_custom_pattern_is_added_not_replacing(self):
        cfg = {"viral_sources": {"content_gate":
                                 {"block_title_patterns": ["(?i)crypto"]}}}
        self.assertFalse(vs.apply_gate(_cand(title="my crypto bag"), cfg).gate_ok)
        self.assertFalse(vs.apply_gate(_cand(title="nude beach"), cfg).gate_ok)
        self.assertTrue(vs.apply_gate(_cand(title="a cat on a roomba"), cfg).gate_ok)

    def test_broken_regex_does_not_break_the_gate(self):
        cfg = {"viral_sources": {"content_gate": {"block_title_patterns": ["(("]}}}
        cand = vs.apply_gate(_cand(title="a cat on a roomba"), cfg)
        self.assertTrue(cand.gate_ok)

    def test_blocked_community(self):
        cfg = {"viral_sources": {"content_gate": {"block_communities": ["r/funny"]}}}
        self.assertFalse(vs.apply_gate(_cand(), cfg).gate_ok)

    def test_unverified_nsfw_flag_can_be_rejected(self):
        """RSS 経路（NSFW フラグ不明）を締める設定が効くこと。"""
        cfg = {"viral_sources": {"content_gate":
                                 {"allow_unverified_nsfw_flag": False}}}
        self.assertFalse(vs.apply_gate(_cand(nsfw_verified=False), cfg).gate_ok)
        self.assertTrue(vs.apply_gate(_cand(nsfw_verified=True), cfg).gate_ok)

    def test_transcript_patterns_include_hard_block(self):
        pats = vs.transcript_patterns({})
        self.assertTrue(vs.check_text("she is completely naked here", pats))
        self.assertFalse(vs.check_text("he jumped over the fence", pats))


class RedditParseTest(unittest.TestCase):

    def test_reddit_hosted_video_uses_cdn_not_post_page(self):
        """投稿ページを yt-dlp に渡すと『Account authentication is required』で落ちる。

        v.redd.it の HLS は認証なしで取れる（実測 2026-08-30）ので、
        media_url は必ず CDN 側でなければならない。
        """
        post = {
            "id": "aaa", "title": "Cat", "permalink": "/r/funny/comments/aaa/cat/",
            "subreddit": "funny", "author": "u1", "score": 5000, "num_comments": 30,
            "over_18": False,
            "secure_media": {"reddit_video": {
                "duration": 23,
                "hls_url": "https://v.redd.it/abc123/HLSPlaylist.m3u8",
                "fallback_url": "https://v.redd.it/abc123/DASH_720.mp4",
            }},
        }
        cand = vs._post_to_candidate(post, subreddit="funny")
        self.assertIsNotNone(cand)
        self.assertEqual(cand.duration_sec, 23)
        self.assertEqual(cand.media_url, "https://v.redd.it/abc123/HLSPlaylist.m3u8")
        self.assertNotIn("reddit.com/r/", cand.media_url)
        # 出典表示には投稿ページを使う
        self.assertIn("/r/funny/comments/aaa/", cand.permalink)

    def test_video_without_media_url_is_skipped(self):
        post = {"id": "aaa", "title": "Cat", "permalink": "/r/funny/comments/aaa/",
                "subreddit": "funny",
                "secure_media": {"reddit_video": {"duration": 23}}}
        self.assertIsNone(vs._post_to_candidate(post, subreddit="funny"))

    def test_crosspost_video_is_found(self):
        post = {
            "id": "bbb", "title": "x", "permalink": "/r/a/comments/bbb/x/",
            "subreddit": "a",
            "crosspost_parent_list": [
                {"secure_media": {"reddit_video": {
                    "duration": 12,
                    "hls_url": "https://v.redd.it/zz/HLSPlaylist.m3u8"}}}],
        }
        cand = vs._post_to_candidate(post, subreddit="a")
        self.assertIsNotNone(cand)
        self.assertEqual(cand.duration_sec, 12)
        self.assertIn("v.redd.it", cand.media_url)

    def test_image_post_is_skipped(self):
        post = {"id": "ccc", "title": "pic", "permalink": "/r/a/comments/ccc/",
                "url": "https://i.redd.it/foo.jpg", "subreddit": "a"}
        self.assertIsNone(vs._post_to_candidate(post, subreddit="a"))

    def test_external_video_host_is_kept(self):
        post = {"id": "ddd", "title": "tt", "permalink": "/r/a/comments/ddd/",
                "url": "https://www.tiktok.com/@x/video/1", "subreddit": "a"}
        cand = vs._post_to_candidate(post, subreddit="a")
        self.assertIsNotNone(cand)
        self.assertIn("tiktok.com", cand.media_url)

    def test_rss_entries_are_parsed(self):
        feed = (
            '<feed><entry><author><name>/u/tester</name></author>'
            '<title>Something &amp; unexpected</title>'
            '<link href="https://www.reddit.com/r/unexpected/comments/zz99/some_post/" />'
            '</entry></feed>'
        )
        # 通信せずにパーサだけ検証する
        import re
        chunks = re.findall(r"<entry>(.*?)</entry>", feed, re.S)
        self.assertEqual(len(chunks), 1)
        link = vs._RSS_LINK_RE.search(chunks[0]).group(1)
        self.assertEqual(vs._RSS_ID_RE.search(link).group(1), "zz99")
        self.assertEqual(vs._unescape("Something &amp; unexpected"),
                         "Something & unexpected")

    def test_channel_key_is_filename_safe(self):
        """`:` `/` が混ざると ffmpeg がプロトコル指定と誤解して落ちる。"""
        key = vs.viral_channel_key("r/funny")
        self.assertNotIn("/", key)
        self.assertNotIn(":", key)


class AsrHelpersTest(unittest.TestCase):

    def test_hallucination_is_dropped(self):
        self.assertEqual(asr_mod._clean("Thank you for watching!"), "")
        self.assertEqual(asr_mod._clean("[Music]"), "")
        self.assertEqual(asr_mod._clean("  ♪♪ "), "")
        self.assertEqual(asr_mod._clean("  he did what?  "), "he did what?")

    def _transcript(self):
        segs = [asr_mod.SpeechSegment(0, 0.0, 4.0, "a"),
                asr_mod.SpeechSegment(1, 50.0, 58.0, "b"),
                asr_mod.SpeechSegment(2, 58.0, 66.0, "c")]
        return asr_mod.Transcript(language="en", segments=segs, duration=120.0)

    def test_densest_window_finds_the_talky_part(self):
        start, end = asr_mod.densest_window(self._transcript(), window_sec=30.0)
        self.assertGreaterEqual(start, 36.0)
        self.assertAlmostEqual(end - start, 30.0, places=3)

    def test_short_video_uses_everything(self):
        tr = asr_mod.Transcript(
            language="en", duration=20.0,
            segments=[asr_mod.SpeechSegment(0, 1.0, 9.0, "x")])
        self.assertEqual(asr_mod.densest_window(tr, window_sec=59.0), (0.0, 20.0))

    def test_slice_trims_to_window(self):
        got = asr_mod.slice_segments(self._transcript(), 52.0, 60.0)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0].start, 52.0)
        self.assertEqual(got[1].end, 60.0)

    def test_speech_ratio(self):
        self.assertAlmostEqual(self._transcript().speech_ratio, 20.0 / 120.0, places=3)


class TranslationParseTest(unittest.TestCase):

    def _lines(self):
        return [asr_mod.SpeechSegment(0, 0.0, 3.0, "hello"),
                asr_mod.SpeechSegment(1, 3.0, 6.0, "world")]

    def test_maps_ids_and_keeps_timing(self):
        res = {"hook": "テスト", "lines": [{"id": 1, "ja": "せかい"},
                                           {"id": 0, "ja": "やあ"}]}
        clip = tr_mod._parse_result(res, self._lines(), hook_limit=28,
                                    subtitle_limit=34, source="test")
        self.assertEqual([l.text_ja for l in clip.lines], ["せかい", "やあ"])
        self.assertEqual(clip.lines[0].start, 3.0)

    def test_empty_translation_is_dropped(self):
        res = {"hook": "h", "lines": [{"id": 0, "ja": ""}, {"id": 1, "ja": "  "}]}
        clip = tr_mod._parse_result(res, self._lines(), hook_limit=28,
                                    subtitle_limit=34, source="test")
        self.assertEqual(clip.lines, [])

    def test_unknown_id_is_ignored(self):
        res = {"hook": "h", "lines": [{"id": 99, "ja": "x"}]}
        clip = tr_mod._parse_result(res, self._lines(), hook_limit=28,
                                    subtitle_limit=34, source="test")
        self.assertEqual(clip.lines, [])

    def test_hook_newlines_are_flattened(self):
        """改行が残るとタイトルに混入して YouTube API が弾く。"""
        clip = tr_mod._parse_result({"hook": "前半\n後半"}, [], hook_limit=28,
                                    subtitle_limit=34, source="test")
        self.assertEqual(clip.hook, "前半 後半")

    def test_hook_is_truncated(self):
        clip = tr_mod._parse_result({"hook": "あ" * 60}, [], hook_limit=28,
                                    subtitle_limit=34, source="test")
        self.assertEqual(len(clip.hook), 28)

    def test_safety_flag_is_read(self):
        clip = tr_mod._parse_result(
            {"hook": "h", "safety_ok": False, "safety_reason": "裸体"}, [],
            hook_limit=28, subtitle_limit=34, source="test")
        self.assertFalse(clip.safety_ok)


class LayoutTest(unittest.TestCase):
    """海外用レンダラ（renderer_overseas）のレイアウト。"""

    HOOK = "賭けに出た男、まさかの結末"

    def test_landscape_source_uses_full_width(self):
        c = compute_layout(OverseasLayout(), hook=self.HOOK,
                           source_size=(1920, 1080))
        self.assertEqual(c.video_w, 1080)
        self.assertEqual(c.video_x, 0)

    def test_portrait_source_fits_on_canvas(self):
        layout = OverseasLayout()
        c = compute_layout(layout, hook=self.HOOK, source_size=(1080, 1920))
        self.assertLess(c.video_w, layout.width)          # 縮めて左右に余白
        self.assertGreater(c.video_x, 0)
        self.assertGreaterEqual(c.hook_y, 0)
        # 字幕帯の下端が CTA を越えない＝画面外に出ない
        self.assertLessEqual(c.subtitle_y + c.subtitle_band_h, c.cta_y)
        self.assertLessEqual(c.video_y + c.video_h, layout.height)

    def test_no_subtitles_frees_the_band(self):
        """無音動画では字幕帯を確保しない（映像が小さいまま間延びするため）。"""
        layout = OverseasLayout()
        with_subs = compute_layout(layout, hook=self.HOOK,
                                   source_size=(1080, 1920))
        without = compute_layout(layout, hook=self.HOOK,
                                 source_size=(1080, 1920),
                                 reserve_subtitles=False)
        self.assertEqual(without.subtitle_band_h, 0)
        self.assertGreater(without.video_h, with_subs.video_h)
        self.assertLessEqual(without.video_y + without.video_h, without.cta_y)

    def test_square_source_fits(self):
        c = compute_layout(OverseasLayout(), hook=self.HOOK,
                           source_size=(1080, 1080))
        self.assertLessEqual(c.subtitle_y + c.subtitle_band_h, c.cta_y)

    def test_video_dimensions_are_even(self):
        """奇数だと libx264 の yuv420p でエンコードが落ちる。"""
        layout = OverseasLayout()
        for size in [(1080, 1921), (721, 1281), (1079, 1919)]:
            c = compute_layout(layout, hook=self.HOOK, source_size=size)
            self.assertEqual(c.video_w % 2, 0, size)
            self.assertEqual(c.video_h % 2, 0, size)


class RendererSeparationTest(unittest.TestCase):
    """海外用レンダラは国内用（renderer.py）から分離されたままであること。

    clip-lab に同居した以上、共有に戻すと海外枠の調整が 17:45 の国内切り抜きの
    見た目を壊す。分離の意図が実装から失われていないかをここで見張る。
    """

    def test_overseas_defaults_do_not_crop_the_source(self):
        """国内既定（下部22%を切り落とす）を継承していないこと。"""
        self.assertEqual(OverseasLayout().source_crop_bottom_ratio, 0.0)
        self.assertEqual(domestic_renderer.ClipLayout().source_crop_bottom_ratio,
                         0.22)

    def test_overseas_layout_ignores_domestic_crop_setting(self):
        """clip-lab 直下の layout_spec（0.22）を読み込まないこと。"""
        channel = {"layout_spec": {"canvas": [1080, 1920], "fps": 30,
                                   "source_crop_bottom_ratio": 0.22}}
        self.assertEqual(
            OverseasLayout.from_channel(channel).source_crop_bottom_ratio, 0.0)

    def test_overseas_layout_reads_its_own_overrides(self):
        channel = {
            "layout_spec": {"source_crop_bottom_ratio": 0.22},
            "clip": {"viral_sources": {
                "layout_spec": {"source_crop_bottom_ratio": 0.1},
                "thumbnail_template": {"badge_color": [1, 2, 3]},
            }},
        }
        layout = OverseasLayout.from_channel(channel)
        self.assertAlmostEqual(layout.source_crop_bottom_ratio, 0.1)
        self.assertEqual(layout.accent_color, (1, 2, 3))

    def test_engine_imports_the_overseas_renderer(self):
        from pipeline.clip_factory.engines import viral as viral_engine
        self.assertTrue(
            viral_engine.render_clip.__module__.endswith("renderer_overseas"))
        self.assertTrue(
            viral_engine.render_thumbnail.__module__.endswith("renderer_overseas"))


class TranslationRetryTest(unittest.TestCase):
    """翻訳失敗時は再試行する（スキップしない）。"""

    def setUp(self):
        self.slept = []
        self.calls = []

    def _run(self, results, reason="Anthropic レート制限（429）"):
        """_call_claude / _claude_reason を差し替えて再試行だけを見る。"""
        orig_call, orig_reason = tr_mod._call_claude, tr_mod._claude_reason

        def fake_call(prompt, channel_id):
            self.calls.append(prompt)
            return results[len(self.calls) - 1] if len(self.calls) <= len(results) else None

        tr_mod._call_claude = fake_call
        tr_mod._claude_reason = lambda: reason
        try:
            return tr_mod._call_claude_with_retry(
                "p", "clip-lab", base_sleep=1.0, sleep=self.slept.append)
        finally:
            tr_mod._call_claude, tr_mod._claude_reason = orig_call, orig_reason

    def test_first_attempt_succeeds_without_sleeping(self):
        self.assertEqual(self._run([{"hook": "ok"}]), {"hook": "ok"})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.slept, [])

    def test_retries_until_success(self):
        self.assertEqual(self._run([None, None, {"hook": "ok"}]), {"hook": "ok"})
        self.assertEqual(len(self.calls), 3)

    def test_backoff_is_exponential(self):
        self._run([None, None, None])
        # 3回試行 → 待つのは 2回だけ（最後の失敗後は待たない）
        self.assertEqual(self.slept, [1.0, 2.0])

    def test_gives_up_after_max_attempts(self):
        self.assertIsNone(self._run([None, None, None]))
        self.assertEqual(len(self.calls), tr_mod.TRANSLATE_MAX_ATTEMPTS)

    def test_permanent_failure_is_not_retried(self):
        """キー未設定・認証エラー・残高不足で3回待っても結果は同じ。"""
        for reason in ["ANTHROPIC_API_KEY 未設定",
                       "ANTHROPIC_API_KEY が無効（認証エラー）",
                       "Anthropic クレジット残高不足（Plans & Billing）",
                       "anthropic SDK 未導入（pip install anthropic）"]:
            self.calls, self.slept = [], []
            self.assertIsNone(self._run([None, None, None], reason=reason), reason)
            self.assertEqual(len(self.calls), 1, reason)
            self.assertEqual(self.slept, [], reason)


class ChannelConfigTest(unittest.TestCase):
    """clip-lab に統合した海外枠の設定（ユーザー決定 2026-08-30）。"""

    @classmethod
    def setUpClass(cls):
        with open(CHANNEL_JSON, encoding="utf-8") as fh:
            cls.raw = json.load(fh)
        cls.clip = cls.raw["clip"]

    def test_viral_sources_live_on_clip_lab(self):
        self.assertTrue(vs.is_enabled(self.clip))

    def test_no_manual_review_and_public(self):
        """レビューなし・直接 public。force_privacy を立てない。"""
        self.assertFalse(vs.requires_review(self.clip))
        self.assertEqual(
            self.raw["publish_settings"]["default_privacy"], "public")

    def test_overseas_durations_are_not_inherited_from_domestic(self):
        """国内枠の min_duration_sec（30秒）を継がない＝短いバイラルも通る。"""
        out = vs.output_cfg(self.clip)
        self.assertLess(float(out["min_duration_sec"]),
                        float(self.clip["min_duration_sec"]))
        self.assertLessEqual(float(out["max_duration_sec"]), 59)

    def test_daily_2045_slot_runs_the_viral_engine(self):
        slots = self.raw["autopilot"]["schedule"]["times"]
        viral = [s for s in slots if s.get("engine") == "viral"]
        self.assertEqual(len(viral), 1)
        self.assertEqual((viral[0]["hour"], viral[0]["minute"]), (20, 45))
        self.assertEqual(sorted(viral[0]["days_of_week"]), list(range(7)))

    def test_domestic_slot_is_untouched(self):
        slots = self.raw["autopilot"]["schedule"]["times"]
        local = [s for s in slots if not s.get("engine")]
        self.assertEqual([(s["hour"], s["minute"]) for s in local], [(17, 45)])
        self.assertEqual(self.clip["engine"], "local")

    def test_hard_block_still_applies_to_the_merged_config(self):
        cand = vs.apply_gate(_cand(title="leaked nude compilation"), self.clip)
        self.assertFalse(cand.gate_ok)


if __name__ == "__main__":
    unittest.main()
