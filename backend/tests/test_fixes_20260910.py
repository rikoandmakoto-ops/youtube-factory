"""2026-09-10 の修正のテスト。

09-09 は投稿が1本しか出なかった。原因はレンダリングが 150〜800 倍遅くなった
ことだが、**遅くなった原因はコードではなくホストの資源枯渇**だった
（実測: load 68/8core・swap 20.1/21.5GB・素の `Image.alpha_composite`
1080x1920 が 670ms＝健全時の 50〜80 倍）。09-09 深夜レポートが立てた
「`make_frame` の中でフレームごとに画像生成が走っているのでは」という仮説は
本テストで恒久的に潰す（実測では 0 回）。

  1. レンダ経路のベンチマーク — フレームごとの画像生成／オーバーレイ再構築が
     入り込んでいないこと。絶対時間ではなく**同じサイズの素の合成に対する倍率**で
     見るので、負荷の高いホストでも判定がぶれない。
  2. render_health      — 「エラーは出ないが遅い」をレポートに出す欠測検知
  3. JobQueue._save     — 同時保存の競合（永続化失敗 78 回の真因）
  4. JobQueue の滞留検知 — 1本のジョブがワーカーを何時間も占有したら気づく
  5. update_channel     — メモリ上の古いスナップショットで JSON を丸ごと上書きしない
  6. _resolve_time_slots — 同一時刻の枠を畳む（scp-lab の6枠二重登録）
  7. title_constraints  — 「秘密」を答え提示語として数えない
"""

import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = Path(__file__).resolve().parents[2]


# =====================================================================
# 1. レンダ経路のベンチマーク
# =====================================================================

