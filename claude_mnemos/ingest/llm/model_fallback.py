"""Model-not-found detection shared by the CLI and API providers.

When the configured model id is rejected by the provider (Anthropic retires
an old id, or the user typed a wrong one), both providers surface it as text:
- API SDK: an ``anthropic.NotFoundError`` (HTTP 404) whose body contains the
  ``not_found_error`` type.
- CLI (``claude -p``): the same error passes through to stderr verbatim.

``looks_like_model_not_found`` pattern-matches that text so the caller can
retry once with ``config.fallback_model``. Kept import-free (no dependency on
the llm package) so both ``api`` and ``cli`` can import it without a cycle.
"""

from __future__ import annotations

import re

# Anthropic's own error type string is the strongest signal; the natural-
# language variants cover CLI wrappers that reformat the message. In the
# extraction code path the only 404-able resource is the model, so matching
# `not_found_error` here is safe.
_MODEL_NOT_FOUND_RE = re.compile(
    r"not_found_error"
    r"|model[^\n]{0,60}?(not\s+found|does\s+not\s+exist|is\s+not\s+supported"
    r"|unknown|invalid|not\s+available)"
    r"|(unknown|invalid|unsupported)[^\n]{0,20}model",
    re.IGNORECASE,
)


def looks_like_model_not_found(text: str | None) -> bool:
    """True if *text* reads like a 'model does not exist' provider error."""
    if not text:
        return False
    return bool(_MODEL_NOT_FOUND_RE.search(text))
