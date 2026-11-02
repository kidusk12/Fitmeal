"""Run with:  python -m unittest discover -s tests -v"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.services import flow

TZ = ZoneInfo("Africa/Addis_Ababa")


class StatusFlowTests(unittest.TestCase):
    def test_one_step_at_a_time(self):
        self.assertEqual(flow.next_status("confirmed"), "preparing")
        self.assertEqual(flow.next_status("preparing"), "ready")
        self.assertEqual(flow.next_status("ready"), "out_for_delivery")
        self.assertEqual(flow.next_status("out_for_delivery"), "delivered")

    def test_no_next_step_outside_the_kitchen_flow(self):
        for status in ("delivered", "payment_review", "awaiting_payment", "expired", "refund_needed", "refunded"):
            self.assertIsNone(flow.next_status(status), status)

    def test_cannot_skip_steps(self):
        self.assertEqual(flow.previous_status("ready"), "preparing")
        self.assertEqual(flow.previous_status("delivered"), "out_for_delivery")
        self.assertIsNone(flow.previous_status("confirmed"))  # approval is not a status button
        self.assertIsNone(flow.previous_status("refunded"))

    def test_kitchen_can_cancel_only_before_delivery(self):
        self.assertEqual(flow.CANCELLABLE_BY_KITCHEN, ("confirmed", "preparing", "ready"))


class DeliveryTimeTests(unittest.TestCase):
    NOW = datetime(2026, 11, 1, 14, 30, 45, tzinfo=TZ)

    def test_valid_times(self):
        self.assertEqual(flow.parse_delivery_time("17:30", self.NOW), datetime(2026, 11, 1, 17, 30, tzinfo=TZ))
        self.assertEqual(flow.parse_delivery_time(" 9.05 ", datetime(2026, 11, 1, 8, 0, tzinfo=TZ)), datetime(2026, 11, 1, 9, 5, tzinfo=TZ))

    def test_past_or_invalid(self):
        for text in ("14:30", "09:00", "25:00", "12:75", "tomorrow", "1730", "", None):
            self.assertIsNone(flow.parse_delivery_time(text, self.NOW), text)

    def test_quick_buttons(self):
        self.assertEqual(flow.in_minutes(self.NOW, 45), datetime(2026, 11, 1, 15, 15, tzinfo=TZ))
        self.assertEqual(flow.QUICK_MINUTES, (30, 45, 60))


if __name__ == "__main__":
    unittest.main()
