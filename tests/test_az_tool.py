import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import az_tool


class UtilityTests(unittest.TestCase):
    def test_device_id_is_stable_for_same_environment(self):
        with patch.dict(os.environ, {
            "COMPUTERNAME": "TEST-PC",
            "PROCESSOR_IDENTIFIER": "TEST-CPU",
            "USERNAME": "tester",
        }, clear=False):
            first = az_tool.device_id()
            second = az_tool.device_id()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in first))

    def test_parse_expiry_normalizes_utc(self):
        parsed = az_tool.parse_expiry("2030-01-02T03:04:05Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed, datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc))

    def test_parse_expiry_rejects_invalid_values(self):
        self.assertIsNone(az_tool.parse_expiry(""))
        self.assertIsNone(az_tool.parse_expiry("not-a-date"))

    def test_load_state_returns_empty_dict_for_missing_or_invalid_file(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = os.path.join(folder, "state.json")
            with patch.object(az_tool, "STATE_FILE", state_path):
                self.assertEqual(az_tool.load_state(), {})
                with open(state_path, "w", encoding="utf-8") as stream:
                    stream.write("{broken")
                self.assertEqual(az_tool.load_state(), {})

    def test_save_state_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = os.path.join(folder, "state.json")
            with patch.object(az_tool, "STATE_FILE", state_path), patch.object(az_tool, "APP_DIR", folder):
                expected = {"license_key": "TEST-KEY", "discord_id": "12345678901234567"}
                az_tool.save_state(expected)
                self.assertEqual(az_tool.load_state(), expected)
                self.assertFalse(os.path.exists(state_path + ".tmp"))

    def test_arabic_error_maps_common_server_responses(self):
        self.assertIn("منتهي", az_tool.arabic_error("license expired"))
        self.assertIn("غير صالح", az_tool.arabic_error("invalid license"))
        self.assertIn("تعذر الاتصال", az_tool.arabic_error("Cannot reach license server"))



    def test_notification_region_is_compact_and_clamped(self):
        monitor = {"left": 100, "top": 50, "width": 1920, "height": 1080}
        region = az_tool.notification_region(monitor)
        self.assertEqual(region["width"], int(1920 * 0.48))
        self.assertEqual(region["height"], int(1080 * 0.16))
        self.assertGreaterEqual(region["left"], monitor["left"])
        self.assertGreaterEqual(region["top"], monitor["top"])
        self.assertLessEqual(region["left"] + region["width"], monitor["left"] + monitor["width"])
        self.assertLessEqual(region["top"] + region["height"], monitor["top"] + monitor["height"])

    def test_runtime_base_dir_returns_source_directory_without_nuitka(self):
        self.assertEqual(az_tool.runtime_base_dir(), os.path.dirname(os.path.abspath(az_tool.__file__)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