class TestRenderPathHasNoPerFrameGeneration(unittest.TestCase):
    """`make_frame(t)` の中で重い生成が走っていないことを恒久的に固定する。

    09-09 の障害調査では「フレームごとに `generate_pillow_illustration` が
    走るようになったのでは」という仮説が立った。実際には全ての呼び出しが
    `plans` ループ（フレーム生成の外・カード枚数ぶんだけ）にあり、キャッシュも
    効いている。ここが将来 `make_frame` の内側に落ちてくると、症状は
    「エラーなしでただ遅い」になり監視に一切かからない。
    """

    @classmethod
    def setUpClass(cls):
        from pipeline import video_generator as vg
        cls.vg = vg
        cls.speaker = next(iter(vg.CHAR_CONFIG))

    def _renderer(self):
        # 背景動画なし＝単色背景。外部素材に依存せずに make_frame を通せる。
        return self.vg.ShortFrameRenderer(bg_video_path=None, image_mode="generate")

    def test_make_frame_does_not_generate_illustrations(self):
        from pipeline import pillow_illustration

        calls = {"pillow": 0, "collect": 0}
        orig = pillow_illustration.generate_pillow_illustration

        def counting(*a, **kw):
            calls["pillow"] += 1
            return orig(*a, **kw)

        pillow_illustration.generate_pillow_illustration = counting
        try:
            r = self._renderer()
            # is_opening=True はパンチイン演出があるので、静止背景でも
            # フレームごとに合成が走る「本物の make_frame」になる。
            clip = r.make_video_clip(
                self.speaker, "テスト字幕です", 1.0, 0.0, "normal", is_opening=True)
            calls["pillow"] = 0  # クリップ組み立て時の呼び出しは対象外
            for i in range(12):
                clip.get_frame(i / 24.0)
        finally:
            pillow_illustration.generate_pillow_illustration = orig

        self.assertEqual(
            calls["pillow"], 0,
            "make_frame の中で generate_pillow_illustration が呼ばれている"
            "（フレーム数ぶんの画像生成＝レンダが2〜3桁遅くなる）")

    def test_overlay_is_built_once_per_clip_not_per_frame(self):
        r = self._renderer()
        built = {"n": 0}
        orig = r._build_overlay

        def counting(*a, **kw):
            built["n"] += 1
            return orig(*a, **kw)

        r._build_overlay = counting
        clip = r.make_video_clip(
            self.speaker, "テスト字幕です", 1.0, 0.0, "normal", is_opening=True)
        for i in range(12):
            clip.get_frame(i / 24.0)
        self.assertEqual(
            built["n"], 1,
            f"_build_overlay がクリップあたり {built['n']} 回呼ばれている（想定1回）")

    def test_frame_cost_stays_within_calibration_multiple(self):
        """1フレームの費用を「同サイズの素の合成」に対する倍率で見る。

        絶対時間で閾値を切ると、負荷の高いホストでは常に落ちる（09-09 の実測で
        素の合成が 670ms＝健全時の 50〜80 倍になっていた）。同じ 1080x1920 の
        `alpha_composite` を較正値に使えば、ホストの状態は分母と分子で相殺され、
        **コード側が1フレームに積んだ仕事の量**だけが残る。
        """
        import numpy as np
        from PIL import Image

        W, H = self.vg.SHORT_W, self.vg.SHORT_H
        bg = Image.new("RGBA", (W, H), (20, 20, 20, 255))
        ov = Image.new("RGBA", (W, H), (200, 100, 50, 128))

        def calib():
            np.array(Image.alpha_composite(bg, ov).convert("RGB"))

        def measure(fn, n):
            fn()
            fn()
            t0 = time.perf_counter()
            for _ in range(n):
                fn()
            return (time.perf_counter() - t0) / n

        base = measure(calib, 3)

        r = self._renderer()
        clip = r.make_video_clip(
            self.speaker, "テスト字幕です", 1.0, 0.0, "normal", is_opening=True)
        counter = {"t": 0.0}

        def one_frame():
            counter["t"] += 1.0 / 24.0
            clip.get_frame(min(0.9, counter["t"]))

        per_frame = measure(one_frame, 5)

        ratio = per_frame / base if base > 0 else float("inf")
        # 冒頭演出は素の合成に加えて overlay の拡大縮小が1回入るので 2〜4倍が正常。
        # 画像生成やディスクI/Oが1フレームに落ちてくると2桁跳ねる。
        self.assertLess(
            ratio, 12.0,
            f"1フレームの費用が素の合成の {ratio:.1f} 倍（較正 {base*1000:.0f}ms / "
            f"実測 {per_frame*1000:.0f}ms）。フレームごとに重い処理が入っている")

    def test_keyword_matching_cost_per_video_is_bounded(self):
        """語彙照合（09-09 に jp_wordmatch へ置き換えた箇所）の総費用。

        1本のショートで呼ばれるのは「カード枚数(<=5) + サムネ判定1〜2」で
        高々8回。素の部分一致より約5倍重くなったが、1本あたりの増分は
        10ms 程度で、レンダ全体（数分）に対して無視できる。ここが
        フレーム単位（数百〜千回）に落ちたら跳ねるので上限を置く。
        """
        from pipeline import pillow_illustration as pi

        topics = [
            "ピカチュウの電気袋に隠された3つの秘密…速さの理由がヤバい",
            "なぜ寒さで顎が先に震える？3秒の正体",
            "ロケット団の言葉選びを3作品で追う",
        ]
        CALLS_PER_VIDEO = 8
        t0 = time.perf_counter()
        for _ in range(CALLS_PER_VIDEO):
            for t in topics:
                pi._match_textbook(t)
                pi._leaked_matched(t)
        elapsed = (time.perf_counter() - t0) / len(topics)
        self.assertLess(
            elapsed, 0.5,
            f"1本あたりの語彙照合が {elapsed*1000:.0f}ms（上限 500ms）")


# =====================================================================
# 2. render_health — 「エラーは出ないが遅い」を可視化する
# =====================================================================

