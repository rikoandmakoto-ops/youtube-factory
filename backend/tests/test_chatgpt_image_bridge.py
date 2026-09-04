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
        self._prev = os.environ.get("IMAGE_BRIDGE_DIR")
        os.environ["IMAGE_BRIDGE_DIR"] = self._tmp.name
        from pipeline import chatgpt_image_bridge
        self.bridge = importlib.reload(chatgpt_image_bridge)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("IMAGE_BRIDGE_DIR", None)
        else:
            os.environ["IMAGE_BRIDGE_DIR"] = self._prev
        self._tmp.cleanup()
        from pipeline import chatgpt_image_bridge
        importlib.reload(chatgpt_image_bridge)

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
    def test_channel_thread_wins_over_default(self):
        self.bridge.set_thread_url("_default", "https://chatgpt.com/c/default")
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp")
        self.assertEqual(self.bridge.thread_url_for("scp-lab"), "https://chatgpt.com/c/scp")
        self.assertEqual(self.bridge.thread_url_for("yokai-watch"), "https://chatgpt.com/c/default")

    def test_thread_url_is_stamped_on_the_request(self):
        self.bridge.set_thread_url("scp-lab", "https://chatgpt.com/c/scp")
        self.bridge.request_image("a cat", channel_id="scp-lab")
        self.assertEqual(
            self.bridge.pending_requests()[0]["thread_url"], "https://chatgpt.com/c/scp"
        )


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
    def test_image_api_blocked_while_bridge_is_on(self):
        from pipeline import openai_policy
        os.environ.pop("OPENAI_IMAGE", None)
        os.environ.pop("IMAGE_BRIDGE", None)
        self.assertFalse(openai_policy.direct_image_api_allowed())

    def test_image_api_allowed_when_bridge_is_off(self):
        from pipeline import chatgpt_image_bridge, openai_policy
        os.environ["IMAGE_BRIDGE"] = "0"
        try:
            importlib.reload(chatgpt_image_bridge)
            self.assertTrue(openai_policy.direct_image_api_allowed())
        finally:
            os.environ.pop("IMAGE_BRIDGE", None)
            importlib.reload(chatgpt_image_bridge)


if __name__ == "__main__":
    unittest.main()
