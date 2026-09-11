"""2026-09-12「そもそもエラーを起きないようにしろ」の根本対策のテスト。

09-11 の PDCA レポートに出た 5 件は、いずれも「1箇所を直せば終わり」ではなく
**構造**の問題だった。パッチではなく構造で潰したことをここで固定する。

  1. title_gate     — タイトル衛生の検査を1箇所に集め、全経路（生成の出口 /
                      ジョブ投入 / レンダ / YouTube・TikTok 投稿）が必ず通る
  2. theme_seeds    — 読み込み時に形を正規化する（設定の書き方で機能が死なない）
                      ＋ 硬い却下（blacklist / genre_blacklist）は代替が無ければ止める
  3. cross_channel  — テーマ段は題材語だけを見る（型語でキュー全件ブロックしない）
                      ＋ 全滅時は「先頭」ではなく最も混んでいない候補
  4. theme_dedup    — 型語を lexicon に一本化 ＋ 比較対象からの自動抽出（文書頻度）
  5. channel JSON   — 書き込みはディスクを土台に1関数へ集約（外部編集を消さない）
                      ＋ get() が外部編集を検知して読み直す
  6. gate_failures  — ゲートの例外は握り潰さず result に記録される
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import title_gate as tg  # noqa: E402
from pipeline import title_lexicon as lex  # noqa: E402
from pipeline.auto_scenario import cross_channel_gate as ccg  # noqa: E402
from pipeline.auto_scenario import theme_dedup as td  # noqa: E402


def _write_channel(dir_: Path, cid: str, **extra) -> Path:
    raw = {"id": cid, "name": cid, "concept": "test", "style": "yukkuri",
           "theme_seeds": [{"title": "河童の皿はなぜ乾くと死ぬのか", "angle": ""},
                           {"title": "天狗の鼻が長い理由", "angle": ""}],
           "video_format": {"resolution": {"short_width": 1080, "short_height": 1920}}}
    raw.update(extra)
    p = dir_ / f"{cid}.json"
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# =====================================================================
# 1. title_gate — 1箇所の検査を全経路が通る
# =====================================================================

class TitleGateSanitizeTest(unittest.TestCase):
    """job 1a6e3105 の『…仕組み、】【の実態』が二度と外に出ないこと。"""

    def test_reversed_bracket_fragment(self):
        got = tg.sanitize("個人向け国債、年0.05%でも元本割れしにくい仕組み、】【の実態")
        self.assertNotIn("】", got)
        self.assertNotIn("【", got)
        self.assertEqual(got, "個人向け国債、年0.05%でも元本割れしにくい仕組みの実態")

    def test_unclosed_and_unopened_brackets(self):
        self.assertEqual(tg.sanitize("SCP-682が適応する本当の理由】"), "SCP-682が適応する本当の理由")
        self.assertEqual(tg.sanitize("なぜ財団は記録を消す【のか"), "なぜ財団は記録を消すのか")
        self.assertEqual(tg.sanitize("仕組み、【ショート】"), "仕組み【ショート】")

    def test_legit_titles_unchanged(self):
        for t in ("なぜ寝言は自分では一度も聞けないのか",
                  "【ショート】なぜ寝言は聞けないのか",
                  "「残業代はやる気で払う」上司の末路",
                  "1分ポケモン研究 #21：カビゴンが寝る理由",
                  "テスト（括弧）付きのタイトルです"):
            self.assertEqual(tg.sanitize(t), t)

    def test_llm_artifacts_are_stripped(self):
        self.assertEqual(tg.sanitize("タイトル: 猫が箱に入る本当の理由"), "猫が箱に入る本当の理由")
        self.assertEqual(tg.sanitize("1. 猫が箱に入る本当の理由"), "猫が箱に入る本当の理由")
        self.assertEqual(tg.sanitize("**猫が箱に入る本当の理由**"), "猫が箱に入る本当の理由")
        self.assertEqual(tg.sanitize("「猫が箱に入る本当の理由」"), "猫が箱に入る本当の理由")
        self.assertEqual(tg.sanitize("猫が箱に入る本当の理由\n\n説明: これは…"), "猫が箱に入る本当の理由")

    def test_double_short_marker_and_control_chars(self):
        self.assertEqual(tg.sanitize("なぜ〜なのか【ショート】【ショート】"), "なぜ〜なのか【ショート】")
        self.assertEqual(tg.sanitize("a<b>c 制御\x07文字"), "abc 制御文字")

    def test_garbage_returns_empty_or_none(self):
        for t in ("】【", "", None, "   "):
            self.assertEqual(tg.sanitize(t), "", repr(t))
            self.assertIsNone(tg.llm_title(t), repr(t))
        self.assertIsNone(tg.llm_title("なぜ猫は【"))  # 掃除後4字 → 使わない

    def test_validate_lists_every_problem(self):
        probs = tg.validate("仕組み、】【の実態、")
        self.assertTrue(any("括弧" in p for p in probs), probs)
        self.assertTrue(any("末尾" in p for p in probs), probs)
        self.assertEqual(tg.validate("x" * 101), ["長すぎ(101字>100)"])
        self.assertEqual(tg.validate("なぜ寝言は自分では一度も聞けないのか"), [])

    def test_validate_includes_channel_constraints(self):
        ch = {"title_rules": {"hard_constraints": {"forbid_digits": True}}}
        probs = tg.validate("妖怪ファイル #12 の話", ch)
        self.assertTrue(any(p.startswith("規約") for p in probs), probs)

    def test_finalize_falls_back_then_raises(self):
        self.assertEqual(tg.finalize("】【", fallback="猫が箱に入る本当の理由"), "猫が箱に入る本当の理由")
        with self.assertRaises(tg.TitleGateError):
            tg.finalize("】【", fallback="】")
        # 短いだけの題名（手動ジョブ）は壊れていないので通す
        self.assertEqual(tg.finalize("SCP-173"), "SCP-173")

    def test_finalize_trims_to_youtube_limit(self):
        long = "あ" * 60 + "、" + "い" * 60
        out = tg.finalize(long)
        self.assertLessEqual(len(out), tg.YOUTUBE_TITLE_MAX)
        self.assertEqual(out, "あ" * 60)

    def test_trim_keeps_complete_hashtag_drops_partial(self):
        base = "あ" * 88
        self.assertEqual(tg.trim_to(base + " #shorts #SCP解説", 96), base + " #shorts")
        self.assertEqual(tg.trim_to(base + " #shorts", 92), base)

    def test_for_upload_raises_on_empty(self):
        with self.assertRaises(tg.TitleGateError):
            tg.for_upload("】【")
        out = tg.for_upload("x" * 150)
        self.assertLessEqual(len(out), tg.YOUTUBE_TITLE_MAX)
        self.assertTrue(out.endswith("…"))

    def test_safe_dirname(self):
        self.assertEqual(tg.safe_dirname("SCP-3999【世界が/一人の:研究員】"),
                         "SCP-3999【世界が一人の研究員】")
        self.assertEqual(tg.safe_dirname("】【"), "untitled")
        self.assertLessEqual(len(tg.safe_dirname("あ" * 300)), tg.DIRNAME_MAX_CHARS)


class TitleGateIsWiredEverywhereTest(unittest.TestCase):
    """全経路が title_gate を通ること。1つでも抜けると mp4 まで貫通する。"""

    def test_generator_regen_helpers_use_gate(self):
        import inspect
        from pipeline.auto_scenario import generator as gen
        src = inspect.getsource(gen)
        for helper in ("_regenerate_title", "_regenerate_title_for_ctr",
                       "_regenerate_title_with_bans"):
            body = inspect.getsource(getattr(gen.ScenarioGenerator, helper))
            self.assertIn("_sanitize_regenerated_title", body, helper)
        self.assertIn("_tg.llm_title", inspect.getsource(gen._sanitize_regenerated_title))
        # generate() の出口
        self.assertIn("self._finalize_title(channel, theme, result)",
                      inspect.getsource(gen.ScenarioGenerator.generate))

    def test_generator_finalize_cleans_result(self):
        from pipeline.auto_scenario.generator import ScenarioGenerator
        g = ScenarioGenerator.__new__(ScenarioGenerator)
        ch = mock.Mock(); ch._raw = {}
        res = {"title": "個人向け国債、年0.05%でも元本割れしにくい仕組み、】【の実態"}
        g._finalize_title(ch, {"title": "個人向け国債の仕組み"}, res)
        self.assertEqual(res["title"], "個人向け国債、年0.05%でも元本割れしにくい仕組みの実態")
        self.assertTrue(res["title_gate"]["cleaned"])
        self.assertEqual(res["original_title"], "個人向け国債、年0.05%でも元本割れしにくい仕組み、】【の実態")
        # 壊れ切っていればテーマ題名へ
        res = {"title": "】【"}
        g._finalize_title(ch, {"title": "個人向け国債の仕組み"}, res)
        self.assertEqual(res["title"], "個人向け国債の仕組み")

    def test_job_queue_submit_cleans_title(self):
        from pipeline.scheduler import job_queue as jq
        q = jq.JobQueue.__new__(jq.JobQueue)
        q._jobs = {}
        q._lock = __import__("threading").Lock()
        q._queue = __import__("queue").PriorityQueue()
        q._save = lambda: None
        sd = {"title": "仕組み、】【の実態", "style": "yukkuri"}
        job_id = q.submit("scp-lab", sd)
        self.assertEqual(q._jobs[job_id].title, "仕組みの実態")
        self.assertEqual(sd["title"], "仕組みの実態")
        with self.assertRaises(ValueError):
            q.submit("scp-lab", {"title": "】【"})

    def test_video_generator_dirname_and_sanitize(self):
        from pipeline import video_generator as vg
        self.assertEqual(vg.output_dirname("仕組み、】【の実態/x"), "仕組みの実態x")
        src = __import__("inspect").getsource(vg.generate_all)
        self.assertIn("_tg.sanitize(title)", src)
        self.assertIn("output_dirname(title)", src)

    def test_uploaders_call_for_upload(self):
        import inspect
        from pipeline import youtube_uploader, tiktok_uploader
        self.assertIn("_tg.for_upload(title)", inspect.getsource(youtube_uploader.upload_video))
        self.assertIn("_tg.for_upload(title)", inspect.getsource(tiktok_uploader.upload_video))

    def test_clip_sources_use_same_dirname(self):
        from pipeline.clip_factory import sources
        from pipeline import video_generator as vg
        t = "SCP-3999【世界が/一人の:研究員】"
        self.assertEqual(sources._dirname_for(t), vg.output_dirname(t))


# =====================================================================
# 2. theme_seeds の正規化 ＋ 硬い却下は止める
# =====================================================================

class ThemeSeedNormalizationTest(unittest.TestCase):
    def test_strings_become_dicts_at_load(self):
        from channels.channel_manager import ChannelManager, normalize_theme_seeds
        self.assertEqual(normalize_theme_seeds(["a", {"title": "b"}, "", 3, {"title": ""}]),
                         [{"title": "a", "angle": ""}, {"title": "b", "angle": ""}])
        self.assertEqual(normalize_theme_seeds("not a list"), [])
        with tempfile.TemporaryDirectory() as d:
            _write_channel(Path(d), "t-str", theme_seeds=["素の文字列", {"title": "dict形式"}])
            cm = ChannelManager(d)
            seeds = cm.get("t-str").theme_seeds
            self.assertTrue(all(isinstance(s, dict) and s.get("title") for s in seeds))
            self.assertEqual([s["title"] for s in seeds], ["素の文字列", "dict形式"])
            codes = [i.code for i in cm.config_issues()]
            self.assertIn("theme_seeds_shape", codes, "設定側を直す合図が出ていない")

    def test_seed_pick_survives_string_seeds(self):
        """以前 'str' object has no attribute 'get' で落ちていた経路。"""
        from channels.channel_manager import ChannelManager
        from pipeline.auto_scenario.generator import ScenarioGenerator
        with tempfile.TemporaryDirectory() as d:
            _write_channel(Path(d), "t-pick", theme_seeds=["河童の皿", "天狗の鼻"])
            ch = ChannelManager(d).get("t-pick")
            g = ScenarioGenerator.__new__(ScenarioGenerator)
            with mock.patch.object(ScenarioGenerator, "_collect_past_themes", return_value=[]):
                picked = g._pick_seed_avoiding_past(ch)
            self.assertIn(picked["title"], ("河童の皿", "天狗の鼻"))
            titles = ScenarioGenerator.suggest_themes  # 存在確認だけ（LLM は呼ばない）
            self.assertTrue(callable(titles))


class HardRejectStopsGenerationTest(unittest.TestCase):
    """genre_blacklist / theme_blacklist に当たったテーマは、代替が無くても採用しない。"""

    def _gen(self, suggest_raises=True):
        from pipeline.auto_scenario.generator import ScenarioGenerator
        g = ScenarioGenerator.__new__(ScenarioGenerator)
        g._existing_titles_for_dedup = lambda cid: ["河童の皿はなぜ乾くと死ぬのか"]
        g._collect_past_themes = lambda cid, limit=50: []
        if suggest_raises:
            def _boom(*a, **k):
                raise AttributeError("'str' object has no attribute 'get'")
            g.suggest_themes = _boom
        else:
            g.suggest_themes = lambda *a, **k: []
        return g

    def test_genre_blacklist_hit_without_alternative_raises(self):
        from pipeline.auto_scenario.generator import ThemeRejectedError
        g = self._gen()
        ch = mock.Mock(); ch.id = "scp-lab"
        ch._raw = {"theme_blacklist": ["財団職員"]}
        ch.theme_seeds = [{"title": "財団職員の一日"}]  # seed も全部当たる
        with self.assertRaises(ThemeRejectedError) as cm:
            g._dedupe_theme(ch, {"title": "財団職員の一日"})
        self.assertIn("suggest_themes", str(cm.exception), "代替探索の失敗理由が消えている")

    def test_hard_reject_uses_alternative_when_available(self):
        g = self._gen()
        ch = mock.Mock(); ch.id = "scp-lab"
        ch._raw = {"theme_blacklist": ["財団職員"]}
        ch.theme_seeds = [{"title": "SCP-096 の顔を見た者"}]
        out = g._dedupe_theme(ch, {"title": "財団職員の一日"})
        self.assertEqual(out["title"], "SCP-096 の顔を見た者")
        self.assertEqual(out["theme_gate"]["replaced"], "財団職員の一日")

    def test_soft_duplicate_keeps_original_but_records(self):
        g = self._gen()
        ch = mock.Mock(); ch.id = "yokai-watch"
        ch._raw = {}
        ch.theme_seeds = [{"title": "河童の皿はなぜ乾くと死ぬのか"}]
        out = g._dedupe_theme(ch, {"title": "河童の皿はなぜ乾くと死ぬのか"})
        self.assertEqual(out["title"], "河童の皿はなぜ乾くと死ぬのか")
        self.assertIn("kept_despite", out["theme_gate"])
        self.assertTrue(out["theme_gate"]["errors"], "suggest_themes の失敗が記録されていない")


# =====================================================================
# 3. 横断ゲート — テーマ段は題材語だけ／全滅時は最も混んでいない候補
# =====================================================================

class CrossChannelTopicOnlyTest(unittest.TestCase):
    def setUp(self):
        self._orig = ccg._STATE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        ccg._STATE_PATH = Path(self._tmp.name) / "cross.json"

    def tearDown(self):
        ccg._STATE_PATH = self._orig
        self._tmp.cleanup()

    def test_answer_markers_come_from_lexicon(self):
        self.assertEqual(ccg.ANSWER_MARKER_KEYWORDS, set(lex.ANSWER_MARKERS))
        self.assertIn("なぜ", ccg.ANSWER_MARKER_KEYWORDS)

    def test_topic_only_never_blocks_on_format_word(self):
        chans = ["a", "b", "c", "d", "e", "f", "g", "h"]
        topics = ["河童", "天狗", "雪女", "座敷童子", "牛鬼", "ろくろ首", "鵺", "件"]
        for c, t in zip(chans, topics):
            ccg.reserve(c, f"なぜ{t}は人を襲うのか", key=f"{c}::{t}")
        # 型語だけ見れば「なぜ」は上限超え
        self.assertIsNotNone(ccg.blocking_keyword("z", "なぜ河童は緑なのか"))
        self.assertEqual(ccg.blocking_keyword("z", "なぜ鬼は角があるのか")[0], "なぜ")
        # テーマ段（題材語だけ）では通る
        self.assertIsNone(ccg.blocking_keyword("z", "なぜ鬼は角があるのか", topic_only=True))
        # 題材語が本当に混んでいればテーマ段でも止まる
        ccg.reserve("y", "河童の皿の秘密", key="y::河童")
        hit = ccg.blocking_keyword("z", "なぜ河童は緑なのか", topic_only=True)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], "河童")

    def test_extract_keywords_topic_only(self):
        self.assertNotIn("なぜ", ccg.extract_keywords("なぜ河童は緑なのか", topic_only=True))
        self.assertIn("なぜ", ccg.extract_keywords("なぜ河童は緑なのか"))
        self.assertTrue(ccg.is_answer_marker("正体"))
        self.assertFalse(ccg.is_answer_marker("河童"))


class AutopilotQueueNeverFullyBlockedTest(unittest.TestCase):
    """全候補が「なぜ型」でもキューは前から順に消費される。"""

    def setUp(self):
        import api_channel_autopilot as ap
        from channels.channel_manager import ChannelManager
        self.ap = ap
        self._orig_state = ccg._STATE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        ccg._STATE_PATH = Path(self._tmp.name) / "cross.json"
        self.cdir = Path(self._tmp.name) / "channels"
        self.cdir.mkdir()
        queue = [{"id": f"t{i}", "title": t, "angle": ""} for i, t in enumerate([
            "なぜ河童は皿が乾くと死ぬのか", "なぜ天狗は鼻が長いのか", "なぜ雪女は溶けないのか"])]
        _write_channel(self.cdir, "t-yokai", autopilot={"enabled": True, "theme_queue": queue})
        self.cm = ChannelManager(str(self.cdir))
        self._orig_cm = ap._state.get("channel_manager")
        self._orig_sg = ap._state.get("scenario_generator")
        ap._state["channel_manager"] = self.cm
        ap._state["scenario_generator"] = None
        self._orig_refresh = ap._refresh_channel_job
        ap._refresh_channel_job = lambda cid: None

    def tearDown(self):
        ccg._STATE_PATH = self._orig_state
        self.ap._state["channel_manager"] = self._orig_cm
        self.ap._state["scenario_generator"] = self._orig_sg
        self.ap._refresh_channel_job = self._orig_refresh
        self._tmp.cleanup()

    def test_why_type_queue_is_consumed_in_order(self):
        # 他 ch が「なぜ」を上限いっぱいまで使っている状態
        for i in range(ccg.ANSWER_MARKER_DAILY_LIMIT + 2):
            ccg.reserve(f"other{i}", f"なぜ題材{i}は動くのか", key=f"o{i}")
        got = self.ap._pop_or_refill_theme("t-yokai")
        self.assertEqual(got["title"], "なぜ河童は皿が乾くと死ぬのか", "型語でブロックされている")
        rest = [t["title"] for t in self.ap._load_autopilot("t-yokai")["theme_queue"]]
        self.assertEqual(rest, ["なぜ天狗は鼻が長いのか", "なぜ雪女は溶けないのか"])

    def test_all_topic_blocked_picks_least_contended(self):
        # 河童 3本 / 天狗 2本 / 雪女 2本 → 全部題材語で止まる → 一番空いている天狗か雪女
        for i in range(3):
            ccg.reserve(f"k{i}", "河童の話", key=f"k{i}")
        for i in range(2):
            ccg.reserve(f"t{i}", "天狗の話", key=f"t{i}")
            ccg.reserve(f"y{i}", "雪女の話", key=f"y{i}")
        got = self.ap._pop_or_refill_theme("t-yokai")
        self.assertIn(got["title"], ("なぜ天狗は鼻が長いのか", "なぜ雪女は溶けないのか"))
        # 保留した候補は捨てられていない
        rest = [t["title"] for t in self.ap._load_autopilot("t-yokai")["theme_queue"]]
        self.assertEqual(len(rest), 2)
        self.assertIn("なぜ河童は皿が乾くと死ぬのか", rest)


# =====================================================================
# 4. theme_dedup — 型語が判定の主語にならない
# =====================================================================

class DedupIgnoresFormatWordsTest(unittest.TestCase):
    def test_reported_format_words_do_not_create_duplicates(self):
        pairs = [
            ("ろくろ首の正体が怖すぎる", "じんめん犬の正体が怖すぎる"),
            ("なぜ猫だけが箱に入るのか", "なぜ犬だけが穴を掘るのか"),
            ("隠された秘密：ミュウツーの本当の理由", "隠された秘密：イーブイの本当の理由"),
            ("【ショート】カビゴンが寝る理由 元ネタ", "【ショート】ピカチュウが光る理由 元ネタ"),
        ]
        for a, b in pairs:
            self.assertLess(td.similarity(a, b), td.DEFAULT_LEXICAL_THRESHOLD, (a, b))

    def test_real_duplicates_still_caught(self):
        self.assertGreaterEqual(
            td.similarity("録音した自分の声が変に聞こえる理由",
                          "自分の声を録音すると別人に聞こえるのはなぜ"), 0.8)
        self.assertEqual(td.similarity("SCP-173 の正体", "なぜ SCP-173 は動くのか"), 1.0)

    def test_lexicon_is_single_source(self):
        self.assertEqual(td._FILLER_WORDS, list(lex.FORMAT_PHRASES))
        for w in ("なぜ", "だけ", "本当の理由", "隠された秘密", "ショート", "元ネタ"):
            self.assertIn(w, lex.FORMAT_PHRASES, w)
        # 長い語が先（replace の順序）
        self.assertLess(lex.FORMAT_PHRASES.index("本当の理由"), lex.FORMAT_PHRASES.index("理由"))

    def test_corpus_stopwords_detects_new_format_word(self):
        """リストに無い新しい型語（例:「末路」）は比較対象の頻度から自動で落ちる。"""
        ex = ["河童の末路が悲惨", "天狗の末路が悲惨", "雪女の末路", "座敷童子の末路が悲惨",
              "牛鬼の末路", "鬼の角が目印になった千年前の変化"]
        stop = td.corpus_stopwords(ex)
        self.assertIn("末路", stop)
        self.assertIn("悲惨", stop)
        self.assertIsNone(td.find_lexical_duplicate("ろくろ首の末路が悲惨", ex))
        # 同じ題材は今も捕まる
        self.assertIsNotNone(td.find_lexical_duplicate("河童の末路", ex))

    def test_corpus_stopwords_needs_enough_docs(self):
        self.assertEqual(td.corpus_stopwords(["河童の末路", "天狗の末路"]), set())

    def test_channel_format_words_from_config(self):
        ch = {"title_rules": {"hard_constraints": {
            "require_any_of": {"words": ["理由", "正体"]}, "forbid_prefixes": ["なぜ"]}}}
        self.assertEqual(lex.channel_format_words(ch), {"理由", "正体", "なぜ"})


# =====================================================================
# 5. channel JSON — 外部編集を消さない
# =====================================================================

class ChannelFilePersistenceTest(unittest.TestCase):
    def setUp(self):
        from channels.channel_manager import ChannelManager
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        _write_channel(self.dir, "t-cfg", genre_blacklist=[], autopilot={"theme_queue": []})
        self.cm = ChannelManager(str(self.dir))

    def tearDown(self):
        self._tmp.cleanup()

    def _external_edit(self, **fields):
        """指揮者が別プロセスからファイルを直す動きを再現する。"""
        p = self.dir / "t-cfg.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw.update(fields)
        p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        # mtime が同一秒に収まっても検知できるよう ns を確実に進める
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    def test_autopilot_save_keeps_external_edits(self):
        self._external_edit(genre_blacklist=["宇宙・天体"], theme_blacklist=["SCP-173"])
        # autopilot セクションだけを保存（メモリはまだ古い）
        self.cm.set_section("t-cfg", "autopilot", {"theme_queue": [{"title": "x"}]})
        raw = json.loads((self.dir / "t-cfg.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["genre_blacklist"], ["宇宙・天体"], "外部編集が巻き戻った")
        self.assertEqual(raw["theme_blacklist"], ["SCP-173"])
        self.assertEqual(raw["autopilot"]["theme_queue"][0]["title"], "x")
        # メモリも書いた直後の内容
        self.assertEqual(self.cm.get("t-cfg")._raw["genre_blacklist"], ["宇宙・天体"])

    def test_get_reloads_when_disk_changes(self):
        self.assertEqual(self.cm.get("t-cfg")._raw.get("genre_blacklist"), [])
        self._external_edit(genre_blacklist=["オブジェクトクラス"])
        self.assertEqual(self.cm.get("t-cfg")._raw["genre_blacklist"], ["オブジェクトクラス"],
                         "外部編集が get() に反映されていない（再起動しないと見えない）")

    def test_update_channel_uses_disk_as_base(self):
        self._external_edit(genre_blacklist=["宇宙・天体"])
        self.cm.update_channel("t-cfg", {"name": "renamed"})
        raw = json.loads((self.dir / "t-cfg.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["name"], "renamed")
        self.assertEqual(raw["genre_blacklist"], ["宇宙・天体"])

    def test_write_is_atomic_no_tmp_left(self):
        self.cm.patch_channel_file("t-cfg", lambda r: r.__setitem__("k", 1))
        self.assertFalse((self.dir / "t-cfg.json.tmp").exists())
        self.assertEqual(json.loads((self.dir / "t-cfg.json").read_text())["k"], 1)

    def test_no_other_writer_bypasses_manager(self):
        """backend 内で data/channels/*.json を直接 write_text するコードが残っていないこと。"""
        import re
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for p in list(root.glob("api_*.py")) + [root / "main.py",
                                                 root / "api_channel_autopilot.py"]:
            src = p.read_text(encoding="utf-8")
            for m in re.finditer(r'_data_dir / f"\{channel_id\}\.json"', src):
                line = src[: m.start()].count("\n") + 1
                # 読むだけの箇所は許す（write_text が同じ関数内に無ければ OK）
                tail = src[m.end(): m.end() + 800]
                if "write_text" in tail:
                    offenders.append(f"{p.name}:{line}")
        self.assertEqual(offenders, [], f"ChannelManager を迂回して書いている: {offenders}")


# =====================================================================
# 6. gate_failures — 握り潰さない
# =====================================================================

class GateFailuresRecordedTest(unittest.TestCase):
    def test_run_gate_records_exception(self):
        from pipeline.auto_scenario.generator import ScenarioGenerator
        g = ScenarioGenerator.__new__(ScenarioGenerator)
        res = {}

        def _boom(*a):
            raise RuntimeError("classifier exploded")
        g._run_gate(res, "genre", _boom, 1, 2)
        self.assertEqual(res["gate_failures"][0]["gate"], "genre")
        self.assertIn("classifier exploded", res["gate_failures"][0]["error"])

    def test_generate_wraps_every_title_gate(self):
        import inspect
        from pipeline.auto_scenario import generator as gen
        src = inspect.getsource(gen.ScenarioGenerator.generate)
        for name in ("title_duplicate", "title_quality", "title_constraints",
                     "cross_channel_keywords", "fact_consistency"):
            self.assertIn(f'"{name}"', src, f"ゲート {name} が _run_gate 経由でない")
        # 素の呼び出しが残っていない
        for fn in ("self._reject_duplicate_title(", "self._enforce_title_quality(",
                   "self._enforce_title_constraints(", "self._enforce_cross_channel_keywords(",
                   "self._enforce_fact_consistency("):
            self.assertNotIn(fn, src, f"{fn} が直接呼ばれている")

    def test_publish_path_has_no_silent_pass(self):
        """公開経路の致命的な握り潰し（09-12 に直した3箇所）が復活していないこと。"""
        root = Path(__file__).resolve().parent.parent
        p4 = (root / "api_phase4.py").read_text(encoding="utf-8")
        self.assertIn("auto_publish marker failed", p4)
        self.assertIn("video_status への記録に失敗 (job", p4)
        ap = (root / "api_channel_autopilot.py").read_text(encoding="utf-8")
        self.assertIn("scenario save failed", ap)
        self.assertNotIn("sg.save_scenario(scenario)\n        except Exception:\n            pass", ap)


if __name__ == "__main__":
    unittest.main()
