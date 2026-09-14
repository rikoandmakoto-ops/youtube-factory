"""2026-09-14 の修正のテスト。

  1. entity_gate     — 実在人物名・第三者IP をテーマ／タイトルから弾く（堀大輔の再発防止）
  2. trend / comment — 自動キュー投入がゲートを通る
  3. publish_blocked — ゲート未解消（ok:false）の動画は autopilot が投入せず、
                       on_generation_complete が公開しない
  4. claude_client   — 無効キー（401）を一度見たら has_api_key() が False（GPT 退避口が開く）
  5. thumb_style     — style_hint がショートサムネの描画パラメータに翻訳され、描画側が使う
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import entity_gate as eg  # noqa: E402


class EntityGateTest(unittest.TestCase):
    def test_real_person_is_blocked(self):
        for t in ("なぜ堀大輔は72時間眠らないのか？睡眠不足の恐怖",
                  "ショートスリーパー堀大輔とSCP: 睡眠不足の恐怖",
                  "ヒカキンの新商品、実はこんな理由で売れる！",
                  "久保建英の成功: 自己効力感の重要性",
                  "田中角栄が日本列島を改造した理由",
                  "ユニクロ柳井社長が広告をやめた理由",
                  "イーロン・マスクが火星に行く理由",
                  "Elon Musk が火星に行く理由"):
            hit = eg.check(t)
            self.assertIsNotNone(hit, t)
            self.assertEqual(hit.kind, "person", t)

    def test_third_party_ip_is_blocked(self):
        for t in ("ゼルダの冒険が教える社会的つながりの力", "鬼滅の刃が売れた理由"):
            hit = eg.check(t)
            self.assertIsNotNone(hit, t)
            self.assertEqual(hit.kind, "ip", t)

    def test_common_words_are_not_names(self):
        for t in ("原因不明の頭痛の正体", "森林が水を蓄える理由", "関西人への偏見",
                  "四天王が四人でなければならない理由", "林業が衰退した理由",
                  "東京の地下に眠る川の正体", "SCP-682が適応する本当の理由",
                  "ワークマンが客層を入れ替えた本当の理由", "スシローが回転をやめた店を増やす理由",
                  "ドン・キホーテが1店舗で4万点を置く理由", "ピグマリオン効果",
                  "雷獣の元ネタが怖すぎる、落雷の跡に爪痕が残る理由"):
            self.assertIsNone(eg.check(t), t)

    def test_channel_allow_and_own_ip(self):
        self.assertIsNone(eg.check("ポケモンの進化の理由", {"id": "pokemon-lab"}))
        self.assertIsNotNone(eg.check("ポケモンの進化の理由", {"id": "scp-lab"}))
        self.assertIsNone(eg.check("妖怪ウォッチの設定", {"id": "yokai-watch"}))
        self.assertIsNone(eg.check("堀大輔の一日", {"id": "x", "entity_gate": {"allow": ["person"]}}))
        self.assertIsNone(eg.check("堀大輔の一日", {"id": "clip-x", "style": "clip"}))

    def test_focus_channel_queues_are_clean_or_explicit(self):
        """注力5chのキュー／seeds に、ゲートに当たる題材が残っていないこと。"""
        root = Path(__file__).resolve().parents[2] / "data" / "channels"
        for cid in ("daily-science", "scp-lab", "yokai-watch", "company-facts"):
            d = json.loads((root / f"{cid}.json").read_text(encoding="utf-8"))
            titles = [t.get("title", "") for t in (d.get("autopilot") or {}).get("theme_queue") or []]
            titles += [s.get("title", "") if isinstance(s, dict) else s for s in d.get("theme_seeds") or []]
            bad = [(t, eg.check(t, d).matched) for t in titles if t and eg.check(t, d)]
            self.assertEqual(bad, [], f"{cid}: {bad}")


class IntakeGateTest(unittest.TestCase):
    def test_trend_scanner_entity_block_reason(self):
        from pipeline.analytics import trend_scanner as ts
        with mock.patch.object(ts, "_channel_raw", return_value={"id": "scp-lab"}):
            self.assertIsNotNone(ts.entity_block_reason("scp-lab", "ショートスリーパー", "堀大輔とSCP"))
            self.assertIsNone(ts.entity_block_reason("scp-lab", "ショートスリーパー", "眠らない人間の異常性"))

    def test_trend_queue_theme_refuses_person(self):
        from pipeline.analytics import trend_scanner as ts
        fake_api = mock.Mock()
        with mock.patch.object(ts, "_channel_raw", return_value={"id": "scp-lab"}), \
             mock.patch.dict(sys.modules, {"api_channel_autopilot": fake_api}):
            self.assertIsNone(ts._queue_theme("scp-lab", "堀大輔とSCP: 睡眠不足の恐怖", ""))
        fake_api._load_autopilot.assert_not_called()
        fake_api._save_autopilot.assert_not_called()

    def test_scoring_prompt_forbids_persons(self):
        from pipeline.analytics import trend_scanner as ts
        _, user = ts._build_scoring_prompt([{"keyword": "x", "source": "s"}],
                                           channel_name="c", channel_concept="k", seeds=[])
        self.assertIn("実在の人物名", user)


class PublishBlockedTest(unittest.TestCase):
    def _gen(self):
        from pipeline.auto_scenario.generator import ScenarioGenerator
        return ScenarioGenerator.__new__(ScenarioGenerator)

    def test_block_reasons(self):
        g = self._gen()
        self.assertEqual(g._publish_block_reasons({}), [])
        self.assertEqual(g._publish_block_reasons({"title_constraints": {"ok": True}}), [])
        # 実効文字数だけの未解消は止めない
        self.assertEqual(g._publish_block_reasons({"title_constraints": {
            "ok": False, "violations": [{"rule": "min_effective_chars", "label": "x", "detail": "16"}]}}), [])
        r = g._publish_block_reasons({"title_constraints": {
            "ok": False, "violations": [{"rule": "max_digit_groups", "label": "数字は1個まで", "detail": "12/72"}]}})
        self.assertEqual(len(r), 1); self.assertIn("数字は1個まで", r[0])
        r = g._publish_block_reasons({"entity_gate": {"ok": False, "reason": "著名人『堀大輔』"}})
        self.assertIn("堀大輔", r[0])
        r = g._publish_block_reasons({"fact_consistency": {"ok": False, "conflicts": [
            {"entity": "味の素", "metric": "年収", "old_value": 900, "new_value": 950, "unit": "万円"}]}})
        self.assertIn("味の素", r[0])

    def test_dedupe_theme_hard_rejects_person(self):
        from pipeline.auto_scenario.generator import ThemeRejectedError
        g = self._gen()
        g._existing_titles_for_dedup = lambda cid: []
        g._collect_past_themes = lambda cid, limit=50: []
        g.suggest_themes = lambda *a, **k: []
        ch = mock.Mock(); ch.id = "scp-lab"; ch._raw = {"id": "scp-lab"}
        ch.theme_seeds = [{"title": "堀大輔の睡眠"}]
        with self.assertRaises(ThemeRejectedError):
            g._dedupe_theme(ch, {"title": "ショートスリーパー堀大輔とSCP"})
        ch.theme_seeds = [{"title": "眠らない職員の記録"}]
        out = g._dedupe_theme(ch, {"title": "ショートスリーパー堀大輔とSCP"})
        self.assertEqual(out["title"], "眠らない職員の記録")

    def test_title_entity_gate_regenerates_then_blocks(self):
        g = self._gen()
        ch = mock.Mock(); ch.id = "scp-lab"; ch._raw = {"id": "scp-lab"}
        # 1回目の作り直しで解消するケース
        g._regenerate_title_with_bans = lambda *a, **k: "なぜ眠らない人間は消えるのか"
        res = {"title": "なぜ堀大輔は72時間眠らないのか"}
        g._enforce_entity_gate(ch, {"title": "t"}, res, {})
        self.assertTrue(res["entity_gate"]["ok"])
        self.assertEqual(res["title"], "なぜ眠らない人間は消えるのか")
        self.assertEqual(res["original_title"], "なぜ堀大輔は72時間眠らないのか")
        # 解消しないケース → ok False → publish_blocked
        g._regenerate_title_with_bans = lambda *a, **k: "堀大輔が眠らない理由"
        res = {"title": "なぜ堀大輔は72時間眠らないのか"}
        g._enforce_entity_gate(ch, {"title": "t"}, res, {})
        self.assertFalse(res["entity_gate"]["ok"])
        self.assertEqual(res["title"], "なぜ堀大輔は72時間眠らないのか")
        self.assertTrue(g._publish_block_reasons(res))

    def test_on_generation_complete_skips_blocked(self):
        import api_phase4
        job = mock.Mock()
        job.id = "j1"; job.title = "t"; job.channel_id = "scp-lab"
        job.scenario_data = {"_options": {"auto_publish": True},
                             "publish_blocked": ["タイトルに実在人物/第三者IP: 堀大輔"]}
        sent = []
        cm = mock.Mock()
        with mock.patch.object(api_phase4, "_send_event_notification",
                               side_effect=lambda k, m: sent.append((k, m))), \
             mock.patch.dict(api_phase4._state, {"channel_manager": cm}):
            api_phase4.on_generation_complete(job)
        self.assertTrue(any(k == "error" and "公開を止めました" in m for k, m in sent), sent)
        # channel_manager.get すら呼ばれない（公開経路に入っていない）
        cm.get.assert_not_called()

    def test_autopilot_does_not_submit_blocked_job(self):
        import inspect
        import api_channel_autopilot as ap
        src = inspect.getsource(ap._run_autopilot)
        self.assertIn('scenario.get("publish_blocked")', src)
        self.assertLess(src.index('scenario.get("publish_blocked")'), src.index("queue.submit("))


class ClaudeInvalidKeyLatchTest(unittest.TestCase):
    def test_401_latches_has_api_key_false_until_key_changes(self):
        from pipeline import claude_client as cc
        if cc.Anthropic is None:
            self.skipTest("anthropic SDK 未導入")
        orig = cc._AUTH_FAILED_KEY
        try:
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-bad"}):
                cc._AUTH_FAILED_KEY = None
                self.assertTrue(cc.has_api_key())
                cc._record_error(RuntimeError("Error code: 401 - authentication_error: API key is invalid."),
                                 "t", "m")
                self.assertFalse(cc.has_api_key())
                from pipeline import openai_policy
                self.assertTrue(openai_policy.direct_text_api_allowed())
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-new"}):
                self.assertTrue(cc.has_api_key(), "キーを差し替えたら復帰する")
        finally:
            cc._AUTH_FAILED_KEY = orig


class ThumbStyleTest(unittest.TestCase):
    def test_heuristic_reads_positive_sentences_only(self):
        from pipeline import thumb_style as ts
        s = ts.heuristic_style("企業の実店舗写真を背景に、赤帯ヘッダーと白太字テキスト。暗いホラー調にはしない。")
        self.assertEqual(s["background"], "photo")
        self.assertNotEqual(s["mood"], "dark")
        s = ts.heuristic_style("深いティールグリーン〜ダークネイビーの背景。白い明朝体テキスト。")
        self.assertEqual(s["font"], "mincho")
        self.assertEqual(s["background"], "gradient")
        self.assertIsNotNone(s["palette"])

    def test_explicit_short_style_wins_without_llm(self):
        from pipeline import thumb_style as ts
        ch = {"id": "x", "thumbnail_template": {
            "style_hint": "写真", "short_style": {"background": "gradient", "font": "mincho",
                                                "palette": {"top": [1, 2, 3], "bottom": [4, 5, 6]}}}}
        with mock.patch.object(ts, "_llm_translate", side_effect=AssertionError("must not call")):
            s = ts.resolve(ch)
        self.assertEqual(s["source"], "short_style")
        self.assertEqual(s["palette"]["top"], [1, 2, 3])
        self.assertEqual(s["font"], "mincho")

    def test_resolve_caches_per_hint(self):
        from pipeline import thumb_style as ts
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(ts, "_CACHE_PATH", Path(d) / "c.json"):
            calls = []
            def fake(hint, name, concept, key):
                calls.append(hint)
                return ts._normalize({"background": "gradient", "font": "gothic", "mood": "dark"})
            with mock.patch.object(ts, "_llm_translate", side_effect=fake):
                ch = {"id": "x", "thumbnail_template": {"style_hint": "暗い"}}
                self.assertEqual(ts.resolve(ch)["source"], "llm")
                self.assertEqual(ts.resolve(ch)["source"], "cache")
            self.assertEqual(len(calls), 1)

    def test_short_thumbnail_uses_style(self):
        import inspect
        from pipeline import video_generator as vg
        src = inspect.getsource(vg.generate_short_thumbnail)
        self.assertIn("_ts.resolve(channel_dict)", src)
        self.assertIn('"photo"', src)
        self.assertIn('"mincho"', src)
        self.assertIn("require_entity_match", src)

    def test_bg_query_substitutes_subject(self):
        from pipeline import thumb_style as ts
        q = ts.bg_query_for({"bg_query": "{subject} storefront"}, "ワークマンが客層を入れ替えた理由",
                            subject="ワークマン")
        self.assertEqual(q, "ワークマン storefront")


if __name__ == "__main__":
    unittest.main()