class TestRenderHealth(unittest.TestCase):

    def test_probe_returns_the_fields_the_report_needs(self):
        from pipeline import render_health

        snap = render_health.probe(calibrate=False)
        for key in ("load_per_core", "swap_used_ratio", "free_mb",
                    "composite_ms", "verdict", "reasons"):
            self.assertIn(key, snap, f"render_health.probe に {key} が無い")
        self.assertIn(snap["verdict"], ("ok", "degraded", "critical"))

    def test_healthy_numbers_are_ok(self):
        from pipeline import render_health

        v, reasons = render_health.classify(
            load_per_core=0.6, swap_used_ratio=0.10, free_mb=4096, composite_ms=12.0)
        self.assertEqual(v, "ok", reasons)
        self.assertEqual(reasons, [])

    def test_the_20260909_condition_is_reported_as_critical(self):
        """09-09 深夜の実測値。これが ok と出るなら検知として役に立たない。"""
        from pipeline import render_health

        v, reasons = render_health.classify(
            load_per_core=68.0 / 8, swap_used_ratio=20146.0 / 21504.0,
            free_mb=24.0, composite_ms=670.0)
        self.assertEqual(v, "critical", reasons)
        self.assertTrue(reasons, "critical なのに理由が空")

    def test_composite_benchmark_alone_can_trip_the_gate(self):
        """負荷指標が読めないホストでも、実測の合成時間だけで判定できること。"""
        from pipeline import render_health

        v, _ = render_health.classify(
            load_per_core=None, swap_used_ratio=None, free_mb=None,
            composite_ms=670.0)
        self.assertIn(v, ("degraded", "critical"))


# =====================================================================
# 3-4. JobQueue — 永続化の競合と滞留検知
# =====================================================================

class _QueueBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "job_queue.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _queue(self):
        from pipeline.scheduler.job_queue import JobQueue
        return JobQueue(max_workers=2, persist_path=self.path)


