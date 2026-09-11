"""2026-09-09 の修正のテスト。

  1. jp_wordmatch      — 語彙照合を素の部分一致から「語として当たったか」に変える
  2. has_confident_render — 1. を使って全13chで無関係アイコンを出さない
  3. title_constraints.require_any_of — 「必ず含む」制約（答え提示語）
  4. 2ch-matome の theme_seeds が結論型になっていること
  5. daily-science の theme_blacklist 棚卸しで重複防止能力が落ちていないこと
  6. publish_log.reconcile_scheduled — 予約公開が published に遷移すること
  7. analytics freshness — video_metrics の欠測検知
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import jp_wordmatch as jw
from pipeline import pillow_illustration as pi
from pipeline import title_constraints as tc

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANNELS = REPO_ROOT / "data" / "channels"


def _channel(cid):
    return json.loads((CHANNELS / f"{cid}.json").read_text(encoding="utf-8"))


# =====================================================================
# 1. jp_wordmatch
# =====================================================================

class TestJpWordMatch(unittest.TestCase):

    def test_single_kanji_inside_compound_is_not_a_word(self):
        """1文字の漢字が漢字複合語の内側に当たるのを認めない（実測の誤爆）。"""
        cases = [
            ("月額いくら払えば元が取れるのか", "月"),
            ("ロケット団の言葉選びを3作品で追う", "葉"),
            ("注目された理由", "目"),
            ("駄目な運用の話", "目"),
            ("影響が出るまでの時間", "影"),
            ("意味が分からない仕様", "味"),
            ("興味を持たれる条件", "味"),
            ("能力が足りない", "力"),
            ("本音が出る瞬間", "音"),
            ("水曜だけ人が減る", "水"),
            ("火曜の残業", "火"),
            ("血税の使い道", "血"),
            ("森林の管理", "森"),
        ]
        for text, kw in cases:
            with self.subTest(text=text, kw=kw):
                self.assertIn(kw, text)               # 素の部分一致では当たる
                self.assertFalse(jw.contains_word(text, kw))

    def test_single_kanji_standing_alone_is_a_word(self):
        cases = [
            ("目がかゆくなる本当の理由", "目"),
            ("月だけが見える夜", "月"),
            ("水を飲むと落ち着く", "水"),
            ("森の奥で聞こえる音", "森"),
            ("音が消える瞬間", "音"),
        ]
        for text, kw in cases:
            with self.subTest(text=text, kw=kw):
                self.assertTrue(jw.contains_word(text, kw))

    def test_katakana_followed_by_kanji_is_a_compound(self):
        """カタカナ＋漢字は複合名詞・固有名詞になるので元の語では無い。"""
        self.assertFalse(jw.contains_word("ロケット団の言葉選び", "ロケット"))
        self.assertFalse(jw.contains_word("アニメ版だけ違う設定", "アニメ"))

    def test_katakana_must_match_the_whole_run(self):
        self.assertFalse(jw.contains_word("サンドイッチの断面", "サン"))
        self.assertFalse(jw.contains_word("コーヒーカップの話", "コーヒー"))
        self.assertTrue(jw.contains_word("ロケットの打ち上げが遅れる理由", "ロケット"))

    def test_latin_must_match_the_whole_run(self):
        self.assertFalse(jw.contains_word("SDNAという表記", "DNA"))
        self.assertTrue(jw.contains_word("DNA鑑定の精度", "DNA"))

    def test_multi_char_kanji_inside_compound_is_kept(self):
        """2文字以上の漢字は複合語の中でも意味が保たれるので許す。"""
        self.assertTrue(jw.contains_word("筋肉痛が2日後に来る理由", "筋肉"))
        self.assertTrue(jw.contains_word("睡眠不足のときだけ起きる", "睡眠"))
        self.assertTrue(jw.contains_word("電気代が夏だけ跳ねる", "電気"))

    def test_hiragana_inflection_still_matches(self):
        """ひらがな側は活用があるので境界を見ない。"""
        self.assertTrue(jw.contains_word("暗い所で見えない理由", "見え"))
        self.assertTrue(jw.contains_word("足がつるのはなぜか", "つる"))

    def test_find_words_preserves_order(self):
        self.assertEqual(jw.find_words("目と耳の話", ["耳", "目", "鼻"]), ["耳", "目"])


# =====================================================================
# 2. has_confident_render（全チャンネル共通の照合規則）
# =====================================================================

class TestHasConfidentRender(unittest.TestCase):

    def test_pokemon_rocket_dan_no_longer_renders(self):
        """09-08 実測の誤爆。『ロケット団』『言葉』でアイコン2個が立っていた。"""
        topic = "幹部だけ別物 台詞の正体 ロケット団の言葉選びを3作品で追う"
        self.assertFalse(pi.has_confident_render(topic, card_style="textbook"))

    def test_unrelated_topics_do_not_render(self):
        for topic in [
            "月額いくら払えば元が取れるのか 家計の正体",
            "注目された本音 影響が出るまでの意味",
            "上司の能力と部下の魅力 評価の裏側",
        ]:
            with self.subTest(topic=topic):
                self.assertFalse(pi.has_confident_render(topic, card_style="textbook"))

    def test_genuine_science_topics_still_render(self):
        for topic in [
            "睡眠中に脳が記憶を整理する本当の理由",
            "汗をかくと体温が下がる仕組み",
            "血液が脳に届くまでの本当の理由",
        ]:
            with self.subTest(topic=topic):
                self.assertTrue(pi.has_confident_render(topic, card_style="textbook"))

    def test_common_compounds_are_listed_explicitly(self):
        """1文字漢字が拾えない2字熟語は語彙に直接並べて取り戻す。

        規則を緩めて拾おうとすると「月額」の月・「言葉」の葉が戻ってくるので、
        語彙を足す側で解決する（→ `_TEXTBOOK_KEYWORDS` のコメント）。
        """
        expect = {"寝落ち": "moon", "湿度": "water", "発熱": "fire",
                  "秒間": "clock", "脳内": "brain", "毛穴": "skin",
                  "静電気": "bolt", "星空": "planet"}
        for word, icon in expect.items():
            with self.subTest(word=word):
                hit = pi._match_textbook(f"{word}が変わる本当の理由")
                self.assertIn(icon, [i for i, _ in hit], f"{word} が拾えていない")

    def test_leaked_document_style_uses_the_same_rule(self):
        """scp-lab 側（`leaked-document`）も同じ境界規則で判定する。"""
        self.assertFalse(pi.has_confident_render("影響を受けた職員の記録",
                                                 card_style="leaked-document"))
        self.assertFalse(pi.has_confident_render("駄目になった収容手順",
                                                 card_style="leaked-document"))
        self.assertTrue(pi.has_confident_render("扉の向こうに立つ人影",
                                                card_style="leaked-document"))

    def test_keyword_icons_disabled_still_returns_false(self):
        self.assertFalse(pi.has_confident_render("睡眠と記憶の話", use_keyword_icons=False))

    def test_channels_no_longer_disable_the_card_by_flag(self):
        """ch単位の `thumbnail_card: false` による潰しは残さない（根本修正済み）。"""
        for cid in ("pokemon-lab", "scp-lab", "yokai-watch"):
            with self.subTest(cid=cid):
                si = ((_channel(cid).get("video_format") or {})
                      .get("short_illustrations") or {})
                self.assertNotEqual(si.get("thumbnail_card"), False)


# =====================================================================
# 3. title_constraints.require_any_of
# =====================================================================

class TestRequireAnyOf(unittest.TestCase):

    CH = {"title_rules": {"hard_constraints": {
        "max_chars": 30,
        "require_any_of": {
            "label": "答え提示語",
            "words": ["理由", "正体", "本当の", "実は", "わけ", "なぜ", "真相", "裏側", "実態"],
            "repair_with": ["正体", "理由"],
        },
    }}}

    def test_title_without_marker_is_a_violation(self):
        r = tc.check("氷が水に浮く不思議な現象", self.CH)
        self.assertFalse(r["ok"])
        self.assertEqual(r["violations"][0]["rule"], "require_any_of")
        self.assertTrue(any("答え提示語" in a for a in r["advice"]))

    def test_title_with_marker_passes(self):
        self.assertTrue(tc.check("氷が水に浮く本当の理由", self.CH)["ok"])

    def test_marker_must_be_a_word_not_a_substring(self):
        """『理不尽』の中の『理』のような偶然一致では満たしたことにしない。"""
        self.assertFalse(tc.check("理不尽な校則の話をする回", self.CH)["ok"])

    def test_repair_appends_marker_after_a_noun_with_no(self):
        out = tc.repair("氷が水に浮く不思議な現象", self.CH)
        self.assertTrue(out.endswith("の正体"), out)
        self.assertTrue(tc.check(out, self.CH)["ok"])

    def test_repair_appends_marker_directly_after_a_verb(self):
        """連体形のあとに『の』を挟むと壊れる（「出すの理由」）。"""
        out = tc.repair("妖怪が夜に出る", self.CH)
        self.assertEqual(out, "妖怪が夜に出る正体")

    def test_repair_does_not_touch_particles_or_word_order(self):
        original = "サウナで整うと言われる感覚"
        out = tc.repair(original, self.CH)
        self.assertTrue(out.startswith(original), out)

    def test_repair_drops_a_trailing_question_mark_before_appending(self):
        out = tc.repair("氷はなんで水に浮くの？", self.CH)
        self.assertNotIn("？", out)
        self.assertTrue(tc.check(out, self.CH)["ok"])

    def test_repair_respects_max_chars(self):
        ch = json.loads(json.dumps(self.CH))
        ch["title_rules"]["hard_constraints"]["max_chars"] = 20
        out = tc.repair("氷が水に浮く現象について科学的にきちんと説明していく回", ch)
        self.assertLessEqual(len(out), 20)
        self.assertTrue(tc.check(out, ch)["ok"], out)

    def test_repair_never_produces_broken_japanese(self):
        """助詞の連結（「はで」「でずつ」）を作らない。"""
        for t in ["ピカチュウは10%なのに", "元ネタは3つある", "3回目の店で起きたこと"]:
            with self.subTest(t=t):
                out = tc.repair(t, self.CH)
                self.assertFalse(tc._is_broken_japanese(out, t), out)

    def test_repair_picks_a_marker_that_is_a_noun(self):
        """『なぜ』『本当の』は語尾に付けられないので repair には使わない。"""
        ch = {"title_rules": {"hard_constraints": {"require_any_of": {
            "words": ["なぜ", "本当の", "真相"], "repair_with": ["真相"]}}}}
        self.assertTrue(tc.repair("上司の機嫌が朝だけいい", ch).endswith("真相"))

    def test_list_shorthand_is_accepted(self):
        ch = {"title_rules": {"hard_constraints": {"require_any_of": ["理由", "正体"]}}}
        self.assertFalse(tc.check("氷が水に浮く現象", ch)["ok"])
        self.assertTrue(tc.check("氷が水に浮く理由", ch)["ok"])

    def test_absent_constraint_keeps_old_behaviour(self):
        ch = {"title_rules": {"hard_constraints": {"max_chars": 30}}}
        self.assertTrue(tc.check("答え提示語のないタイトル", ch)["ok"])


class TestRequireAnyOfChannelConfig(unittest.TestCase):
    """対象6chの設定が `hard_constraints` 側へ移行できていること。"""

    TARGETS = ("daily-science", "scp-lab", "pokemon-lab", "yokai-watch",
               "2ch-matome", "company-facts")

    def test_all_six_channels_have_the_hard_constraint(self):
        for cid in self.TARGETS:
            with self.subTest(cid=cid):
                hc = ((_channel(cid).get("title_rules") or {})
                      .get("hard_constraints") or {})
                spec = hc.get("require_any_of")
                self.assertIsInstance(spec, dict, f"{cid} に require_any_of が無い")
                self.assertTrue(spec.get("words"))
                self.assertTrue(spec.get("repair_with"))

    def test_repair_words_are_suffixable_nouns(self):
        """語尾に足しても日本語が壊れない語だけを repair_with に置く。"""
        not_suffixable = {"なぜ", "本当の", "実は", "何故", "なんで", "どうして"}
        for cid in self.TARGETS:
            hc = (_channel(cid).get("title_rules") or {}).get("hard_constraints") or {}
            for w in (hc.get("require_any_of") or {}).get("repair_with") or []:
                with self.subTest(cid=cid, w=w):
                    self.assertNotIn(w, not_suffixable)

    def test_repair_output_passes_every_other_constraint(self):
        """答え提示語を足した結果が数字禁止・文字数などに違反しないこと。"""
        samples = ["妖怪が夜に出る", "上司の機嫌が朝だけいい", "氷が水に浮く現象",
                   "社員が定時で帰る会社", "自分の声が別人に聞こえる"]
        for cid in self.TARGETS:
            raw = _channel(cid)
            for s in samples:
                with self.subTest(cid=cid, s=s):
                    out = tc.repair(s, raw)
                    # 2026-09-11: min_effective_chars（実効長の下限）は repair が
                    # 原理的に直せない規則なので除外する。文字を足す修復は意味の
                    # ない水増しになるため、検査と再生成 advice だけに留めてある。
                    # ここで見たいのは「答え提示語を足した結果、他の規則を新たに
                    # 破っていないか」なので、元から短い samples の長さ不足は対象外。
                    left = [v for v in tc.check(out, raw)["violations"]
                            if v["rule"] not in tc.UNREPAIRABLE_RULES]
                    self.assertEqual(left, [],
                                     f"{cid}: {s!r} → {out!r} が未解消")
                    self.assertFalse(tc._is_broken_japanese(out, s), out)


# =====================================================================
# 4. 2ch-matome の theme_seeds
# =====================================================================

# 参加型（お題を投げて答えを渡さない型）の語尾・定型。
PARTICIPATORY_MARKERS = (
    "あげてけ", "書いてけ", "晒せ", "当ててみてくれ", "当てるスレ", "当ててくれ",
    "語って", "教えてくれ", "質問ある", "答えたる", "おる？", "おるか",
    "какой",  # 誤検出防止のダミー（並びの型を固定するためだけ）
)


class TestNichanThemeSeeds(unittest.TestCase):

    def setUp(self):
        self.cfg = _channel("2ch-matome")
        self.markers = [m for m in PARTICIPATORY_MARKERS if m != "какой"]
        self.answer_words = ["理由", "正体", "本当の", "実は", "わけ", "なぜ",
                             "真相", "裏側", "実態"]

    def _titles(self, items):
        return [(i.get("title") if isinstance(i, dict) else str(i)) for i in items]

    def test_no_participatory_seeds_remain(self):
        bad = [t for t in self._titles(self.cfg.get("theme_seeds") or [])
               if any(m in t for m in self.markers)]
        self.assertEqual(bad, [], f"参加型が残っている: {bad}")

    def test_every_seed_presents_an_answer(self):
        missing = [t for t in self._titles(self.cfg.get("theme_seeds") or [])
                   if not jw.any_word(t, self.answer_words)]
        self.assertEqual(missing, [], f"答え提示語が無い: {missing}")

    def test_live_queue_is_also_conclusion_type(self):
        """実際に消費されるのは autopilot.theme_queue なのでそちらも見る。"""
        q = self._titles((self.cfg.get("autopilot") or {}).get("theme_queue") or [])
        bad = [t for t in q if any(m in t for m in self.markers)]
        self.assertEqual(bad, [], f"live queue に参加型が残っている: {bad}")
        missing = [t for t in q if not jw.any_word(t, self.answer_words)]
        self.assertEqual(missing, [], f"live queue に答え提示語が無い: {missing}")

    def test_live_queue_has_no_duplicate_titles(self):
        q = self._titles((self.cfg.get("autopilot") or {}).get("theme_queue") or [])
        dups = sorted({t for t in q if q.count(t) > 1})
        self.assertEqual(dups, [], f"live queue が重複している: {dups}")

    def test_module_queue_file_is_also_conclusion_type(self):
        """`data/channels/<ch>/theme_queue.json` は theme_seeds から再補充される。"""
        p = CHANNELS / "2ch-matome" / "theme_queue.json"
        if not p.exists():
            self.skipTest("module queue file not present")
        items = json.loads(p.read_text(encoding="utf-8")).get("items") or []
        bad = [t for t in self._titles(items) if any(m in t for m in self.markers)]
        self.assertEqual(bad, [], f"module queue に参加型が残っている: {bad}")


# =====================================================================
# 5. daily-science の theme_blacklist 棚卸し
# =====================================================================

# 棚卸し前（2026-09-08 時点）の 42 語。これが止めていた過去タイトルは
# 棚卸し後も必ず止まっていなければならない（重複防止能力の非回帰）。
OLD_DS_BLACKLIST = [
    "骨伝導", "しゃっくり", "横隔膜", "録音した自分の声", "録音の声", "自分の声が別人",
    "宇宙", "天体", "星", "銀河", "酸素が1秒", "ドアが閉まる寸前", "センサーの待機設計",
    "本を読むと眠くなる", "本だけで眠く", "待機設計", "ドアが閉ま", "酸素が消え",
    "口の乾き", "本を開いた", "本を読むと", "金縛り", "蛍光灯", "睡眠の深さ", "浅い眠り",
    "炭酸", "体が緩む", "成長ホルモン", "寝ている間だけ分泌", "耳が詰ま", "毎晩3時",
    "42度", "ブルーライト", "シャワーカーテン", "3割増し", "悲しい曲", "あくび",
    "指を鳴ら", "指パキ", "笑うだけで", "免疫力", "録音",
]

# 棚卸しで解放したい「領域ごと封じていた」語。これらの領域が通るようになること。
FREED_TOPICS = [
    "土星の輪が消えて見える年がある本当の理由",      # 星／天体／宇宙
    "銀河の腕が渦を巻いたままな理由",                  # 銀河
    "会議を録音すると話が短くなる本当の理由",          # 録音
    "免疫力という言葉が医学的に存在しない理由",        # 免疫力
    "炭酸水で洗うと汚れが落ちる本当の理由",            # 炭酸
    "悲しい曲を聴くと落ち着く本当の理由",              # 悲しい曲
]


class TestDailyScienceBlacklist(unittest.TestCase):

    def setUp(self):
        from pipeline.auto_scenario import theme_dedup as td
        self.td = td
        self.new = _channel("daily-science").get("theme_blacklist") or []

    def test_blacklist_got_smaller(self):
        self.assertLess(len(self.new), len(OLD_DS_BLACKLIST))

    def test_no_regression_in_duplicate_prevention(self):
        """旧リストが止めていた過去タイトルは新リストでも止まること。"""
        past = self.td.past_theme_titles("daily-science", within_days=400)
        if not past:
            self.skipTest("過去シナリオが無い環境")
        blocked_before = [t for t in past if self.td.blacklist_match(t, OLD_DS_BLACKLIST)]
        self.assertTrue(blocked_before, "旧リストが1件も止めていない＝前提が崩れている")
        leaked = [t for t in blocked_before if not self.td.blacklist_match(t, self.new)]
        self.assertEqual(leaked, [], f"重複防止が落ちた: {leaked}")

    def test_whole_domains_are_freed(self):
        for t in FREED_TOPICS:
            with self.subTest(t=t):
                self.assertIsNone(self.td.blacklist_match(t, self.new),
                                  f"まだ領域ごと塞がれている: {t}")

    def test_broad_single_domain_words_are_gone(self):
        for w in ("宇宙", "星", "天体", "銀河", "録音", "免疫力", "炭酸"):
            self.assertNotIn(w, self.new)


# =====================================================================
# 6. publish_log.reconcile_scheduled
# =====================================================================

class TestReconcileScheduled(unittest.TestCase):

    def setUp(self):
        from pipeline import publish_log
        self.publish_log = publish_log
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = publish_log.PUBLISH_DB
        publish_log.PUBLISH_DB = Path(self.tmp.name) / "video_publish.db"

    def tearDown(self):
        self.publish_log.PUBLISH_DB = self._orig
        self.tmp.cleanup()

    def _rows(self):
        conn = self.publish_log.connect()
        try:
            return {r[0]: r[1:] for r in conn.execute(
                "SELECT job_id, status, published_at FROM video_status")}
        finally:
            conn.close()

    def test_past_scheduled_becomes_published(self):
        self.publish_log.record_publish(
            channel_id="daily-science", video_id="abc123",
            job_id="j1", scheduled_at="2026-09-08T08:00:00Z")
        self.assertEqual(self._rows()["j1"][0], "scheduled")

        n = self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z")
        self.assertEqual(n, 1)
        status, published_at = self._rows()["j1"]
        self.assertEqual(status, "published")
        self.assertEqual(published_at, "2026-09-08T08:00:00Z")

    def test_future_scheduled_is_left_alone(self):
        self.publish_log.record_publish(
            channel_id="daily-science", video_id="future1",
            job_id="j2", scheduled_at="2026-09-30T08:00:00Z")
        self.assertEqual(self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z"), 0)
        self.assertEqual(self._rows()["j2"][0], "scheduled")

    def test_rows_without_video_id_are_not_promoted(self):
        conn = self.publish_log.connect()
        conn.execute(
            "INSERT INTO video_status (job_id, channel_id, status, video_id, "
            "scheduled_at, updated_at) VALUES ('j3','x','scheduled',NULL,"
            "'2026-09-01T00:00:00Z',0)")
        conn.commit()
        conn.close()
        self.assertEqual(self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z"), 0)
        self.assertEqual(self._rows()["j3"][0], "scheduled")

    def test_is_idempotent(self):
        self.publish_log.record_publish(
            channel_id="daily-science", video_id="abc123",
            job_id="j1", scheduled_at="2026-09-08T08:00:00Z")
        self.assertEqual(self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z"), 1)
        self.assertEqual(self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z"), 0)

    def test_naive_scheduled_at_is_treated_as_jst(self):
        """`scheduled_at` は Z 付きと naive が混在している（実データ）。"""
        self.publish_log.record_publish(
            channel_id="daily-science", video_id="naive1",
            job_id="j4", scheduled_at="2026-09-08T17:00:00")
        self.assertEqual(self.publish_log.reconcile_scheduled(now="2026-09-09T00:00:00Z"), 1)
        self.assertEqual(self._rows()["j4"][0], "published")


# =====================================================================
# 7. video_metrics の欠測検知
# =====================================================================

class TestMetricsFreshness(unittest.TestCase):

    def setUp(self):
        from pipeline.analytics import freshness
        self.freshness = freshness
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "analytics.db"
        conn = sqlite3.connect(str(self.db))
        conn.execute("CREATE TABLE video_metrics (video_id TEXT, channel_id TEXT, "
                     "date TEXT, views INTEGER)")
        for cid, n in (("2ch-matome", 50), ("daily-science", 50), ("scp-lab", 3)):
            for i in range(n):
                conn.execute("INSERT INTO video_metrics VALUES (?,?,?,?)",
                             (f"{cid}-{i}", cid, "2026-09-09", 1))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _cov(self, expected):
        return self.freshness.snapshot_coverage(
            expected_channels=expected, date="2026-09-09", db_path=self.db)

    def test_missing_channels_are_reported(self):
        cov = self._cov(["2ch-matome", "daily-science", "scp-lab", "yokai-watch"])
        self.assertEqual(cov["missing"], ["yokai-watch"])
        self.assertFalse(cov["ok"])

    def test_complete_snapshot_is_ok(self):
        cov = self._cov(["2ch-matome", "daily-science", "scp-lab"])
        self.assertEqual(cov["missing"], [])
        self.assertTrue(cov["ok"])

    def test_row_counts_are_returned_per_channel(self):
        cov = self._cov(["2ch-matome", "scp-lab"])
        self.assertEqual(cov["rows"]["2ch-matome"], 50)
        self.assertEqual(cov["rows"]["scp-lab"], 3)

    def test_markdown_names_the_missing_channels(self):
        md = self.freshness.coverage_markdown(
            self._cov(["daily-science", "yokai-watch"]))
        self.assertIn("yokai-watch", md)
        self.assertIn("欠測", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
