"""Phone number cleanup for Ethiopian mobile numbers."""
from __future__ import annotations

import re

_CLEAN = re.compile(r"[\s\-().]")
_ETHIOPIAN_MOBILE = re.compile(r"^(?:\+?251|0)?([79]\d{8})$")


def normalize_phone(raw: str | None) -> str | None:
    """Return +2519XXXXXXXX / +2517XXXXXXXX, or None if the text is not a valid mobile number."""
    cleaned = _CLEAN.sub("", raw or "")
    match = _ETHIOPIAN_MOBILE.match(cleaned)
    return f"+251{match.group(1)}" if match else None