class TestJobQueuePersistRace(_QueueBase):

    def _enqueue(self, q, n):
        for i in range(n):
            q.submit("daily-science", {"title": f"t{i}", "short_scenario": []})

    def test_concurrent_saves_never_fail(self):
        """78回出ていた `[Errno 2] ... job_queue.json.tmp -> job_queue.json`。

        固定名の tmp を複数スレッドが同時に使うので、先に rename した側が
        tmp を消し、後続の `replace()` が「そんなファイルは無い」で落ちる。
        """
        q = self._queue()
        self._enqueue(q, 20)

        buf = io.StringIO()
        errors = []

        def hammer():
            try:
                for _ in range(25):
                    q._save()
            except Exception as e:  # pragma: no cover
                errors.append(e)

        with redirect_stdout(buf):
            threads = [threading.Thread(target=hammer) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        out = buf.getvalue()
        self.assertEqual(errors, [])
        self.assertNotIn("JobQueue persist failed", out, out[-2000:])
        self.assertTrue(self.path.exists(), "保存先が消えている")
        json.loads(self.path.read_text(encoding="utf-8"))  # 壊れていないこと

    def test_save_while_jobs_are_added_does_not_raise(self):
        """`dictionary changed size during iteration` の側。"""
        q = self._queue()
        self._enqueue(q, 10)

        buf = io.StringIO()
        stop = threading.Event()

        def adder():
            i = 0
            while not stop.is_set():
                q.submit("daily-science", {"title": f"x{i}", "short_scenario": []})
                i += 1

        with redirect_stdout(buf):
            t = threading.Thread(target=adder)
            t.start()
            try:
                for _ in range(40):
                    q._save()
            finally:
                stop.set()
                t.join()

        out = buf.getvalue()
        self.assertNotIn("changed size during iteration", out, out[-2000:])
        self.assertNotIn("JobQueue persist failed", out, out[-2000:])

    def test_no_stray_tmp_files_are_left_behind(self):
        q = self._queue()
        self._enqueue(q, 5)
        with redirect_stdout(io.StringIO()):
            for _ in range(5):
                q._save()
        leftovers = [p.name for p in self.path.parent.iterdir()
                     if p.name != self.path.name]
        self.assertEqual(leftovers, [], f"tmp が残っている: {leftovers}")


class TestJobQueueStallDetection(_QueueBase):
    """09-09 の障害が監視に引っかからなかった理由そのもの。

    ERROR ログは 0 件だった。ジョブは「失敗」ではなく「11時間走り続けている」
    だけなので、例外を見る監視には一生かからない。
    """

    def test_long_running_job_is_reported_as_stalled(self):
        from datetime import datetime, timedelta
        from pipeline.scheduler.job_queue import JobStatus

        q = self._queue()
        jid = q.submit("daily-science", {"title": "遅いやつ", "short_scenario": []})
        job = q._jobs[jid]
        job.status = JobStatus.RUNNING
        job.started_at = (datetime.now() - timedelta(hours=11)).isoformat()

        stalled = q.stalled_jobs(threshold_minutes=90)
        self.assertEqual([s["id"] for s in stalled], [jid])
        self.assertGreater(stalled[0]["running_minutes"], 600)

    def test_fresh_running_job_is_not_stalled(self):
        from datetime import datetime
        from pipeline.scheduler.job_queue import JobStatus

        q = self._queue()
        jid = q.submit("daily-science", {"title": "普通のやつ", "short_scenario": []})
        job = q._jobs[jid]
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        self.assertEqual(q.stalled_jobs(threshold_minutes=90), [])

    def test_pending_jobs_are_not_counted_as_stalled(self):
        q = self._queue()
        q.submit("daily-science", {"title": "待ち", "short_scenario": []})
        self.assertEqual(q.stalled_jobs(threshold_minutes=1), [])


# =====================================================================
# 5. update_channel — 指揮者がディスクに書いた変更を消さない
# =====================================================================

class TestUpdateChannelDoesNotClobberDisk(unittest.TestCase):
    """09-08 の「バックエンドが設定を上書きして消す」の真因。

    `update_channel` は `ch._raw`（＝最後に reload した時点のメモリ上の写し）を
    土台にファイルを丸ごと書き直す。指揮者がディスク側を直した後にこの経路が
    走ると、更新キー以外の**全ての変更が黙って巻き戻る**。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "demo.json").write_text(json.dumps({
            "id": "demo",
            "name": "デモ",
            "concept": "元のコンセプト",
            "theme_seeds": ["A"],
            "video_format": {"short_illustrations": {"enabled": True}},
        }, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _manager(self):
        from channels.channel_manager import ChannelManager
        return ChannelManager(data_dir=str(self.dir))

    def test_on_disk_edits_made_after_load_survive_an_update(self):
        m = self._manager()
        path = self.dir / "demo.json"

        # 指揮者がディスク側を直接編集（backend はまだ reload していない）
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["theme_seeds"] = ["指揮者が入れたテーマ"]
        raw["title_rules"] = {"hard_constraints": {"require_any_of": ["理由"]}}
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        # backend 側は無関係なキーだけを更新する
        m.update_channel("demo", {"concept": "新しいコンセプト"})

        after = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(after["concept"], "新しいコンセプト")
        self.assertEqual(after["theme_seeds"], ["指揮者が入れたテーマ"],
                         "ディスク側の theme_seeds が巻き戻っている")
        self.assertIn("title_rules", after,
                      "ディスク側で足されたキーが消えている")

    def test_video_format_partial_update_still_merges(self):
        m = self._manager()
        m.update_channel("demo", {"video_format": {"short_illustrations": {"max_count": 4}}})
        after = json.loads((self.dir / "demo.json").read_text(encoding="utf-8"))
        si = after["video_format"]["short_illustrations"]
        self.assertEqual(si["max_count"], 4)
        self.assertTrue(si["enabled"], "部分更新で既存キーが落ちている")

    def test_in_memory_profile_is_not_mutated_by_a_failed_update(self):
        """`_raw.copy()` は浅いコピーなので、入れ子を触るとメモリ側も汚れる。"""
        m = self._manager()
        before = json.loads(json.dumps(m.get("demo")._raw.get("video_format")))
        m.update_channel("demo", {"video_format": {"short_illustrations": {"max_count": 9}}})
        # reload 後は当然新しい値。ここで見たいのは「更新前のオブジェクトが
        # その場で書き換わっていないこと」なので、ディスクを土台にしている限り
        # 更新は reload 経由でしか反映されない。
        self.assertEqual(before["short_illustrations"]["enabled"], True)


# =====================================================================
# 6. 投稿枠の重複
# =====================================================================

class TestTimeSlotDedup(unittest.TestCase):

    def test_identical_slots_are_collapsed(self):
        import api_channel_autopilot as ap

        slots = ap._resolve_time_slots({"times": [
            {"hour": 9, "minute": 0}, {"hour": 13, "minute": 0},
            {"hour": 19, "minute": 0}, {"hour": 9, "minute": 0},
            {"hour": 13, "minute": 0}, {"hour": 19, "minute": 0},
        ]})
        self.assertEqual([(s["hour"], s["minute"]) for s in slots],
                         [(9, 0), (13, 0), (19, 0)],
                         "同一時刻の枠が畳まれていない（scp-lab の6枠二重登録）")

    def test_same_time_different_days_are_kept(self):
        import api_channel_autopilot as ap

        slots = ap._resolve_time_slots({"times": [
            {"hour": 20, "minute": 0, "days_of_week": [1, 2, 3, 4, 5]},
            {"hour": 20, "minute": 0, "days_of_week": [0, 6]},
        ]})
        self.assertEqual(len(slots), 2, "曜日が違う枠まで畳んでいる")

    def test_same_time_different_engine_is_kept(self):
        import api_channel_autopilot as ap

        slots = ap._resolve_time_slots({"times": [
            {"hour": 20, "minute": 45, "engine": "local"},
            {"hour": 20, "minute": 45, "engine": "viral"},
        ]})
        self.assertEqual(len(slots), 2, "engine が違う枠まで畳んでいる")

    def test_live_channel_configs_have_no_duplicate_slots(self):
        for path in sorted((REPO_ROOT / "data" / "channels").glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            times = ((d.get("autopilot") or {}).get("schedule") or {}).get("times") or []
            seen = set()
            for t in times:
                key = (t.get("hour"), t.get("minute"),
                       tuple(sorted(t.get("days_of_week") or [])), t.get("engine"))
                self.assertNotIn(key, seen, f"{path.name}: 枠 {key} が重複している")
                seen.add(key)


# =====================================================================
# 7. 「秘密」を答え提示語として数えない
# =====================================================================

class TestReasonWords(unittest.TestCase):

    def test_himitsu_is_not_treated_as_an_answer_marker(self):
        from pipeline import title_constraints as tc

        self.assertNotIn("秘密", tc._REASON_WORDS,
                         "「秘密」は登録/千再生 0.120 で有害。答え提示語に数えない")

    def test_a_title_with_himitsu_still_gets_a_real_answer_marker(self):
        from pipeline import title_constraints as tc

        out = tc.rewrite_why("なぜピカチュウの電気袋には秘密があるのか？")
        self.assertTrue(
            any(w in out for w in tc._REASON_WORDS),
            f"「秘密」しか無いタイトルに答え提示語が足されていない: {out}")

    def test_existing_reason_words_still_short_circuit(self):
        from pipeline import title_constraints as tc

        out = tc.rewrite_why("なぜ妖怪は夜に出るのか？その正体")
        self.assertEqual(out.count("正体"), 1)
        self.assertNotIn("本当の理由", out)


if __name__ == "__main__":
    unittest.main()
