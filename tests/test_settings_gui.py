import unittest

from settings_gui import MIN_INTERVAL_SECONDS, SettingsError, parse_keywords, validate_settings_values


def valid_values(**overrides):
    values = {
        "max_price": "10",
        "min_price": "0",
        "check_interval_seconds": "120",
        "min_stock": "1",
        "fresh_within_minutes": "120",
    }
    values.update(overrides)
    return values


class SettingsGuiTests(unittest.TestCase):
    def test_interval_accepts_official_minimum(self):
        parsed = validate_settings_values(
            valid_values(check_interval_seconds=str(MIN_INTERVAL_SECONDS))
        )
        self.assertEqual(parsed["check_interval_seconds"], 60)

    def test_interval_rejects_less_than_one_minute(self):
        with self.assertRaises(SettingsError):
            validate_settings_values(valid_values(check_interval_seconds="59"))

    def test_rejects_min_price_above_monitor_price(self):
        with self.assertRaises(SettingsError):
            validate_settings_values(valid_values(min_price="11"))

    def test_keyword_parser_deduplicates(self):
        self.assertEqual(parse_keywords("已接码\n质保，已接码"), ["已接码", "质保"])


if __name__ == "__main__":
    unittest.main()
