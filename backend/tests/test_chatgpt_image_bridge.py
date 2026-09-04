"""ChatGPT 画像ブリッジのキュー挙動。

`data/image_requests/` を汚さないよう、各テストで一時ディレクトリに差し替える。
"""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BridgeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = {
            k: os.environ.get(k)
            for k in ("IMAGE_BRIDGE_DIR", "IMAGE_BRIDGE_CHANNELS_DIR")
        }
        root = Path(self._tmp.name)
        self.channels_dir = root / "channels"
        self.channels_dir.mkdir()
        os.environ["IMAGE_BRIDGE_DIR"] = str(root / "queue")
        os.environ["IMAGE_BRIDGE_CHANNELS_DIR"] = str(self.channels_dir)
        from pipeline import chatgpt_image_bridge
        self.bridge = importlib.reload(chatgpt_image_bridge)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()
        from pipeline import chatgpt_image_bridge
        importlib.reload(chatgpt_image_bridge)

    def _channel(self, channel_id, **extra):
        import json
        cfg = {"id": channel_id, "name": channel_id, **extra}
        (self.channels_dir / f"{channel_id}.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg

    def _png(self, name="src.png"):
        from PIL import Image
        path = Path(self._tmp.name) / name
        Image.new("RGB", (32, 32), (10, 20, 30)).save(path)
        return path


class TestQueue(BridgeTestCase):
    def test_request_queues_and_does_not_block(self):
        """既定では待たずに None を返す（autopilot を止めないため）。"""
        got = self.bridge.request_image("a cat", size="1024x1024", channel_id="scp-lab")
        self.assertIsNone(got)
        pending = self.bridge.pending_requests()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["channel_id"], "scp-lab")
        self.assertEqual(pending[0]["status"], "pending")

    def test_identical_prompt_is_not_queued_twice(self):
        self.bridge.request_image("a cat", size="1024x1024")
        self.bridge.request_image("a cat", size="1024x1024")
        pending = self.bridge.pending_requests()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["request_count"], 2)

    def test_different_size_is_a_separate_request(self):
        self.bridge.request_image("a cat", size="1024x1024")
        self.bridge.request_image("a cat", size="1536x1024")
        self.assertEqual(len(self.bridge.pending_requests()), 2)

    def test_deliver_then_cache_hit(self):
        self.bridge.request_image("a cat", size="1024x1024")
        req_id = self.bridge.pending_requests()[0]["id"]
        self.bridge.deliver(req_id, self._png())

        self.assertEqual(self.bridge.pending_requests(), [])
        again = self.bridge.request_image("a cat", size="1024x1024")
        self.assertIsNotNone(again)
        self.assertTrue(again.startswith(b"\x89PNG"))
        # キャッシュヒットなので依頼は積み直されない
        self.assertEqual(self.bridge.pending_requests(), [])

    def test_fail_moves_out_of_pending(self):
        self.bridge.request_image("a cat", size="1024x1024")
        req_id = self.bridge.pending_requests()[0]["id"]
        self.bridge.fail(req_id, "content policy")
        self.assertEqual(self.bridge.pending_requests(), [])
        rec = self.bridge.load_request(req_id)
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(rec["reason"], "content policy")

    def test_disabled_bridge_returns_none_without_queueing(self):
        os.environ["IMAGE_BRIDGE"] = "0"
        try:
            self.assertIsNone(self.bridge.request_image("a cat"))
            self.assertEqual(self.bridge.pending_requests(), [])
        finally:
            os.environ.pop("IMAGE_BRIDGE", None)


