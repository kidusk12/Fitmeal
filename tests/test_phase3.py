"""Run with:  python -m unittest discover -s tests -v"""
import asyncio
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from bot.services import location, rules

ADDIS = ZoneInfo("Africa/Addis_Ababa")


class OrderCodeTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(rules.order_code(date(2026, 10, 30), 7), "FIT-261030-007")
        self.assertEqual(rules.order_code(date(2026, 1, 5), 123), "FIT-260105-123")

    def test_more_than_999_still_works(self):
        self.assertEqual(rules.order_code(date(2026, 10, 30), 1042), "FIT-261030-1042")


class OpeningHoursTests(unittest.TestCase):
    def test_normal_day(self):
        opens, closes = time(8, 0), time(21, 0)
        self.assertTrue(rules.is_open(time(8, 0), opens, closes))
        self.assertTrue(rules.is_open(time(20, 59), opens, closes))
        self.assertFalse(rules.is_open(time(21, 0), opens, closes))
        self.assertFalse(rules.is_open(time(7, 59), opens, closes))

    def test_closing_after_midnight(self):
        opens, closes = time(18, 0), time(2, 0)
        self.assertTrue(rules.is_open(time(23, 30), opens, closes))
        self.assertTrue(rules.is_open(time(1, 0), opens, closes))
        self.assertFalse(rules.is_open(time(12, 0), opens, closes))

    def test_same_time_means_always_open(self):
        self.assertTrue(rules.is_open(time(3, 0), time(0, 0), time(0, 0)))

    def test_parse(self):
        self.assertEqual(rules.parse_hhmm("08:30", time(1, 0)), time(8, 30))
        self.assertEqual(rules.parse_hhmm(" 9:05 ", time(1, 0)), time(9, 5))
        for bad in (None, "", "abc", "25:00", "8"):
            self.assertEqual(rules.parse_hhmm(bad, time(1, 0)), time(1, 0), bad)


class DayBoundsTests(unittest.TestCase):
    def test_addis_day_not_server_day(self):
        now = datetime(2026, 10, 30, 23, 30, tzinfo=ADDIS)
        start, end = rules.day_bounds(now)
        self.assertEqual(start, datetime(2026, 10, 30, 0, 0, tzinfo=ADDIS))
        self.assertEqual(end, datetime(2026, 10, 31, 0, 0, tzinfo=ADDIS))
        # 23:30 in Addis is 20:30 UTC: still inside the same Addis day
        self.assertTrue(start <= now < end)


class MapsLinkTests(unittest.TestCase):
    def test_link_format(self):
        self.assertEqual(location.maps_link(9.0123456, 38.7654321), "https://www.google.com/maps?q=9.012346,38.765432")

    def test_pin_beats_map_centre(self):
        url = "https://www.google.com/maps/place/Edna+Mall/@9.0000,38.0000,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d9.0123456!4d38.7654321"
        self.assertEqual(location.parse_coordinates(url), (9.0123456, 38.7654321))

    def test_at_form(self):
        url = "https://www.google.com/maps/@9.0192,38.7525,15z"
        self.assertEqual(location.parse_coordinates(url), (9.0192, 38.7525))

    def test_query_forms(self):
        self.assertEqual(location.parse_coordinates("https://www.google.com/maps?q=9.03,38.74"), (9.03, 38.74))
        self.assertEqual(location.parse_coordinates("https://maps.google.com/?ll=9.03,38.74&z=15"), (9.03, 38.74))
        self.assertEqual(location.parse_coordinates("https://www.google.com/maps?q=9.03%2C38.74"), (9.03, 38.74))

    def test_negative_coordinates(self):
        self.assertEqual(location.parse_coordinates("https://www.google.com/maps/@-1.2921,36.8219,12z"), (-1.2921, 36.8219))

    def test_out_of_range_rejected(self):
        self.assertIsNone(location.parse_coordinates("https://www.google.com/maps?q=95.5,38.74"))

    def test_place_name_only_has_no_coordinates(self):
        self.assertIsNone(location.parse_coordinates("https://www.google.com/maps/place/Edna+Mall"))

    def test_find_url(self):
        self.assertEqual(
            location.find_url("deliver here https://maps.app.goo.gl/AbC123, thanks"),
            "https://maps.app.goo.gl/AbC123",
        )
        self.assertIsNone(location.find_url("Bole, near Edna Mall"))

    def test_only_google_links_accepted(self):
        self.assertTrue(location.is_google_maps_link("https://maps.app.goo.gl/AbC123"))
        self.assertTrue(location.is_google_maps_link("https://www.google.com/maps?q=9.03,38.74"))
        self.assertFalse(location.is_google_maps_link("https://evil.example.com/?q=9.03,38.74"))
        self.assertFalse(location.is_google_maps_link("https://notgoogle.com/maps?q=9.03,38.74"))

    def test_full_link_needs_no_network(self):
        result = asyncio.run(location.coordinates_from_link("https://www.google.com/maps?q=9.03,38.74"))
        self.assertEqual(result, (9.03, 38.74))

    def test_foreign_link_is_refused_without_network(self):
        self.assertIsNone(asyncio.run(location.coordinates_from_link("https://evil.example.com/?q=9.03,38.74")))


if __name__ == "__main__":
    unittest.main()
