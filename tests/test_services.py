"""Run with:  python -m unittest discover -s tests -v"""
import unittest

from bot.services.allergy import find_conflicts, has_allergies
from bot.services.phone import normalize_phone

SHAKE = [
    {"name": "Whey protein", "allergen": "dairy"},
    {"name": "Milk", "allergen": "dairy"},
    {"name": "Banana", "allergen": None},
    {"name": "Peanut butter", "allergen": "peanut"},
]


class PhoneTests(unittest.TestCase):
    def test_valid_formats(self):
        for raw in ("0911223344", "+251911223344", "251 911 22 33 44", "911223344", "0711-223-344"):
            self.assertIsNotNone(normalize_phone(raw), raw)
        self.assertEqual(normalize_phone("0911223344"), "+251911223344")
        self.assertEqual(normalize_phone("0711223344"), "+251711223344")

    def test_invalid(self):
        for raw in ("", "abc", "0123", "09112233", "09112233445", None):
            self.assertIsNone(normalize_phone(raw), raw)


class AllergyTests(unittest.TestCase):
    def test_none_means_no_allergies(self):
        for text in ("None", "no", "No known allergies", "I don't have any allergies", "", None):
            self.assertFalse(has_allergies(text), text)
            self.assertEqual(find_conflicts(text, SHAKE), [])

    def test_dairy(self):
        self.assertEqual(find_conflicts("dairy", SHAKE), ["Whey protein", "Milk"])

    def test_synonym_and_plural(self):
        self.assertEqual(find_conflicts("peanuts", SHAKE), ["Peanut butter"])
        self.assertEqual(find_conflicts("lactose", SHAKE), ["Whey protein", "Milk"])

    def test_ingredient_name(self):
        self.assertEqual(find_conflicts("bananas, shellfish", SHAKE), ["Banana"])

    def test_no_false_alarm(self):
        self.assertEqual(find_conflicts("shellfish", SHAKE), [])


if __name__ == "__main__":
    unittest.main()
