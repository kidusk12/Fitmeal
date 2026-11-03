"""Closest-meal matching for the meal builder (SRS FR-C10). Pure logic: no database, no Telegram.

A customer picks ingredients; every meal on the menu that contains at least one of them is
ranked. Order of the ranking, most important first:

  1. meals that can be ordered today come before meals that are sold out
  2. meals that do not clash with the customer's allergies come before those that might
  3. more of the picked ingredients in the meal is better
  4. fewer ingredients the customer did not ask for is better
  5. name, so the order is always the same
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_RESULTS = 5


@dataclass(frozen=True)
class Match:
    meal: dict
    have: tuple[dict, ...]     # picked ingredients that the meal contains
    missing: tuple[int, ...]   # ids of picked ingredients the meal does not contain
    extra: tuple[dict, ...]    # ingredients in the meal that were not picked

    @property
    def complete(self) -> bool:
        return not self.missing


def rank(selected: set[int], meals: list[dict], limit: int = MAX_RESULTS) -> list[Match]:
    """meals: dicts with id, name, sold_out (bool), conflict (bool) and ingredients ([{id, name}])."""
    if not selected:
        return []
    matches: list[Match] = []
    for meal in meals:
        have = tuple(i for i in meal["ingredients"] if i["id"] in selected)
        if not have:
            continue
        in_meal = {i["id"] for i in meal["ingredients"]}
        missing = tuple(sorted(selected - in_meal))
        extra = tuple(i for i in meal["ingredients"] if i["id"] not in selected)
        matches.append(Match(meal, have, missing, extra))
    matches.sort(
        key=lambda m: (
            bool(m.meal.get("sold_out")),
            bool(m.meal.get("conflict")),
            -len(m.have),
            len(m.extra),
            m.meal["name"].lower(),
            m.meal["id"],
        )
    )
    return matches[:limit]


def short_list(names: list[str], limit: int = 4) -> str:
    """'Egg, Spinach' or 'Egg, Spinach, Avocado, Oil +2 more'."""
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + " +" + str(len(names) - limit) + " more"
