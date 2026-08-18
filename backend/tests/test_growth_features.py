"""タイトルCTRゲート・自動コメント・ショートのループ構成の単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_growth_features -v

守りたい回帰:
  - タイトルCTR採点が「説明型」を落とし、数字・感情ワード入りを通す
    （プロンプトで指示していても LLM が落とすため、生成後の決定論的ゲートが要る）
  - チャンネル固有の勝ち書式（引用→結果型 / 対決型 / ジャンル語）を
    低スコア扱いして無駄に作り直さない
  - 自動コメントがオプトイン制で、未設定チャンネルには投稿しない
  - 予約公開の動画は即投稿せず保留キューに積まれ、公開時刻後に投稿される
  - ショートのプロンプトにループ構成ルールが入っている
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import auto_comment as ac  # noqa: E402
from pipeline import title_quality as tq  # noqa: E402
from pipeline.auto_scenario import generator as gen  # noqa: E402

DATA_CHANNELS = Path(__file__).resolve().parents[2] / "data" / "channels"


def _load_channel(cid):
    return json.loads((DATA_CHANNELS / f"{cid}.json").read_text(encoding="utf-8"))


class TestTitleQualityScoring(unittest.TestCase):
    def test_explainer_titles_fail(self):
        """「〜について解説」型は CTR を最も落とすので必ず落第させる。"""
        for title in ("水たまりについて解説", "コーヒーの効果を解説", "睡眠のメカニズムを紹介"):
            d = tq.score_title(title)
            self.assertFalse(d["passed"], f"説明型が通ってしまった: {title} ({d['score']})")

    def test_number_and_power_words_pass(self):
        """数字＋感情ワード＋疑問形が揃ったタイトルは高スコアで通る。"""
        d = tq.score_title("99%が知らない、たった3秒で眠くなる呼吸法の正体")
        self.assertTrue(d["passed"])
        self.assertGreaterEqual(d["score"], 80)
        self.assertTrue(d["signals"]["has_number"])

    def test_bracket_prefix_penalised(self):
        """先頭の【】プレフィックスは減点される（ショートで文字数を食うだけ）。"""
        plain = tq.score_title("なぜ3秒で眠くなるのか、その本当の理由")
        braced = tq.score_title("【ゆっくり解説】なぜ3秒で眠くなるのか、その本当の理由")
        self.assertLess(braced["score"], plain["score"])

    def test_number_detection_ignores_non_counting_kanji(self):
        """「一般」「一部」のような数量でない漢数字を数字と誤検出しない。"""
        self.assertFalse(tq.has_number("一般的な現象の正体"))
        self.assertTrue(tq.has_number("3つの理由"))
        self.assertTrue(tq.has_number("三つの理由"))
        self.assertTrue(tq.has_number("９９％が知らない"))

    def test_empty_title(self):
        d = tq.score_title("")
        self.assertEqual(d["score"], 0)
        self.assertFalse(d["passed"])


class TestChannelWinningFormats(unittest.TestCase):
    """チャンネルごとの勝ち書式が低スコアで作り直しにされないこと。"""

    def test_quote_result_format_passes(self):
        """2ch まとめの「発言引用 → 結果」型は疑問形でなくても通る。"""
        d = tq.score_title(
            "上司「残業代はやる気で払う」→ 全員が黙った理由", _load_channel("2ch-matome")
        )
        self.assertTrue(d["passed"], d)

    def test_matchup_format_passes(self):
        """pokemon-lab の対決型は数字が入りにくいが通る。"""
        d = tq.score_title(
            "ガブリアスとギャラドス、どっちが勝つ？相性有利がひっくり返る条件",
            _load_channel("pokemon-lab"),
        )
        self.assertTrue(d["passed"], d)

    def test_channel_power_words_lift_score(self):
        """チャンネル JSON の title_power_words がスコアに効く。"""
        title = "SCP-3000が収容違反した日、職員が最後に見たもの"
        without = tq.score_title(title)
        with_ch = tq.score_title(title, _load_channel("scp-lab"))
        self.assertGreater(with_ch["score"], without["score"])
        self.assertTrue(with_ch["passed"])

    def test_all_channels_declare_power_words(self):
        """全チャンネルにジャンル語が入っていること（無いと汎用語だけで採点される）。"""
        for path in sorted(DATA_CHANNELS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            words = (data.get("theme_priority") or {}).get("title_power_words")
            self.assertTrue(
                isinstance(words, list) and words,
                f"{path.stem} に title_power_words がない",
            )


class TestBestOf(unittest.TestCase):
    def test_picks_highest_scoring(self):
        best = tq.best_of(["水たまりについて解説", "なぜ水たまりは3秒で消えるのか"])
        self.assertEqual(best["title"], "なぜ水たまりは3秒で消えるのか")

    def test_empty_candidates(self):
        best = tq.best_of([])
        self.assertEqual(best["title"], "")
        self.assertEqual(best["score"], 0)


class TestAutoCommentText(unittest.TestCase):
    def test_includes_subscribe_url_and_question(self):
        cd = _load_channel("daily-science")
        text = ac.build_comment_text("daily-science", title="テスト", channel_dict=cd)
        self.assertIn("sub_confirmation=1", text)
        self.assertIn(cd["publish_settings"]["auto_comment"]["question"], text)

    def test_main_url_included_for_shorts(self):
        text = ac.build_comment_text(
            "daily-science", title="テスト", is_short=True, main_url="https://youtu.be/abc"
        )
        self.assertIn("https://youtu.be/abc", text)

    def test_custom_template_is_used(self):
        cd = {
            "id": "daily-science",
            "publish_settings": {
                "auto_comment": {"enabled": True, "template": "見てくれてありがと！{subscribe_url}"}
            },
        }
        text = ac.build_comment_text("daily-science", channel_dict=cd)
        self.assertTrue(text.startswith("見てくれてありがと！"))
        self.assertIn("sub_confirmation=1", text)

    def test_template_with_unknown_placeholder_does_not_crash(self):
        cd = {
            "id": "daily-science",
            "publish_settings": {
                "auto_comment": {"enabled": True, "template": "{unknown_key} だよ"}
            },
        }
        self.assertTrue(ac.build_comment_text("daily-science", channel_dict=cd))

    def test_length_capped(self):
        cd = {
            "id": "daily-science",
            "publish_settings": {"auto_comment": {"enabled": True, "template": "あ" * 5000}},
        }
        text = ac.build_comment_text("daily-science", channel_dict=cd)
        self.assertLessEqual(len(text), ac.MAX_COMMENT_CHARS)

    def test_all_channels_opt_in(self):
        """全チャンネルで自動コメントが有効になっていること。"""
        for path in sorted(DATA_CHANNELS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = (data.get("publish_settings") or {}).get("auto_comment") or {}
            self.assertTrue(cfg.get("enabled"), f"{path.stem} の auto_comment が無効")
            self.assertTrue(cfg.get("question"), f"{path.stem} に question がない")


class TestAutoCommentGating(unittest.TestCase):
    def test_disabled_channel_is_skipped(self):
        cd = {"id": "x", "publish_settings": {"auto_comment": {"enabled": False}}}
        res = ac.post_for_video("x", "vid123", channel_dict=cd)
        self.assertFalse(res["ok"])
        self.assertEqual(res["skipped"], "disabled")

    def test_missing_config_is_skipped(self):
        res = ac.post_for_video("x", "vid123", channel_dict={"id": "x"})
        self.assertEqual(res["skipped"], "disabled")

    def test_post_comment_requires_video_and_text(self):
        self.assertFalse(ac.post_comment("daily-science", "", "hi")["ok"])
        self.assertFalse(ac.post_comment("daily-science", "vid", "  ")["ok"])


class TestPendingQueue(unittest.TestCase):
    """予約公開の動画にはコメントできないので保留キューに積まれること。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = ac.PENDING_FILE
        ac.PENDING_FILE = Path(self._tmp.name) / "pending_comments.json"

    def tearDown(self):
        ac.PENDING_FILE = self._orig
        self._tmp.cleanup()

    def _future(self, minutes=60):
        return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def test_scheduled_publish_is_queued_not_posted(self):
        cd = {"id": "daily-science", "publish_settings": {"auto_comment": {"enabled": True}}}
        res = ac.post_for_video(
            "daily-science", "vid1", publish_at=self._future(), channel_dict=cd
        )
        self.assertTrue(res["queued"])
        self.assertEqual(len(ac._read_pending()), 1)

    def test_flush_leaves_future_items_untouched(self):
        ac.enqueue("daily-science", "vid1", "text", due_at=self._future())
        res = ac.flush_pending()
        self.assertEqual(res["posted"], 0)
        self.assertEqual(res["pending"], 1)

    def test_enqueue_is_idempotent_per_video(self):
        ac.enqueue("daily-science", "vid1", "a", due_at=self._future())
        ac.enqueue("daily-science", "vid1", "b", due_at=self._future())
        self.assertEqual(len(ac._read_pending()), 1)

    def test_flush_on_empty_queue(self):
        self.assertEqual(ac.flush_pending()["posted"], 0)

    def test_due_item_is_attempted_and_dropped_when_not_retryable(self):
        """期限切れかつ再試行不能（未連携チャンネル）なら捨てて溜め込まない。"""
        ac.enqueue("no-such-channel", "vid1", "text", due_at=None)
        res = ac.flush_pending()
        self.assertEqual(res["posted"], 0)
        self.assertEqual(res["dropped"], 1)
        self.assertEqual(ac._read_pending(), [])


class TestShortLoopRule(unittest.TestCase):
    """ショートは自動ループするので、最終行→1行目が繋がる構成を指示すること。"""

    def test_loop_rule_defined(self):
        self.assertIn("ループ構成ルール", gen._LOOP_RULE_SHORT)
        self.assertIn("ご視聴ありがとう", gen._LOOP_RULE_SHORT)

    def test_loop_rule_in_both_short_prompts(self):
        src = Path(gen.__file__).read_text(encoding="utf-8")
        self.assertEqual(
            src.count("{_LOOP_RULE_SHORT}"),
            2,
            "yukkuri / monologue 両方のショートプロンプトに入っている必要がある",
        )


class TestTitleRuleBlock(unittest.TestCase):
    """プロンプトの指示と CTR 採点の基準がズレていないこと。"""

    class _FakeChannel:
        def __init__(self, raw):
            self._raw = raw

    def test_number_requirement_in_prompt(self):
        sg = gen.ScenarioGenerator(api_key="dummy")
        block = sg._title_rule_block(self._FakeChannel(_load_channel("daily-science")))
        self.assertIn("具体的な数字を必ず1つ入れる", block)
        self.assertIn("クリック率スコア", block)


if __name__ == "__main__":
    unittest.main()
