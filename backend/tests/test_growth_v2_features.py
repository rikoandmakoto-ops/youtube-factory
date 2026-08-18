"""再生リスト / シリーズリンク / リクエスト募集 / 競合RSS / エンドカード の単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_growth_v2_features -v

守りたい回帰:
  - 再生リストの投入先がショート/長尺で分かれ、無効化フラグが効く
  - 前回/次回リンクが二重に積み重ならない（貼り直しで置換される）
  - videos.update に categoryId/title を落とさない（落とすと 400 で失敗する）
  - リクエスト募集ブロックが説明文と自動コメントの両方に出る
  - 競合 RSS の XML が video_id / 公開時刻まで正しく取れる
  - エンドカードが末尾に1枚だけ足され、無効化できる
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import playlist_manager as pm  # noqa: E402
from pipeline import series_links as sl  # noqa: E402
from pipeline import short_endcard as ec  # noqa: E402
from pipeline import viewer_requests as vr  # noqa: E402
from pipeline.analytics import competitor_rss as crss  # noqa: E402

DATA_CHANNELS = Path(__file__).resolve().parents[2] / "data" / "channels"


def _load_channel(cid):
    return json.loads((DATA_CHANNELS / f"{cid}.json").read_text(encoding="utf-8"))


# =====================================================================
# 再生リスト
# =====================================================================

class TestPlaylistTargets(unittest.TestCase):
    def test_short_and_main_go_to_different_playlists(self):
        cd = {
            "id": "x",
            "name": "テストch",
            "publish_settings": {"playlists": {"shorts": "S", "main": "M"}},
        }
        self.assertEqual(
            pm.resolve_playlist_titles("x", is_short=True, channel_dict=cd), ["S"]
        )
        self.assertEqual(
            pm.resolve_playlist_titles("x", is_short=False, channel_dict=cd), ["M"]
        )

    def test_defaults_when_unconfigured(self):
        """設定が無くてもチャンネル名から既定の受け皿を決める。"""
        cd = {"id": "x", "name": "テストch"}
        titles = pm.resolve_playlist_titles("x", is_short=True, channel_dict=cd)
        self.assertEqual(titles, ["テストch｜ショート"])

    def test_rules_add_extra_playlist_on_keyword_match(self):
        cd = {
            "id": "x",
            "name": "テストch",
            "publish_settings": {
                "playlists": {
                    "shorts": "S",
                    "rules": [{"match": ["睡眠"], "title": "睡眠シリーズ"}],
                }
            },
        }
        hit = pm.resolve_playlist_titles(
            "x", video_title="なぜ睡眠は必要か", is_short=True, channel_dict=cd
        )
        self.assertEqual(hit, ["S", "睡眠シリーズ"])
        miss = pm.resolve_playlist_titles(
            "x", video_title="なぜ空は青い", is_short=True, channel_dict=cd
        )
        self.assertEqual(miss, ["S"])

    def test_explicit_null_skips_default_bucket(self):
        """shorts: null は「ショートは再生リストに入れない」の意思表示。"""
        cd = {
            "id": "x",
            "name": "テストch",
            "publish_settings": {"playlists": {"shorts": None}},
        }
        self.assertEqual(
            pm.resolve_playlist_titles("x", is_short=True, channel_dict=cd), []
        )

    def test_disabled_channel_skips(self):
        cd = {"id": "x", "publish_settings": {"playlists": {"enabled": False}}}
        self.assertFalse(pm.is_enabled("x", cd))
        res = pm.add_video_to_playlists("x", "vid1", channel_dict=cd)
        self.assertEqual(res.get("skipped"), "disabled")

    def test_live_channels_are_enabled(self):
        for cid in ("daily-science", "scp-lab", "pokemon-lab"):
            cd = _load_channel(cid)
            self.assertTrue(pm.is_enabled(cid, cd), cid)
            self.assertTrue(pm.resolve_playlist_titles(cid, is_short=True, channel_dict=cd))


# =====================================================================
# シリーズ連続性（前回 / 次回）
# =====================================================================

class TestSeriesLinkBlocks(unittest.TestCase):
    def test_block_appended_at_end(self):
        out = sl.apply_block("本文です", sl.PREV_HEADER, "前の動画", "https://x/1")
        self.assertIn("本文です", out)
        self.assertIn(sl.PREV_HEADER, out)
        self.assertTrue(out.rstrip().endswith("https://x/1"))

    def test_reapplying_replaces_instead_of_stacking(self):
        """貼り直しても同じヘッダが2つ並ばない（毎回の投稿で積み上がるのを防ぐ）。"""
        once = sl.apply_block("本文", sl.NEXT_HEADER, "A", "https://x/a")
        twice = sl.apply_block(once, sl.NEXT_HEADER, "B", "https://x/b")
        self.assertEqual(twice.count(sl.NEXT_HEADER), 1)
        self.assertNotIn("https://x/a", twice)
        self.assertIn("https://x/b", twice)

    def test_prev_and_next_blocks_coexist(self):
        desc = sl.apply_block("本文", sl.PREV_HEADER, "前", "https://x/p")
        desc = sl.apply_block(desc, sl.NEXT_HEADER, "次", "https://x/n")
        self.assertIn(sl.PREV_HEADER, desc)
        self.assertIn(sl.NEXT_HEADER, desc)

    def test_respects_5000_char_limit(self):
        long_body = "あ" * 4990
        out = sl.apply_block(long_body, sl.PREV_HEADER, "前の動画", "https://x/1")
        self.assertLessEqual(len(out), sl.MAX_DESCRIPTION)
        self.assertIn("https://x/1", out)

    def test_history_tracks_short_and_main_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sl, "HISTORY_DIR", Path(tmp)):
                sl.record_upload("ch", "s1", title="S1", is_short=True)
                sl.record_upload("ch", "m1", title="M1", is_short=False)
                sl.record_upload("ch", "s2", title="S2", is_short=True)
                prev_short = sl.last_entry("ch", is_short=True, exclude_video_id="s2")
                prev_main = sl.last_entry("ch", is_short=False)
                self.assertEqual(prev_short["video_id"], "s1")
                self.assertEqual(prev_main["video_id"], "m1")

    def test_duplicate_record_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sl, "HISTORY_DIR", Path(tmp)):
                sl.record_upload("ch", "v1", title="V1", is_short=True)
                sl.record_upload("ch", "v1", title="V1", is_short=True)
                self.assertEqual(len(sl.read_history("ch")), 1)


class _FakeVideos:
    """videos().list/update の最小モック。update に渡った body を記録する。"""

    def __init__(self, snippet):
        self._snippet = snippet
        self.updated_body = None

    def list(self, **kwargs):
        snippet = self._snippet
        return mock.Mock(execute=lambda: {"items": [{"snippet": snippet}]})

    def update(self, **kwargs):
        self.updated_body = kwargs.get("body")
        return mock.Mock(execute=lambda: {})


class _FakeYouTube:
    def __init__(self, videos):
        self._videos = videos

    def videos(self):
        return self._videos


class TestSeriesLinkUpdate(unittest.TestCase):
    def test_update_preserves_required_snippet_fields(self):
        """videos.update は snippet 全置換。title/categoryId を落とすと 400 になる。"""
        videos = _FakeVideos(
            {
                "title": "元タイトル",
                "description": "本文",
                "categoryId": "24",
                "tags": ["a", "b"],
                "defaultLanguage": "ja",
            }
        )
        res = sl.update_description(
            "ch",
            "vid",
            header=sl.NEXT_HEADER,
            link_title="次の動画",
            link_url="https://x/next",
            youtube=_FakeYouTube(videos),
        )
        self.assertTrue(res["ok"])
        body = videos.updated_body
        self.assertEqual(body["id"], "vid")
        self.assertEqual(body["snippet"]["title"], "元タイトル")
        self.assertEqual(body["snippet"]["categoryId"], "24")
        self.assertEqual(body["snippet"]["tags"], ["a", "b"])
        self.assertIn("https://x/next", body["snippet"]["description"])

    def test_no_update_call_when_nothing_changes(self):
        desc = sl.apply_block("本文", sl.PREV_HEADER, "前", "https://x/p")
        videos = _FakeVideos({"title": "t", "description": desc, "categoryId": "27"})
        res = sl.update_description(
            "ch",
            "vid",
            header=sl.PREV_HEADER,
            link_title="前",
            link_url="https://x/p",
            youtube=_FakeYouTube(videos),
        )
        self.assertTrue(res.get("unchanged"))
        self.assertIsNone(videos.updated_body)


# =====================================================================
# 視聴者参加型（リクエスト募集）
# =====================================================================

class TestViewerRequests(unittest.TestCase):
    def test_block_contains_header_and_prompt(self):
        cd = {
            "id": "x",
            "publish_settings": {
                "viewer_requests": {"prompt": "テーマ送って", "show_top_demands": False}
            },
        }
        lines = vr.build_request_block("x", channel_dict=cd)
        self.assertEqual(lines[0], vr.HEADER)
        self.assertIn("テーマ送って", lines)

    def test_disabled_returns_empty(self):
        cd = {"id": "x", "publish_settings": {"viewer_requests": {"enabled": False}}}
        self.assertEqual(vr.build_request_block("x", channel_dict=cd), [])
        self.assertEqual(vr.build_comment_line("x", channel_dict=cd), "")

    def test_top_demands_rendered_when_available(self):
        cd = {"id": "x", "publish_settings": {"viewer_requests": {}}}
        with mock.patch.object(
            vr, "top_demands", return_value=["猫の睡眠", "深海生物"]
        ):
            lines = vr.build_request_block("x", channel_dict=cd)
        self.assertTrue(any("猫の睡眠" in ln and "深海生物" in ln for ln in lines))

    def test_top_demands_survive_missing_analytics(self):
        """DB が無い/壊れていてもブロック生成は止まらない。"""
        with mock.patch(
            "pipeline.analytics.store.list_comment_demands", side_effect=RuntimeError("no db")
        ):
            self.assertEqual(vr.top_demands("x"), [])

    def test_appears_in_generated_descriptions(self):
        from pipeline import video_generator as vg

        cd = _load_channel("daily-science")
        with mock.patch.object(vr, "top_demands", return_value=[]):
            out = vg.generate_descriptions(
                "なぜ眠くなるのか",
                [{"speaker": "真", "text": "テスト"}],
                channel_dict=cd,
            )
        self.assertIn(vr.HEADER, out["short"])
        self.assertIn(vr.HEADER, out["main"])

    def test_appears_in_auto_comment(self):
        from pipeline import auto_comment as ac

        cd = _load_channel("daily-science")
        text = ac.build_comment_text("daily-science", title="t", channel_dict=cd)
        self.assertIn(vr.build_comment_line("daily-science", channel_dict=cd), text)


# =====================================================================
# 競合 RSS 監視
# =====================================================================

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>ライバル解説チャンネル</title>
  <entry>
    <id>yt:video:AAAAAAAAAAA</id>
    <yt:videoId>AAAAAAAAAAA</yt:videoId>
    <title>【衝撃】睡眠の新常識を解説</title>
    <published>2026-08-19T09:00:00+00:00</published>
  </entry>
  <entry>
    <id>yt:video:BBBBBBBBBBB</id>
    <yt:videoId>BBBBBBBBBBB</yt:videoId>
    <title>睡眠と夢のふしぎ</title>
    <published>2026-08-18T09:00:00Z</published>
  </entry>
</feed>
"""


