"""2026-09-16 — ショートサムネのレイアウト（上 70% に収める）。

Shorts のフィードでは下 30% が題名・ボタンの UI に隠れる。従来はテキストが
中央・立ち絵が最下端で、上 40% が空いたまま下 30% が隠れていた。
  - テキスト塊は上端（TEXT_TOP）から
  - 立ち絵は中段右、底は SAFE_BOTTOM（70%）
  - 読ませる文字列はバッジ＋見出し（最大2行）＋副題1行
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ShortThumbnailLayoutTest(unittest.TestCase):
    def test_layout_constants_in_source(self):
        import inspect
        from pipeline import video_generator as vg
        src = inspect.getsource(vg.generate_short_thumbnail)
        self.assertIn("SAFE_BOTTOM = int(SH * 0.70)", src)
        self.assertIn("TEXT_TOP = int(_tt.get(\"short_text_top\") or 200)", src)
        self.assertIn("paste_y = band_bottom - s_h", src, "立ち絵の底が SAFE_BOTTOM に揃っていない")
        self.assertIn('max_total_lines=int(_st.get("hook_max_lines", 2))', src)
        self.assertNotIn("paste_y = SH - s_h - 40", src, "立ち絵が最下端に戻っている")

    def test_render_keeps_everything_above_70_percent(self):
        """実際に描いて、下 30% が背景のまま（文字・立ち絵が無い）ことを確認する。"""
        from PIL import Image
        from pipeline import video_generator as vg
        with tempfile.TemporaryDirectory() as d:
            ch = {"id": "t", "name": "t", "thumbnail_template": {
                "badge_text": "テスト", "short_bg_gradient": {
                    "top": [10, 10, 40], "bottom": [10, 10, 40], "orb": [10, 10, 40], "dot": [10, 10, 40]}}}
            chars = {"理子": {"side": "left"}, "真": {"side": "right"}}
            p = vg.generate_short_thumbnail(
                "テストのタイトル", "t", d,
                thumb_info={"hook_lines": ["一行目の見出し", "二行目の見出し"],
                            "subtitle": "副題です", "tagline": "帯の文言"},
                channel_dict=ch, char_config=chars, channel_format=None, channel_id="t")
            im = Image.open(p).convert("RGB")
            w, h = im.size
            self.assertEqual((w, h), (1080, 1920))
            # 下 30% は単色（グラデを単色にしてあるので、描画物があれば色が変わる）
            bottom = im.crop((0, int(h * 0.71), w, h))
            colors = bottom.getcolors(maxcolors=64)
            self.assertIsNotNone(colors, "下 30% に文字か立ち絵が描かれている")
            # 上 30% には文字（明るい画素）がある
            top = im.crop((0, 0, w, int(h * 0.3))).convert("L")
            self.assertGreater(top.getextrema()[1], 200, "上部にテキストが無い")


if __name__ == "__main__":
    unittest.main()
