"""Matches a customer's allergy text against a meal's ingredients (conservative: warns when unsure)."""
from __future__ import annotations

import re

# Words that mean "no allergies"
NONE_WORDS = {
    "none", "no", "nothing", "na", "nil", "known", "allergies", "allergy",
    "any", "have", "i", "dont", "don", "t", "not",
}
# Filler words that should never be matched against ingredient names
STOP_WORDS = {"allergic", "food", "foods", "with", "from", "very", "also", "some", "and", "the"}
# Everyday words mapped to the allergen tags stored on ingredients
SYNONYMS = {
    "milk": "dairy", "lactose": "dairy", "dairy": "dairy", "cheese": "dairy", "yogurt": "dairy",
    "yoghurt": "dairy", "whey": "dairy", "butter": "dairy",
    "egg": "egg", "eggs": "egg",
    "peanut": "peanut", "peanuts": "peanut", "nut": "peanut", "nuts": "peanut",
    "gluten": "gluten", "wheat": "gluten", "bread": "gluten",
}


def _words(text: str | None) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def has_allergies(text: str | None) -> bool:
    words = _words(text)
    return bool(words) and not all(w in NONE_WORDS for w in words)


def find_conflicts(allergies_text: str | None, ingredients: list[dict]) -> list[str]:
    """Return the names of ingredients that may conflict with the allergy text."""
    if not has_allergies(allergies_text):
        return []
    words = [w for w in _words(allergies_text) if w not in NONE_WORDS]
    tags = {SYNONYMS[w] for w in words if w in SYNONYMS}
    terms = {w.rstrip("s") for w in words if len(w) >= 4 and w not in STOP_WORDS}
    hits: list[str] = []
    for ing in ingredients:
        name = ing["name"].lower()
        allergen = (ing.get("allergen") or "").lower()
        if (allergen and allergen in tags) or any(term in name for term in terms):
            hits.append(ing["name"])
    return hits
