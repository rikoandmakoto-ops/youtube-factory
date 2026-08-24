"""ショート尺・サムネ配色・連投ガードの単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_short_format -v

守りたい回帰:
  - ショート専用チャンネルに長尺用の target_duration(=720秒) が漏れない
    （autopilot が duration_minutes*12分 から 720 を渡すため、company-facts の
     ファクトオーバーレイのプロンプトが「合計約720秒」になり、実測 76〜97秒の
     ショートが量産されていた）
  - ファクト数と文字数上限が目標尺から逆算され、30〜45秒帯に収まる
  - サムネの配色がチャンネルの thumbnail_template から引かれる
    （以前は HTML テンプレート側が色をハードコードしていて、8ch すべて同じ
     見た目になり、ブラウズ面でチャンネルを見分けられなかった）
  - 連投ガードが最小間隔内の2回目の発火を落とす
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.auto_scenario import generator as gen  # noqa: E402
from pipeline import thumbnail_generator as tg  # noqa: E402

DATA_CHANNELS = Path(__file__).resolve().parents[2] / "data" / "channels"


class _FakeChannel:
    def __init__(self, defaults=None):
        self.defaults = defaults or {}


class TestShortDurationClamp(unittest.TestCase):
    def test_longform_default_is_clamped(self):
        """autopilot が渡す 720秒（12分）をショート帯に丸める。"""
        ch = _FakeChannel({"target_duration": 40})
        self.assertEqual(gen._clamp_short_duration(ch, 720), 40)

    def test_falls_back_to_default_when_nothing_usable(self):
        ch = _FakeChannel({"target_duration": 720})
        self.assertEqual(
            gen._clamp_short_duration(ch, 720), gen.SHORT_DURATION_DEFAULT
        )

    def test_explicit_short_duration_wins(self):
        ch = _FakeChannel({"target_duration": 40})
        self.assertEqual(gen._clamp_short_duration(ch, 45), 45)

    def test_garbage_config_does_not_raise(self):
        for bad in ({}, {"target_duration": None}, {"target_duration": "abc"}):
            self.assertEqual(
                gen._clamp_short_duration(_FakeChannel(bad), None),
                gen.SHORT_DURATION_DEFAULT,
            )

    def test_result_always_in_sweet_spot(self):
        ch = _FakeChannel({"target_duration": 40})
        for td in (0, 5, 45, 300, 720, 3600):
            got = gen._clamp_short_duration(ch, td)
            self.assertGreaterEqual(got, gen.SHORT_DURATION_MIN)
            self.assertLessEqual(got, gen.SHORT_DURATION_MAX)


class TestFactsOverlayLength(unittest.TestCase):
    """ファクト数 × 1画面あたりの秒数が目標尺に収まること。"""

    @staticmethod
    def _fact_count(target_duration: int) -> int:
        fact_seconds = max(20, target_duration - gen._FACTS_CTA_SECONDS)
        return max(5, min(8, round(fact_seconds / gen._FACTS_SECONDS_PER_SCREEN)))

    def test_estimated_runtime_stays_under_50s(self):
        for td in (30, 35, 40, 45, 50):
            n = self._fact_count(td)
            est = n * gen._FACTS_SECONDS_PER_SCREEN + gen._FACTS_CTA_SECONDS
            self.assertLessEqual(est, 50, f"target={td}s → 推定 {est}s")
            self.assertGreaterEqual(est, 30, f"target={td}s → 推定 {est}s")

    def test_fact_count_never_explodes_on_longform_value(self):
        """720 が漏れてきても画面数は8で頭打ち（旧実装は9まで許していた）。"""
        self.assertEqual(self._fact_count(720), 8)


class TestThumbnailPalette(unittest.TestCase):
    def test_defaults_match_previous_look(self):
        """設定なしのときは従来の白見出し+黄フック+赤バッジを維持する。"""
        p = tg._resolve_palette(None)
        self.assertEqual(p["line1"], "#FFFFFF")
        self.assertEqual(p["line2"], "#FFEB3C")
        self.assertTrue(p["badge_bg"].startswith("rgba(220, 40, 40"))

    def test_channel_colors_drive_palette(self):
        cfg = {
            "thumbnail_template": {
                "badge_color": [40, 90, 200],
                "hook_color": [255, 222, 0],
                "subtitle_color": [255, 190, 205],
            }
        }
        p = tg._resolve_palette(cfg)
        self.assertEqual(p["line2"], "#FFDE00")
        self.assertEqual(p["sub"], "#FFBECD")
        self.assertTrue(p["badge_bg"].startswith("rgba(40, 90, 200"))

    def test_explicit_palette_overrides(self):
        cfg = {
            "thumbnail_template": {
                "badge_color": [40, 90, 200],
                "palette": {"line2": "#00FF00"},
            }
        }
        self.assertEqual(tg._resolve_palette(cfg)["line2"], "#00FF00")

    def test_channels_are_visually_distinct(self):
        """投稿中のチャンネル同士が同じ配色にならないこと。"""
        seen = {}
        for path in sorted(DATA_CHANNELS.glob("*.json")):
            conf = json.loads(path.read_text())
            if not (conf.get("autopilot") or {}).get("enabled"):
                continue
            p = tg._resolve_palette(conf)
            key = (p["line2"], p["badge_bg"], p["sub"])
            self.assertNotIn(
                key, seen,
                f"{path.stem} のサムネ配色が {seen.get(key)} と同一",
            )
            seen[key] = path.stem
        self.assertGreaterEqual(len(seen), 5)

    def test_build_html_has_no_unfilled_placeholders(self):
        import base64
        import tempfile

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z"
            "8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        bg = Path(tempfile.mkdtemp()) / "bg.png"
        bg.write_bytes(png)
        brief = {
            "line1": "見出し", "line2": "主役の行",
            "line3_badge": "バッジ", "sub_text": "補足",
        }
        html = tg.build_html(brief, bg, None, None, None)
        style = html.split("<style>")[1].split("</style>")[0]
        # `{c_line2}` のような .format プレースホルダが残っていないこと
        # （CSS のブロック `{ ... }` とは区別するため識別子の形で照合する）。
        leftovers = re.findall(r"\{[a-z_][a-z0-9_]*\}", style)
        self.assertEqual(leftovers, [], f"未展開のプレースホルダ: {leftovers}")
        self.assertIn("drop-shadow", style)


class TestBurstGuard(unittest.TestCase):
    def setUp(self):
        import api_channel_autopilot as ap

        self.ap = ap
        ap._last_fire_at.clear()
        self.addCleanup(ap._last_fire_at.clear)

    def test_second_fire_within_window_is_dropped(self):
        self.assertTrue(self.ap._burst_guard_ok("ch", {}))
        self.assertFalse(self.ap._burst_guard_ok("ch", {}))

    def test_other_channels_unaffected(self):
        self.assertTrue(self.ap._burst_guard_ok("ch-a", {}))
        self.assertTrue(self.ap._burst_guard_ok("ch-b", {}))

    def test_can_be_disabled_per_channel(self):
        cfg = {"min_fire_interval_minutes": 0}
        self.assertTrue(self.ap._burst_guard_ok("ch", cfg))
        self.assertTrue(self.ap._burst_guard_ok("ch", cfg))

    def test_misfire_grace_never_exceeds_lead(self):
        """遅延許容が公開リード時間を超えると予約公開が成立しなくなる。"""
        for lead in (0, 15, 30, 45, 120):
            grace = self.ap._misfire_grace_seconds(lead)
            self.assertLessEqual(grace, 1200)
            self.assertGreaterEqual(grace, 300)
            if lead:
                self.assertLessEqual(grace, lead * 60)


class TestChannelShortFormats(unittest.TestCase):
    def test_short_channels_target_the_sweet_spot(self):
        """ショート専用チャンネルの想定尺が 25〜45秒に収まること。

        下限は当初 29.0 秒だったが、2026-08-23 の実測（維持率45〜70%の動画で
        推定尺26.0秒の短い側が 1本あたり登録者 0.838、推定尺35.8秒の長い側が
        0.632 = 1.33倍）を受けて各チャンネルの total_chars_min を短縮したため、
        テスト側の下限もそれに合わせる。現在の設定値は
        daily-science 240字 = 27.0秒、scp-lab 230字 = 25.8秒。
        """
        for path in sorted(DATA_CHANNELS.glob("*.json")):
            conf = json.loads(path.read_text())
            ap = conf.get("autopilot") or {}
            if not ap.get("enabled") or ap.get("gen_type") != "short":
                continue
            sf = conf.get("short_format") or {}
            if not sf:
                continue  # 既定の8行ルールを使う（generator 側で担保）
            lo = sf.get("total_chars_min")
            hi = sf.get("total_chars_max")
            # VOICEVOX 1.3x の実効読み上げ速度 ≒ 8.9 字/秒
            self.assertGreaterEqual(lo / 8.9, 25.0, f"{path.stem} が短すぎる")
            self.assertLessEqual(hi / 8.9, 45.0, f"{path.stem} が長すぎる")


if __name__ == "__main__":
    unittest.main()
