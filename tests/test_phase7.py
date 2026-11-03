"""Run with:  python -m unittest discover -s tests -v"""
import unittest

from bot.services import matcher


def ing(i, name):
    return {"id": i, "name": name, "allergen": None}


def meal(mid, name, ingredients, sold_out=False, conflict=False):
    return {"id": mid, "name": name, "ingredients": ingredients, "sold_out": sold_out, "conflict": conflict}


OATS, BANANA, MILK, CHICKEN, RICE, BROCCOLI, OIL = (ing(i, n) for i, n in enumerate(
    ["Oats", "Banana", "Milk", "Chicken", "Rice", "Broccoli", "Oil"], start=1))

BOWL = meal(1, "Chicken Bowl", [CHICKEN, RICE, BROCCOLI, OIL])
PLATE = meal(2, "Chicken Plate", [CHICKEN, OIL])
OATBOWL = meal(3, "Oats Bowl", [OATS, BANANA, MILK])


class RankTests(unittest.TestCase):
    def test_nothing_picked_gives_nothing(self):
        self.assertEqual(matcher.rank(set(), [BOWL]), [])

    def test_meals_without_any_pick_are_left_out(self):
        result = matcher.rank({4}, [BOWL, PLATE, OATBOWL])
        self.assertEqual([m.meal["id"] for m in result], [2, 1])   # both chicken meals, no oats

    def test_more_of_the_picks_wins(self):
        result = matcher.rank({4, 5, 6}, [PLATE, BOWL])            # chicken, rice, broccoli
        self.assertEqual(result[0].meal["id"], 1)
        self.assertTrue(result[0].missing == ())
        self.assertEqual(result[1].missing, (5, 6))

    def test_fewer_extras_breaks_a_tie(self):
        result = matcher.rank({4}, [BOWL, PLATE])                  # both have chicken only
        self.assertEqual([m.meal["id"] for m in result], [2, 1])   # plate has 1 extra, bowl has 3

    def test_sold_out_comes_after_available(self):
        sold = meal(9, "Perfect But Gone", [CHICKEN, RICE, BROCCOLI], sold_out=True)
        result = matcher.rank({4, 5, 6}, [sold, PLATE])
        self.assertEqual([m.meal["id"] for m in result], [2, 9])

    def test_allergy_conflict_comes_after_clean_meals(self):
        risky = meal(8, "Risky", [CHICKEN, RICE, BROCCOLI], conflict=True)
        result = matcher.rank({4, 5, 6}, [risky, PLATE])
        self.assertEqual([m.meal["id"] for m in result], [2, 8])
        self.assertTrue(result[1].meal["conflict"])

    def test_allergy_beats_sold_out_order(self):
        # available but risky still comes before sold out and clean
        risky = meal(8, "Risky", [CHICKEN], conflict=True)
        gone = meal(9, "Gone", [CHICKEN], sold_out=True)
        self.assertEqual([m.meal["id"] for m in matcher.rank({4}, [gone, risky])], [8, 9])

    def test_limit_and_stable_order(self):
        many = [meal(i, "Meal " + chr(64 + i), [CHICKEN]) for i in range(1, 9)]
        first = matcher.rank({4}, many)
        self.assertEqual(len(first), matcher.MAX_RESULTS)
        self.assertEqual([m.meal["id"] for m in first], [m.meal["id"] for m in matcher.rank({4}, list(reversed(many)))])

    def test_extra_lists_what_was_not_picked(self):
        result = matcher.rank({4}, [PLATE])[0]
        self.assertEqual([e["name"] for e in result.extra], ["Oil"])
        self.assertEqual([h["name"] for h in result.have], ["Chicken"])


class ShortListTests(unittest.TestCase):
    def test_short_and_long(self):
        self.assertEqual(matcher.short_list(["A", "B"]), "A, B")
        self.assertEqual(matcher.short_list(["A", "B", "C", "D", "E", "F"]), "A, B, C, D +2 more")


if __name__ == "__main__":
    unittest.main()
