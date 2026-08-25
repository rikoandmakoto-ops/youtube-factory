"""縦サムネ（1080x1920）の中間帯に short_illustrations を差し込む処理のテスト。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_short_thumbnail_illustration -v

守りたい回帰:
  テキストが上 1/3 に固まり、キャラが下端に貼り付き、その間の
  y=1030〜1350（約 320px＝画面の 17%）が全チャンネルで完全な無地だった。
  図解カードが用意できたときだけそこを埋め、用意できないときは
  従来どおり無地に倒すこと（サムネ生成が落ちないことが最優先）。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from pipeline import video_generator as vg  # noqa: E402


class TestFindCachedIllustration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_without_cache_dir(self):
        self.assertIsNone(vg._thumb_find_cached_illustration(self.out))

    def test_picks_dalle_card_before_pillow(self):
        cache = self.out / "short_illustrations"
        cache.mkdir()
        Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(cache / "illust_000.png")
        Image.new("RGBA", (40, 20), (0, 255, 0, 255)).save(cache / "pillow_000.png")
        img = vg._thumb_find_cached_illustration(self.out)
        self.assertIsNotNone(img)
        self.assertEqual(img.getpixel((0, 0))[:3], (255, 0, 0))

    def test_falls_back_to_pillow_card(self):
        cache = self.out / "short_illustrations"
        cache.mkdir()
        Image.new("RGBA", (40, 20), (0, 255, 0, 255)).save(cache / "pillow_001.png")
        img = vg._thumb_find_cached_illustration(self.out)
        self.assertIsNotNone(img)
        self.assertEqual(img.getpixel((0, 0))[:3], (0, 255, 0))

    def test_corrupt_file_does_not_raise(self):
        cache = self.out / "short_illustrations"
        cache.mkdir()
        (cache / "illust_000.png").write_bytes(b"not a png")
        self.assertIsNone(vg._thumb_find_cached_illustration(self.out))


class TestBuildIllustrationGating(unittest.TestCase):
    """自動描画は「本物の図解になる」条件が揃ったときだけ。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_disabled_channel_gets_nothing(self):
        self.assertIsNone(vg._thumb_build_illustration(
            self.out, "テーマ", {"short_illustrations": {"enabled": False}}))

    def test_keyword_icons_off_gets_nothing(self):
        # keyword_icons=false の Pillow 図解はほぼ文字だけのカードになり、
        # 真上の見出しと同じ文字を繰り返してしまう。
        self.assertIsNone(vg._thumb_build_illustration(
            self.out, "テーマ",
            {"short_illustrations": {"enabled": True, "keyword_icons": False}}))

    def test_empty_topic_gets_nothing(self):
        self.assertIsNone(vg._thumb_build_illustration(
            self.out, "   ", {"short_illustrations": {"enabled": True}}))

    def test_cache_wins_even_when_channel_disabled(self):
        """本編が既に描いた絵は、設定に関係なくサムネと本編で揃えたい。"""
        cache = self.out / "short_illustrations"
        cache.mkdir()
        Image.new("RGBA", (40, 20), (0, 0, 255, 255)).save(cache / "illust_000.png")
        img = vg._thumb_build_illustration(
            self.out, "テーマ", {"short_illustrations": {"enabled": False}})
        self.assertIsNotNone(img)


class TestPasteIllustration(unittest.TestCase):
    def _canvas(self):
        return Image.new("RGBA", (1080, 1920), (10, 5, 150, 255))

    def test_skips_band_that_is_too_short(self):
        canvas = self._canvas()
        illust = Image.new("RGBA", (600, 400), (255, 255, 255, 255))
        band_h = vg.THUMB_ILLUST_MIN_BAND_H - 1
        self.assertIsNone(
            vg._thumb_paste_illustration(canvas, illust, 1030, 1030 + band_h))

    def test_stays_inside_the_band(self):
        canvas = self._canvas()
        illust = Image.new("RGBA", (900, 600), (255, 255, 255, 255))
        box = vg._thumb_paste_illustration(canvas, illust, 1030, 1350)
        self.assertIsNotNone(box)
        x0, y0, x1, y1 = box
        self.assertGreaterEqual(y0, 1030)
        self.assertLessEqual(y1, 1350)
        self.assertGreaterEqual(x0, 0)
        self.assertLessEqual(x1, 1080)

    def test_actually_paints_the_empty_band(self):
        """無地帯が埋まっていること（回帰の本体）。"""
        canvas = self._canvas()
        before = canvas.getpixel((540, 1190))
        illust = Image.new("RGBA", (900, 600), (255, 255, 255, 255))
        vg._thumb_paste_illustration(canvas, illust, 1030, 1350)
        self.assertNotEqual(canvas.getpixel((540, 1190)), before)

    def test_none_illustration_is_a_noop(self):
        canvas = self._canvas()
        self.assertIsNone(vg._thumb_paste_illustration(canvas, None, 1030, 1350))


class TestGenerateShortThumbnail(unittest.TestCase):
    """生成そのものが落ちないこと。channel_format 無しは従来の無地レイアウト。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        self.thumb_info = {
            "hook_lines": ["99%が知らない"],
            "subtitle": "暗い場所を出た直後だけ白く飛ぶ理由",
            "tagline": "今日の1分科学",
        }

    def tearDown(self):
        self._tmp.cleanup()

    def test_without_channel_format_is_plain(self):
        path = vg.generate_short_thumbnail(
            "テストタイトル", "t", str(self.out), thumb_info=self.thumb_info,
            char_config={})
        img = Image.open(path)
        self.assertEqual(img.size, (1080, 1920))
        # short_illustrations キャッシュを作っていないこと
        self.assertFalse((self.out / "short_illustrations").exists())

    def test_cached_card_is_composited(self):
        cache = self.out / "short_illustrations"
        cache.mkdir()
        Image.new("RGBA", (900, 500), (255, 255, 255, 255)).save(cache / "illust_000.png")
        path = vg.generate_short_thumbnail(
            "テストタイトル", "t", str(self.out), thumb_info=self.thumb_info,
            char_config={}, channel_format={"short_illustrations": {"enabled": True}})
        img = Image.open(path).convert("RGB")
        # 中間帯に白いカードが載っている（無地のグラデーションのままではない）
        band = [img.getpixel((540, y)) for y in range(1100, 1300, 20)]
        self.assertTrue(any(sum(p) > 600 for p in band), f"no card in band: {band}")


if __name__ == "__main__":
    unittest.main()