class TestCompetitorRss(unittest.TestCase):
    def test_parse_extracts_video_ids_and_times(self):
        parsed = crss.parse_feed(SAMPLE_FEED)
        self.assertEqual(parsed["competitor_title"], "ライバル解説チャンネル")
        self.assertEqual(len(parsed["entries"]), 2)
        first = parsed["entries"][0]
        self.assertEqual(first["video_id"], "AAAAAAAAAAA")
        self.assertEqual(first["link"], "https://www.youtube.com/watch?v=AAAAAAAAAAA")
        self.assertIsNotNone(first["published_ts"])
        # "Z" 表記の方もパースできる（両方の表記が実際に来る）
        self.assertIsNotNone(parsed["entries"][1]["published_ts"])

    def test_broken_xml_does_not_raise(self):
        self.assertEqual(crss.parse_feed("<not xml")["entries"], [])

    def test_hot_keywords_prefers_words_shared_by_competitors(self):
        videos = [
            {"competitor_id": "UC1", "title": "睡眠の新常識"},
            {"competitor_id": "UC2", "title": "睡眠と夢の関係"},
            {"competitor_id": "UC1", "title": "深海生物の話"},
        ]
        kws = crss.hot_keywords(videos, limit=5)
        self.assertTrue(kws)
        self.assertEqual(kws[0]["keyword"], "睡眠")
        self.assertEqual(kws[0]["competitors"], 2)

    def test_watch_targets_use_channel_competitors(self):
        targets = crss.watch_targets("daily-science")
        self.assertTrue(targets)
        self.assertTrue(all(t.startswith("UC") for t in targets))

    def test_scan_records_only_new_videos(self):
        seen = {"calls": 0}

        def _fake_insert(**kwargs):
            seen["calls"] += 1
            return seen["calls"] <= 2  # 1周目だけ新規

        with mock.patch.object(crss, "watch_targets", return_value=["UC_TEST"]), \
             mock.patch.object(crss, "fetch_feed", return_value=SAMPLE_FEED), \
             mock.patch.object(crss.analytics_store, "insert_rss_video", _fake_insert):
            first = crss.scan_channel("x", since_hours=24 * 365 * 100)
            second = crss.scan_channel("x", since_hours=24 * 365 * 100)
        self.assertEqual(first["new_videos"], 2)
        self.assertEqual(second["new_videos"], 0)

    def test_failed_feed_does_not_abort_scan(self):
        with mock.patch.object(crss, "watch_targets", return_value=["UC_A", "UC_B"]), \
             mock.patch.object(crss, "fetch_feed", side_effect=[None, SAMPLE_FEED]), \
             mock.patch.object(crss.analytics_store, "insert_rss_video", return_value=True):
            res = crss.scan_channel("x", since_hours=24 * 365 * 100)
        self.assertEqual(res["failed_feeds"], ["UC_A"])
        self.assertEqual(res["new_videos"], 2)


