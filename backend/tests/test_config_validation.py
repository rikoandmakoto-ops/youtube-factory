"""channels.config_validation の単体テスト。

pytest 未導入の環境でも動くよう標準ライブラリ unittest で記述。

実行方法（backend/ ディレクトリから）:
    python3 -m unittest tests.test_config_validation -v

過去の事故（scp-lab の default_privacy=private 放置で自動投稿が全部非公開）を
二度と起こさないための回帰テスト。
"""

import os
import sys
import unittest

# backend/ を import パスに追加（tests/ の1つ上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from channels.config_validation import (  # noqa: E402
    validate_channel_config,
    validate_channels,
    summarize,
    get_default_privacy,
    is_autopilot_enabled,
    LEVEL_ERROR,
    LEVEL_WARNING,
)


def _channel(autopilot_enabled=False, privacy="public", cid="test-ch"):
    """テスト用の最小チャンネル raw dict を組み立てる。"""
    raw = {
        "id": cid,
        "name": "Test Channel",
        "publish_settings": {"default_privacy": privacy},
        "autopilot": {"enabled": autopilot_enabled},
    }
    return raw


class TestHelpers(unittest.TestCase):
    def test_default_privacy_present(self):
        self.assertEqual(get_default_privacy(_channel(privacy="unlisted")), "unlisted")

    def test_default_privacy_missing_falls_back_to_public(self):
        self.assertEqual(get_default_privacy({}), "public")
        self.assertEqual(get_default_privacy({"publish_settings": {}}), "public")

    def test_default_privacy_null_falls_back_to_public(self):
        self.assertEqual(
            get_default_privacy({"publish_settings": {"default_privacy": None}}),
            "public",
        )

    def test_is_autopilot_enabled(self):
        self.assertTrue(is_autopilot_enabled(_channel(autopilot_enabled=True)))
        self.assertFalse(is_autopilot_enabled(_channel(autopilot_enabled=False)))
        self.assertFalse(is_autopilot_enabled({}))


class TestValidateChannelConfig(unittest.TestCase):
    def test_public_autopilot_is_clean(self):
        """正常系: フルオート有効 × public は問題なし。"""
        issues = validate_channel_config(_channel(autopilot_enabled=True, privacy="public"))
        self.assertEqual(issues, [])

    def test_private_without_autopilot_is_clean(self):
        """フルオート無効なら private でも問題視しない（手動運用の自由）。"""
        issues = validate_channel_config(_channel(autopilot_enabled=False, privacy="private"))
        self.assertEqual(issues, [])

    def test_autopilot_private_is_error(self):
        """これが過去の事故ケース: フルオート有効 × private は ERROR。"""
        issues = validate_channel_config(_channel(autopilot_enabled=True, privacy="private"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "autopilot_private")
        self.assertEqual(issues[0].level, LEVEL_ERROR)
        self.assertTrue(issues[0].is_error)
        self.assertEqual(issues[0].field, "publish_settings.default_privacy")

    def test_autopilot_unlisted_is_warning(self):
        """フルオート有効 × unlisted は WARNING（意図確認）。"""
        issues = validate_channel_config(_channel(autopilot_enabled=True, privacy="unlisted"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "autopilot_unlisted")
        self.assertEqual(issues[0].level, LEVEL_WARNING)
        self.assertFalse(issues[0].is_error)

    def test_invalid_privacy_value_is_error(self):
        """privacy 値そのものが不正なら ERROR。"""
        issues = validate_channel_config(_channel(autopilot_enabled=True, privacy="bogus"))
        codes = [i.code for i in issues]
        self.assertIn("invalid_privacy", codes)
        # 不正値のときは組み合わせ判定はスキップ（誤検知防止）
        self.assertNotIn("autopilot_private", codes)

    def test_channel_id_inferred_from_raw(self):
        issues = validate_channel_config(_channel(autopilot_enabled=True, privacy="private", cid="scp-lab"))
        self.assertEqual(issues[0].channel_id, "scp-lab")

    def test_channel_id_override(self):
        issues = validate_channel_config(
            _channel(autopilot_enabled=True, privacy="private"), channel_id="override-id"
        )
        self.assertEqual(issues[0].channel_id, "override-id")

    def test_missing_publish_settings_defaults_public(self):
        """publish_settings 欠損 = public 扱いなのでフルオート有効でもクリーン。"""
        raw = {"id": "x", "autopilot": {"enabled": True}}
        self.assertEqual(validate_channel_config(raw), [])


class TestValidateChannels(unittest.TestCase):
    def test_mixed_channels(self):
        raws = [
            _channel(autopilot_enabled=True, privacy="public", cid="ok"),
            _channel(autopilot_enabled=True, privacy="private", cid="bad"),
            _channel(autopilot_enabled=True, privacy="unlisted", cid="warn"),
        ]
        issues = validate_channels(raws)
        self.assertEqual(len(issues), 2)
        by_channel = {i.channel_id: i for i in issues}
        self.assertEqual(by_channel["bad"].level, LEVEL_ERROR)
        self.assertEqual(by_channel["warn"].level, LEVEL_WARNING)


class TestSummarize(unittest.TestCase):
    def test_summarize_clean(self):
        s = summarize([])
        self.assertTrue(s["ok"])
        self.assertEqual(s["error_count"], 0)
        self.assertEqual(s["warning_count"], 0)
        self.assertEqual(s["issues"], [])

    def test_summarize_with_error(self):
        issues = validate_channels([
            _channel(autopilot_enabled=True, privacy="private", cid="bad"),
            _channel(autopilot_enabled=True, privacy="unlisted", cid="warn"),
        ])
        s = summarize(issues)
        self.assertFalse(s["ok"])
        self.assertEqual(s["error_count"], 1)
        self.assertEqual(s["warning_count"], 1)
        self.assertEqual(len(s["issues"]), 2)


class TestRealChannelConfigs(unittest.TestCase):
    """実際の data/channels/*.json が整合的であることを確認（要件5の常時保証）。"""

    def _load_all(self):
        import glob
        import json

        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "channels",
        )
        raws = []
        for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
            with open(path, encoding="utf-8") as f:
                raws.append(json.load(f))
        return raws

    def test_no_config_errors_in_real_channels(self):
        raws = self._load_all()
        self.assertTrue(raws, "data/channels/*.json が見つからない")
        issues = validate_channels(raws)
        errors = [i for i in issues if i.is_error]
        msg = "\n".join(f"[{i.channel_id}] {i.message}" for i in errors)
        self.assertEqual(errors, [], f"設定エラーあり:\n{msg}")

    def test_daily_science_and_scp_lab_are_public(self):
        raws = {r.get("id"): r for r in self._load_all()}
        for cid in ("daily-science", "scp-lab"):
            self.assertIn(cid, raws, f"{cid} の設定が見つからない")
            self.assertEqual(
                get_default_privacy(raws[cid]),
                "public",
                f"{cid} の default_privacy が public ではない",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