class TestThreads(BridgeTestCase):
    """1チャンネル = 1スレッド固定。URL の正は data/channels/<ch>.json。"""

    def test_url_is_written_into_the_channel_config(self):
        import json
        self._channel("scp-lab")
        where = self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp", note="サムネ用")

        path = self.channels_dir / "scp-lab.json"
        self.assertEqual(where, str(path))
        cfg = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(cfg["image_generation"]["chatgpt_thread_url"], "https://chatgpt.com/c/scp")
        self.assertEqual(cfg["image_generation"]["note"], "サムネ用")
        # 既存フィールドを壊さない
        self.assertEqual(cfg["name"], "scp-lab")
        self.assertEqual(self.bridge.thread_url_for("scp-lab"), "https://chatgpt.com/c/scp")

    def test_updating_keeps_the_rest_of_the_config(self):
        import json
        self._channel("scp-lab", autopilot={"enabled": True}, theme_queue=[1, 2, 3])
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/one")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/two")
        cfg = json.loads((self.channels_dir / "scp-lab.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["image_generation"]["chatgpt_thread_url"], "https://chatgpt.com/c/two")
        self.assertEqual(cfg["autopilot"], {"enabled": True})
        self.assertEqual(cfg["theme_queue"], [1, 2, 3])

    def test_channel_thread_wins_over_default(self):
        self._channel("scp-lab")
        self.bridge.set_thread_url("_default", "https://chatgpt.com/c/default")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp")
        self.assertEqual(self.bridge.thread_url_for("scp-lab"), "https://chatgpt.com/c/scp")
        self.assertEqual(self.bridge.thread_url_for("yokai-watch"), "https://chatgpt.com/c/default")

    def test_default_goes_to_threads_json_when_no_config_exists(self):
        where = self.bridge.set_thread_url("_default", "https://chatgpt.com/c/default")
        self.assertEqual(where, str(self.bridge.THREADS_PATH))

    def test_thread_url_is_stamped_on_the_request(self):
        self._channel("scp-lab")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp")
        self.bridge.request_image("a cat", channel_id="scp-lab")
        self.assertEqual(
            self.bridge.pending_requests()[0]["thread_url"], "https://chatgpt.com/c/scp"
        )

    def test_missing_lists_channels_without_a_thread(self):
        self._channel("scp-lab")
        self._channel("yokai-watch")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp")
        self.assertEqual(self.bridge.channels_missing_thread(), ["yokai-watch"])


class TestQualityLoop(BridgeTestCase):
    """Claude の 生成 → 目視チェック → 修正 のループ。"""

    def _queue(self):
        self.bridge.request_image("a cracked stone tablet", size="1024x1024")
        return self.bridge.pending_requests()[0]["id"]

    def test_first_prompt_is_the_original(self):
        req_id = self._queue()
        self.assertEqual(self.bridge.next_prompt(req_id), "a cracked stone tablet")

    def test_reject_keeps_it_pending_and_switches_to_a_revision_prompt(self):
        req_id = self._queue()
        self.bridge.reject(req_id, "文字が入ってる", revision_prompt="文字を完全に消して")

        self.assertEqual(len(self.bridge.pending_requests()), 1)
        nxt = self.bridge.next_prompt(req_id)
        self.assertIn("文字を完全に消して", nxt)
        self.assertIn("作り直して", nxt)

    def test_revisions_accumulate_in_order(self):
        req_id = self._queue()
        self.bridge.reject(req_id, "文字が入ってる", revision_prompt="文字を消して")
        self.bridge.reject(req_id, "暗すぎる", revision_prompt="もっと明るく")
        nxt = self.bridge.next_prompt(req_id)
        self.assertLess(nxt.index("文字を消して"), nxt.index("もっと明るく"))
        self.assertEqual(len(self.bridge.load_request(req_id)["attempts"]), 2)

    def test_reject_falls_back_to_reason_when_no_revision_given(self):
        req_id = self._queue()
        self.bridge.reject(req_id, "顔が切れてる")
        self.assertIn("顔が切れてる", self.bridge.next_prompt(req_id))

    def test_deliver_records_the_qc_verdict(self):
        req_id = self._queue()
        self.bridge.reject(req_id, "文字が入ってる")
        data = self.bridge.deliver(req_id, self._png(), qc_note="文字なし・下部空きOK")
        verdicts = [a["verdict"] for a in data["attempts"]]
        self.assertEqual(verdicts, ["rejected", "accepted"])
        self.assertEqual(data["qc_note"], "文字なし・下部空きOK")

    def test_reject_on_a_delivered_request_raises(self):
        req_id = self._queue()
        self.bridge.deliver(req_id, self._png())
        with self.assertRaises(KeyError):
            self.bridge.reject(req_id, "やっぱりダメ")


class TestGenerateOrQueue(BridgeTestCase):
    def test_raises_queued_when_undelivered(self):
        with self.assertRaises(self.bridge.Queued) as ctx:
            self.bridge.generate_or_queue("a cat", size="1024x1024")
        self.assertEqual(ctx.exception.req_id, self.bridge.pending_requests()[0]["id"])

    def test_returns_bytes_after_delivery(self):
        try:
            self.bridge.generate_or_queue("a cat", size="1024x1024")
        except self.bridge.Queued as e:
            self.bridge.deliver(e.req_id, self._png())
        self.assertTrue(
            self.bridge.generate_or_queue("a cat", size="1024x1024").startswith(b"\x89PNG")
        )


class TestPolicy(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_TEXT", None)

    def tearDown(self):
        os.environ.pop("OPENAI_TEXT", None)

    def test_there_is_no_image_api_switch_anymore(self):
        """画像の OpenAI API 呼び出しは廃止したので、許可する経路自体が無い。"""
        from pipeline import openai_policy
        self.assertFalse(hasattr(openai_policy, "direct_image_api_allowed"))

    def test_text_api_is_off_when_claude_is_available(self):
        from pipeline import openai_policy
        original = openai_policy.claude_available
        openai_policy.claude_available = lambda: True
        try:
            self.assertFalse(openai_policy.direct_text_api_allowed())
        finally:
            openai_policy.claude_available = original

    def test_text_api_stays_on_while_claude_is_unavailable(self):
        from pipeline import openai_policy
        original = openai_policy.claude_available
        openai_policy.claude_available = lambda: False
        try:
            self.assertTrue(openai_policy.direct_text_api_allowed())
        finally:
            openai_policy.claude_available = original

    def test_openai_text_zero_wins_over_everything(self):
        from pipeline import openai_policy
        original = openai_policy.claude_available
        openai_policy.claude_available = lambda: False
        os.environ["OPENAI_TEXT"] = "0"
        try:
            self.assertFalse(openai_policy.direct_text_api_allowed())
        finally:
            openai_policy.claude_available = original


class TestNoOpenAIImageCalls(unittest.TestCase):
    """画像生成のコードに OpenAI Images API が残っていないことを守る。"""

    def test_pipeline_modules_do_not_reference_the_images_endpoint(self):
        base = Path(__file__).resolve().parents[1] / "pipeline"
        for name in ("video_generator.py", "thumbnail_generator.py"):
            src = (base / name).read_text(encoding="utf-8")
            self.assertNotIn("v1/images/generations", src, f"{name} に画像 API が残っている")


if __name__ == "__main__":
    unittest.main()
