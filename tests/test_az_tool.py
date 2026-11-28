import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import az_tool
import rebirth_data


class UtilityTests(unittest.TestCase):
    def test_calculate_afk_earnings_from_per_second_income(self):
        self.assertAlmostEqual(az_tool.calculate_afk_earnings(25.4, 10), 254.0)
        self.assertAlmostEqual(az_tool.calculate_afk_earnings(1.5, 60), 90.0)

    def test_calculate_afk_earnings_rejects_nonpositive_income(self):
        for income in (0, -1):
            with self.assertRaises(ValueError):
                az_tool.calculate_afk_earnings(income, 10)

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



    def test_afk_screen_classifier_detects_loading_lobby_and_gameplay(self):
        self.assertEqual(az_tool.classify_afk_screen("Connecting to server..."), "loading")
        self.assertEqual(az_tool.classify_afk_screen("Battle Royale  PLAY  Locker"), "lobby")
        self.assertEqual(az_tool.classify_afk_screen("Gameplay - Health 100"), "gameplay")
        self.assertEqual(az_tool.classify_afk_screen(""), "unknown")

    def test_afk_screen_classifier_does_not_treat_gameplay_as_lobby(self):
        self.assertEqual(az_tool.classify_afk_screen("Gameplay"), "gameplay")

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

    def test_notification_region_is_within_small_display(self):
        monitor = {"left": 0, "top": 0, "width": 800, "height": 600}
        region = az_tool.notification_region(monitor)
        self.assertLess(region["width"], monitor["width"])
        self.assertLess(region["height"], monitor["height"])
        self.assertGreaterEqual(region["left"], 0)
        self.assertGreaterEqual(region["top"], 0)
        self.assertLessEqual(region["left"] + region["width"], 800)
        self.assertLessEqual(region["top"] + region["height"], 600)

    def test_income_to_qi_converts_every_supported_unit(self):
        self.assertEqual(az_tool.income_to_qi(1, "QI"), 1)
        self.assertEqual(az_tool.income_to_qi(1, "SX"), 1000)
        self.assertEqual(az_tool.income_to_qi(1, "SP"), 1000000)
        self.assertEqual(az_tool.income_to_qi(1, "OC"), 1000000000)
        self.assertEqual(az_tool.income_to_qi(1, "NO"), 1000000000000)

    def test_format_money_scales_from_qi_through_no(self):
        self.assertEqual(az_tool.format_money(999), "999.00 QI")
        self.assertEqual(az_tool.format_money(1000), "1.00 SX")
        self.assertEqual(az_tool.format_money(1000000), "1.00 SP")
        self.assertEqual(az_tool.format_money(1000000000), "1.00 OC")
        self.assertEqual(az_tool.format_money(1000000000000), "1.00 NO")



    def test_rebirth_tables_have_complete_user_supplied_ranges(self):
        self.assertEqual(len(rebirth_data.JUMP_COSTS), 96)
        self.assertEqual(len(rebirth_data.REBIRTH_COSTS), 95)
        self.assertEqual(rebirth_data.format_game_money(rebirth_data.REBIRTH_COSTS[-1]), "1.38no")
        self.assertEqual(rebirth_data.parse_game_money("1Qa"), rebirth_data.parse_game_money("1000T"))

    def test_next_rebirth_progresses_to_final_entry(self):
        target, cost, complete = rebirth_data.next_rebirth(0)
        self.assertEqual(target, 1)
        self.assertFalse(complete)
        target, cost, complete = rebirth_data.next_rebirth(rebirth_data.REBIRTH_COSTS[-1])
        self.assertEqual(target, 95)
        self.assertTrue(complete)

    def test_remaining_time_uses_decimal_balance_and_income(self):
        target, cost, seconds = rebirth_data.remaining_time(0, 1)
        self.assertEqual(target, 1)
        self.assertEqual(seconds, rebirth_data.REBIRTH_COSTS[0])

    def test_income_and_format_support_qa(self):
        self.assertEqual(az_tool.income_to_qi(1, "QA"), 0.001)
        self.assertEqual(az_tool.format_money(0.001), "1.00 QA")
        self.assertEqual(az_tool.format_expected_money(0.001), "1qa")

if __name__ == "__main__":
    unittest.main(verbosity=2)
