from __future__ import annotations

import hashlib
import re
import unicodedata

from unidecode import unidecode

_MAX_LEN = 60
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def make_slug(title: str) -> str:
    """Deterministically turn a title into an ASCII filename slug.

    - NFKD normalize, drop combining marks
    - unidecode transliteration (UK/RU -> ASCII)
    - lowercase
    - collapse non-alphanumerics into single dashes
    - strip leading/trailing dashes
    - truncate to 60 chars at last dash boundary
    - empty -> "untitled-<8 hex of original>"
    """
    decomposed = unicodedata.normalize("NFKD", title)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_form = unidecode(stripped).lower()
    collapsed = _NON_ALNUM.sub("-", ascii_form).strip("-")

    if not collapsed:
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
        return f"untitled-{digest}"

    if len(collapsed) <= _MAX_LEN:
        return collapsed

    head = collapsed[:_MAX_LEN]
    last_dash = head.rfind("-")
    if last_dash > 0:
        head = head[:last_dash]
    return head.strip("-")
