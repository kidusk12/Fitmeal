"""Run with:  python -m unittest discover -s tests -v"""
import ast
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.services import owner_rules as r

TZ = ZoneInfo("Africa/Addis_Ababa")


class SettingTests(unittest.TestCase):
    def test_whole_numbers_in_range(self):
        self.assertEqual(r.parse_setting("delivery_fee_etb", "75"), "75")
        self.assertEqual(r.parse_setting("delivery_fee_etb", "0"), "0")
        self.assertIsNone(r.parse_setting("delivery_fee_etb", "-5"))
        self.assertIsNone(r.parse_setting("delivery_fee_etb", "5001"))
        self.assertIsNone(r.parse_setting("delivery_fee_etb", "abc"))
        self.assertIsNone(r.parse_setting("delivery_fee_etb", "7.5"))

    def test_limits_and_windows_must_be_at_least_one(self):
        for key in ("daily_order_limit", "payment_window_min", "kitchen_review_min", "alert_repeat_min"):
            self.assertIsNone(r.parse_setting(key, "0"), key)
            self.assertEqual(r.parse_setting(key, "1"), "1", key)

    def test_times(self):
        self.assertEqual(r.parse_setting("opening_time", "8:00"), "08:00")
        self.assertEqual(r.parse_setting("closing_time", "21.30"), "21:30")
        self.assertIsNone(r.parse_setting("opening_time", "24:00"))
        self.assertIsNone(r.parse_setting("opening_time", "8"))
        self.assertIsNone(r.parse_setting("opening_time", "08:60"))

    def test_unknown_key_is_refused(self):
        self.assertIsNone(r.parse_setting("business_name", "x"))


class MealInputTests(unittest.TestCase):
    def test_macros(self):
        self.assertEqual(r.parse_macros("420 28 55 10"), (420, Decimal("28.0"), Decimal("55.0"), Decimal("10.0")))
        self.assertEqual(r.parse_macros("90 1 20 0.5")[3], Decimal("0.5"))
        self.assertEqual(r.parse_macros("90 1,5 20 0.5")[1], Decimal("1.5"))
        self.assertIsNone(r.parse_macros("420 28 55"))
        self.assertIsNone(r.parse_macros("420 28 55 10 9"))
        self.assertIsNone(r.parse_macros("abc 1 2 3"))
        self.assertIsNone(r.parse_macros("9000 1 2 3"))
        self.assertIsNone(r.parse_macros("100 -1 2 3"))

    def test_price(self):
        self.assertEqual(r.parse_price("180"), 180)
        self.assertIsNone(r.parse_price("0"))
        self.assertIsNone(r.parse_price("12.5"))
        self.assertIsNone(r.parse_price("free"))

    def test_optional_text(self):
        self.assertEqual(r.parse_optional_text("-", 300), "")
        self.assertEqual(r.parse_optional_text("  Fresh  and   tasty ", 300), "Fresh and tasty")
        self.assertIs(r.parse_optional_text("x" * 301, 300), False)
        self.assertIs(r.parse_optional_text("   ", 300), False)

    def test_ingredients(self):
        items, error = r.parse_ingredients("Chicken breast 150g, egg 3, Olive oil 5 ml\nRice 1.5")
        self.assertIsNone(error)
        self.assertEqual([i[0] for i in items], ["Chicken breast", "Egg", "Olive oil", "Rice"])
        self.assertEqual(items[0][1:], (Decimal("150.00"), "g"))
        self.assertEqual(items[1][1:], (Decimal("3.00"), None))
        self.assertEqual(items[2][2], "ml")
        self.assertEqual(items[3][1], Decimal("1.50"))

    def test_ingredient_errors(self):
        self.assertEqual(r.parse_ingredients("")[1], "empty")
        self.assertEqual(r.parse_ingredients("Lettuce")[1], "format")
        self.assertEqual(r.parse_ingredients("Rice 0")[1], "qty")
        self.assertEqual(r.parse_ingredients("Rice 5, rice 6")[1], "dup")
        self.assertEqual(r.parse_ingredients("5 5")[1], "name")
        self.assertEqual(r.parse_ingredients(",".join(f"Item{chr(97 + i)} 1" for i in range(21)))[1], "toomany")

    def test_meal_code(self):
        self.assertEqual(r.next_meal_code(0), "M-001")
        self.assertEqual(r.next_meal_code(9), "M-010")
        self.assertEqual(r.next_meal_code(999), "M-1000")


class PeopleInputTests(unittest.TestCase):
    def test_telegram_id(self):
        self.assertEqual(r.parse_telegram_id(" 123456789 "), 123456789)
        self.assertIsNone(r.parse_telegram_id("12ab"))
        self.assertIsNone(r.parse_telegram_id("123"))
        self.assertIsNone(r.parse_telegram_id("@name"))

    def test_names(self):
        self.assertEqual(r.parse_name("  Abel   T  "), "Abel T")
        self.assertIsNone(r.parse_name("A"))
        self.assertIsNone(r.parse_name("x" * 61))

    def test_phone_list(self):
        valid, bad = r.normalize_phones("0911223344, +251922334455\n0933445566 0944556677")
        self.assertEqual(valid, ["+251911223344", "+251922334455", "+251933445566", "+251944556677"])
        self.assertEqual(bad, [])
        valid, bad = r.normalize_phones("0911223344, nope, 0911223344")
        self.assertEqual(valid, ["+251911223344"])
        self.assertEqual(bad, ["nope"])


class ReportPeriodTests(unittest.TestCase):
    NOW = datetime(2026, 11, 3, 15, 20, tzinfo=TZ)

    def test_today(self):
        start, end = r.period_bounds(self.NOW, "today")
        self.assertEqual((start.day, start.hour, end.day), (3, 0, 4))

    def test_yesterday(self):
        start, end = r.period_bounds(self.NOW, "yesterday")
        self.assertEqual((start.day, end.day), (2, 3))

    def test_week_is_seven_days_including_today(self):
        start, end = r.period_bounds(self.NOW, "week")
        self.assertEqual((end - start).days, 7)
        self.assertEqual((start.day, end.day), (28 - 0, 4))  # 28 Oct to 3 Nov

    def test_unknown_period(self):
        self.assertIsNone(r.period_bounds(self.NOW, "decade"))

    def test_revenue_statuses_exclude_refunds_and_unpaid(self):
        for status in ("refunded", "refund_needed", "expired", "cancelled", "payment_review", "payment_denied", "awaiting_payment"):
            self.assertNotIn(status, r.CONFIRMED_STATUSES)
        self.assertIn("delivered", r.CONFIRMED_STATUSES)


class TextsGuardTests(unittest.TestCase):
    def test_no_message_name_is_defined_twice(self):
        """A second definition silently replaces the first (this once broke the signup error message)."""
        source = (Path(__file__).resolve().parent.parent / "bot" / "texts.py").read_text(encoding="utf-8")
        seen, repeated = set(), []
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id in seen:
                            repeated.append(target.id)
                        seen.add(target.id)
        self.assertEqual(repeated, [])


if __name__ == "__main__":
    unittest.main()
