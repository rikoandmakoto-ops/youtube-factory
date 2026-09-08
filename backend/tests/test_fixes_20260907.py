"""2026-09-07 の修正の回帰テスト。

対象:
  1. 【ショート】の二重付与 — 既にマーカーが付いたタイトルに再付与しないこと
  2. thumbnail_ab_tests の書き戻し — CTR(比率) 列に代理指標(1日あたり再生数)の
     実数が入らないこと
  3. dup_check — theme_blacklist に入れた題材を毎日再報告しないこと
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# 1. 【ショート】の二重付与
# ---------------------------------------------------------------------------
class TestShortSuffix(unittest.TestCase):
    def test_appends_once(self):
        from pipeline.short_title import with_short_suffix
        self.assertEqual(with_short_suffix("妖怪の正体"), "妖怪の正体【ショート】")

    def test_does_not_double_append(self):
        from pipeline.short_title import with_short_suffix
        # 実際に公開されてしまった型: 「〜秘密【ショート】【ショート】」
        already = "なぜロボニャンだけ未来から来た？隠された時系列の秘密【ショート】"
        self.assertEqual(with_short_suffix(already), already)

    def test_marker_anywhere_counts_as_present(self):
        from pipeline.short_title import with_short_suffix
        mid = "妖怪の正体【ショート】 #shorts"
        self.assertEqual(with_short_suffix(mid), mid)

    def test_empty_stays_empty(self):
        """空文字にマーカーだけ付けた無意味なタイトルを作らない。"""
        from pipeline.short_title import with_short_suffix
        self.assertEqual(with_short_suffix(""), "")
        self.assertEqual(with_short_suffix(None), "")

    def test_call_sites_use_the_helper(self):
        """4箇所のフォールバックが素の文字列連結に戻っていないこと。"""
        root = Path(__file__).resolve().parents[1]
        for name in ("api_phase3.py", "api_phase4.py", "republish_short.py"):
            src = (root / name).read_text(encoding="utf-8")
            for line in src.splitlines():
                if "【ショート】" not in line or line.lstrip().startswith("#"):
                    continue
                self.assertNotIn(
                    '+ "【ショート】"', line,
                    f"{name}: 素の連結が復活している -> {line.strip()}",
                )
                self.assertNotIn(
                    '}【ショート】', line,
                    f"{name}: f-string の素の連結が復活している -> {line.strip()}",
                )


# ---------------------------------------------------------------------------
# 2. thumbnail_ab_tests の書き戻し（単位混在）
# ---------------------------------------------------------------------------
class TestThumbnailAbWriteback(unittest.TestCase):
    def setUp(self):
        from pipeline.analytics import thumbnail_ab_test as ab
        self.ab = ab
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_db = ab.DB_PATH
        ab.DB_PATH = Path(self.tmp.name) / "analytics.db"
        ab._init_table()
        with sqlite3.connect(str(ab.DB_PATH)) as c:
            now = ab._now()
            c.execute(
                "INSERT INTO thumbnail_ab_tests "
                "(video_id, channel_id, variants_json, created_at, updated_at, next_check_at) "
                "VALUES (?,?,?,?,?,?)",
                ("vid1", "daily-science", "[]", now, now, now),
            )

    def tearDown(self):
        self.ab.DB_PATH = self._orig_db
        self.tmp.cleanup()

    def _row(self):
        with sqlite3.connect(str(self.ab.DB_PATH)) as c:
            c.row_factory = sqlite3.Row
            return dict(c.execute(
                "SELECT * FROM thumbnail_ab_tests WHERE video_id='vid1'"
            ).fetchone())

    def test_ratio_is_stored(self):
        self.ab._update_row("vid1", {"channel_avg_ctr": 0.033, "last_check_ctr": 0.014})
        r = self._row()
        self.assertAlmostEqual(r["channel_avg_ctr"], 0.033)
        self.assertAlmostEqual(r["last_check_ctr"], 0.014)

    def test_velocity_scale_never_lands_in_ctr_columns(self):
        """1日あたり再生数(42〜55)やパーセント尺度(39〜46)を弾く。

        ここを素通しすると切替判定 `last_check_ctr < channel_avg_ctr * 0.8` が
        丸ごと壊れ、19件中18件が monitoring のまま滞留する（09-05/09-07 に再発）。
        """
        self.ab._update_row("vid1", {"channel_avg_ctr": 55.17, "last_check_ctr": 42.8})
        r = self._row()
        self.assertIsNone(r["channel_avg_ctr"])
        self.assertIsNone(r["last_check_ctr"])

    def test_metric_agnostic_columns_exist(self):
        self.ab._update_row("vid1", {
            "last_check_metric": "view_velocity",
            "last_check_value": 12.5,
            "baseline_value": 55.17,
        })
        r = self._row()
        self.assertEqual(r["last_check_metric"], "view_velocity")
        self.assertAlmostEqual(r["baseline_value"], 55.17)
        # 代理指標の値は CTR 列へ漏れない（列の既定値 0 のまま）
        self.assertNotAlmostEqual(r["channel_avg_ctr"] or 0.0, 55.17)


# ---------------------------------------------------------------------------
# 3. dup_check の blacklist 除外
# ---------------------------------------------------------------------------
class TestDupCheckBlacklist(unittest.TestCase):
    def test_blacklisted_theme_is_not_reported(self):
        import run_daily_pdca as pdca
        cfg_path = pdca.CHANNELS_DIR / "scp-lab.json"
        blacklist = json.loads(cfg_path.read_text(encoding="utf-8")).get("theme_blacklist") or []
        self.assertIn("SCP-173", blacklist, "前提が変わった: scp-lab の blacklist に SCP-173 が無い")

        videos = [
            {"title": "SCP-173 の正体を追う"},
            {"title": "SCP-173 の正体を追う記録"},
        ]
        self.assertEqual(pdca._dup_check("scp-lab", videos), [])

    def test_non_blacklisted_duplicates_still_reported(self):
        import run_daily_pdca as pdca
        videos = [
            {"title": "収容違反の記録が毎回消える理由"},
            {"title": "収容違反の記録が毎回消える理由とは"},
        ]
        pairs = pdca._dup_check("scp-lab", videos)
        self.assertTrue(pairs, "blacklist 除外が効きすぎて通常の重複まで消えている")


if __name__ == "__main__":
    unittest.main()
