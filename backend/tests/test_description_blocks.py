"""pipeline.description_blocks とアップロード用タグ生成の単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_description_blocks -v

守りたい回帰:
  - ハッシュタグが5個を超えない（YouTube は15個超で全無視、表示は先頭3個）
  - アップロード用タグが defaults.hashtags の4〜6個で頭打ちにならない
    （video_format.youtube.default_tags を merge_channel_defaults が
     上書きしていたため、以前は死に設定だった）
  - youtube_channel_id 未設定のチャンネルに存在しないURLを載せない
"""

import os
import sys
import unittest

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import description_blocks as db  # noqa: E402
from channels import ChannelManager  # noqa: E402


class TestNormalizeHashtags(unittest.TestCase):
    def test_caps_at_five(self):
        out = db.normalize_hashtags("#a #b #c #d #e #f #g")
        self.assertEqual(out, "#a #b #c #d #e")

    def test_dedupes_case_insensitively(self):
        out = db.normalize_hashtags("#SCP #scp #SCP財団")
        self.assertEqual(out, "#SCP #SCP財団")

    def test_required_comes_first(self):
        out = db.normalize_hashtags("#雑学 #科学", required=["shorts"])
        self.assertTrue(out.startswith("#shorts "))

    def test_required_not_duplicated(self):
        out = db.normalize_hashtags("#shorts #雑学", required=["shorts"])
        self.assertEqual(out.count("#shorts"), 1)

    def test_accepts_list(self):
        self.assertEqual(db.normalize_hashtags(["科学", "#雑学"]), "#科学 #雑学")

    def test_strips_spaces_that_would_split_tags(self):
        # 空白入りはタグとして割れるので詰める
        self.assertEqual(db.normalize_hashtags(["ゆっくり 解説"]), "#ゆっくり解説")

    def test_empty_input(self):
        self.assertEqual(db.normalize_hashtags(None), "")


class TestKeywordLead(unittest.TestCase):
    def _ch(self):
        return {
            "id": "test-ch",
            "name": "テストch",
            "concept": "テスト用のコンセプト。二文目はリードでは切られる。",
            "defaults": {"hashtags": ["#雑学"]},
            "video_format": {"youtube": {"default_tags": ["科学", "豆知識"]}},
        }

    def test_contains_title_and_keywords(self):
        lines = db.build_keyword_lead(self._ch(), "水の話", hook="なぜ水は青い？")
        text = "\n".join(lines)
        self.assertIn("水の話", text)
        self.assertIn("なぜ水は青い？", text)
        self.assertIn("科学", text)
        self.assertIn("豆知識", text)

    def test_lead_template_override(self):
        ch = self._ch()
        ch["description_template"] = {"lead_template": "『{title}』を{channel}がまとめました。"}
        text = "\n".join(db.build_keyword_lead(ch, "スレの話"))
        self.assertIn("まとめました", text)
        self.assertNotIn("解説します", text)

    def test_bad_lead_template_falls_back(self):
        ch = self._ch()
        ch["description_template"] = {"lead_template": "{missing_key}"}
        text = "\n".join(db.build_keyword_lead(ch, "お題"))
        self.assertIn("お題", text)


class TestChannelLinks(unittest.TestCase):
    def test_no_links_without_youtube_channel_id(self):
        ch = {"id": "ghost-ch", "name": "無連携ch", "concept": ""}
        self.assertEqual(db.build_related_block(ch), [])
        self.assertEqual(db.build_subscribe_block(ch, compact=True),
                         ["🔔 チャンネル登録＆高評価で応援お願いします！"])

    def test_related_links_override(self):
        ch = {
            "id": "x",
            "description_template": {
                "related_links": [{"title": "前回", "url": "https://youtu.be/abc"}]
            },
        }
        lines = db.build_related_block(ch)
        self.assertIn("▼ 関連動画", lines[0])
        self.assertIn("https://youtu.be/abc", lines[1])

    def test_cross_promo_disabled(self):
        ch = {"id": "daily-science", "description_template": {"disable_cross_promo": True}}
        self.assertEqual(db.build_cross_promo_block(ch), [])

    def test_cross_promo_never_points_at_itself(self):
        ch = {"id": "daily-science", "description_template": {
            "cross_promote": ["daily-science", "scp-lab"]
        }}
        lines = db.build_cross_promo_block(ch)
        self.assertTrue(all("daily-science" not in ln for ln in lines))

    def test_cross_promo_limit_counts_channels_not_lines(self):
        # 1チャンネルにつき2行（名前＋URL）出るので、行数で数えると1件で打ち切られる
        ch = {"id": "daily-science", "description_template": {
            "cross_promote": ["scp-lab", "akashic-librarian"]
        }}
        lines = db.build_cross_promo_block(ch, limit=2)
        self.assertEqual(sum(1 for ln in lines if ln.startswith("・")), 2)


class TestUploadTags(unittest.TestCase):
    """実チャンネル設定でのタグ生成（回帰テスト）。"""

    @classmethod
    def setUpClass(cls):
        cls.cm = ChannelManager()

    def test_default_tags_not_clobbered_by_hashtags(self):
        """merge_channel_defaults が default_tags を潰さないこと。"""
        for ch in self.cm.list_channels():
            with self.subTest(channel=ch.id):
                self.assertGreaterEqual(
                    len(ch.video_format.youtube.default_tags), 4,
                    f"{ch.id}: default_tags が空 or 縮んでいる",
                )

    def test_upload_tags_are_richer_than_hashtags(self):
        for ch in self.cm.list_channels():
            with self.subTest(channel=ch.id):
                self.assertGreaterEqual(
                    len(ch.get_upload_tags()), len(ch.get_hashtags()),
                )

    def test_upload_tags_have_no_hash_prefix(self):
        for ch in self.cm.list_channels():
            with self.subTest(channel=ch.id):
                self.assertTrue(all(not t.startswith("#") for t in ch.get_upload_tags()))

    def test_upload_tags_within_youtube_limit(self):
        """YouTube のタグ合計は500文字上限。"""
        for ch in self.cm.list_channels():
            with self.subTest(channel=ch.id):
                total = sum(len(t) + 1 for t in ch.get_upload_tags())
                self.assertLessEqual(total, 500)

    def test_shorts_tag_prepended(self):
        ch = self.cm.list_channels()[0]
        self.assertEqual(ch.get_upload_tags(is_short=True)[0], "Shorts")
        self.assertNotIn("Shorts", ch.get_upload_tags(is_short=False))

    def test_upload_tags_deduped(self):
        for ch in self.cm.list_channels():
            with self.subTest(channel=ch.id):
                tags = [t.lower() for t in ch.get_upload_tags()]
                self.assertEqual(len(tags), len(set(tags)))

    def test_max_chars_truncates(self):
        ch = self.cm.list_channels()[0]
        self.assertLessEqual(sum(len(t) + 1 for t in ch.get_upload_tags(max_chars=20)), 20)


class TestRealChannelHashtags(unittest.TestCase):
    """実チャンネルの description_template ハッシュタグが5個以内であること。"""

    def test_hashtag_count(self):
        cm = ChannelManager()
        for ch in cm.list_channels():
            tmpl = ch._raw.get("description_template") or {}
            for key in ("main_hashtags", "short_hashtags"):
                raw = tmpl.get(key)
                if not raw:
                    continue
                with self.subTest(channel=ch.id, key=key):
                    self.assertLessEqual(len(raw.split()), db.HASHTAG_MAX)


if __name__ == "__main__":
    unittest.main(verbosity=2)