# =====================================================================
# エンドカード
# =====================================================================

class TestShortEndcard(unittest.TestCase):
    def test_enabled_by_default_and_disableable(self):
        self.assertTrue(ec.is_enabled({}))
        self.assertFalse(ec.is_enabled({"defaults": {"short_endcard": {"enabled": False}}}))

    def test_duration_is_clamped(self):
        self.assertEqual(ec.duration_for({"defaults": {"short_endcard": {"duration": 99}}}),
                         ec.MAX_DURATION)
        self.assertEqual(ec.duration_for({"defaults": {"short_endcard": {"duration": 0.1}}}),
                         ec.MIN_DURATION)
        self.assertAlmostEqual(ec.duration_for({}), ec.DEFAULT_DURATION)

    def test_texts_fall_back_to_channel_name(self):
        texts = ec.build_texts({"name": "テストch"})
        self.assertEqual(texts["headline"], ec.DEFAULT_HEADLINE)
        self.assertEqual(texts["sub"], "テストch")

    def test_render_image_has_short_dimensions(self):
        img = ec.render_image(216, 384, {"name": "テストch"})
        self.assertEqual(img.size, (216, 384))

    def test_append_adds_exactly_one_clip(self):
        clips = [object(), object()]
        with mock.patch.object(ec, "make_clip", return_value=object()):
            out = ec.append_to_clips(clips, width=1080, height=1920, channel_dict={})
        self.assertEqual(len(out), 3)

    def test_append_is_noop_when_disabled(self):
        clips = [object()]
        out = ec.append_to_clips(
            clips,
            width=1080,
            height=1920,
            channel_dict={"defaults": {"short_endcard": {"enabled": False}}},
        )
        self.assertEqual(out, clips)

    def test_append_survives_render_failure(self):
        """エンドカードの失敗で動画生成そのものを落とさない。"""
        clips = [object()]
        with mock.patch.object(ec, "make_clip", side_effect=RuntimeError("boom")):
            out = ec.append_to_clips(clips, width=1080, height=1920, channel_dict={})
        self.assertEqual(out, clips)

    def test_live_channels_have_endcard_enabled(self):
        for cid in ("daily-science", "scp-lab", "yokai-watch"):
            self.assertTrue(ec.is_enabled(_load_channel(cid)), cid)


if __name__ == "__main__":
    unittest.main()
