"""Pure text-similarity helpers for the ontology scanner.

Phase B3a of the Ontology Scanner V1 plan. No I/O, no LLM — used to build a
shortlist of duplicate/merge candidates before sending pairs to the LLM
validator (Phase B3c).

Functions:
- ``normalize_body``: case + whitespace fold, so semantically equal bodies
  hash to the same string.
- ``body_hash``: SHA-256 of normalized body — used to detect 100% duplicates.
- ``tokenize_for_similarity``: extract a word set for Jaccard. Drops short
  noise tokens (length ≤ 2).
- ``jaccard_similarity``: standard |A ∩ B| / |A ∪ B|, with empty-set
  conventions for edge cases.
"""

from __future__ import annotations

import hashlib
import re

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁіїґєІЇҐЄ0-9]+")
_MIN_TOKEN_LEN = 3


def normalize_body(text: str) -> str:
    """Lower-case + collapse whitespace + strip edges.

    Two bodies that differ only in indentation, line breaks, or case will
    normalize to the same string — exactly what we want for "are these
    pages identical?" comparison.
    """
    return " ".join(text.lower().split())


def body_hash(text: str) -> str:
    """SHA-256 of the normalized body. Hex string of length 64."""
    return hashlib.sha256(normalize_body(text).encode("utf-8")).hexdigest()


def tokenize_for_similarity(text: str) -> set[str]:
    """Extract a set of useful word tokens from text.

    - Matches latin + cyrillic alphanumerics (Russian / Ukrainian friendly)
    - Lower-cases
    - Drops tokens of length ≤ 2 (articles, prepositions — noise in similarity)
    - Returns a set (de-duplicated by construction)
    """
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= _MIN_TOKEN_LEN
    }


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard coefficient |A ∩ B| / |A ∪ B|.

    Edge cases:
    - Both empty → 1.0 (no disagreement). Used when comparing two
      empty / whitespace-only bodies.
    - Exactly one empty → 0.0.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union
