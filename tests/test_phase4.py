"""Run with:  python -m unittest discover -s tests -v"""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bot.services import rules

ADDIS = ZoneInfo("Africa/Addis_Ababa")


class AlertKindTests(unittest.TestCase):
    def test_reminders_then_overdue(self):
        # kitchen has 30 minutes; alerts every 10: 10 and 20 are reminders, 30 is overdue (FR-P4)
        self.assertEqual(rules.alert_kind(10.2, 30), "reminder")
        self.assertEqual(rules.alert_kind(20.1, 30), "reminder")
        self.assertEqual(rules.alert_kind(30.0, 30), "overdue")
        self.assertEqual(rules.alert_kind(40.5, 30), "overdue")

    def test_shortened_test_timers(self):
        self.assertEqual(rules.alert_kind(1.0, 3), "reminder")
        self.assertEqual(rules.alert_kind(3.0, 3), "overdue")


class ClockTests(unittest.TestCase):
    def test_shows_addis_time_not_utc(self):
        utc = datetime(2026, 10, 31, 11, 32, tzinfo=timezone.utc)
        self.assertEqual(rules.clock(utc, ADDIS), "14:32")


if __name__ == "__main__":
    unittest.main()
