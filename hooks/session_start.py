"""SessionStart hook for claude-mnemos plugin (Plan #13c).

When Claude Code starts a session, this hook resolves the cwd → project
via ``ProjectResolver``, calls ``build_adaptive_context`` to assemble a
relevant-pages markdown block, and emits it to stdout as JSON for Claude
Code to inject into the model's system prompt.

Output shape (Claude Code v1 contract):
    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<markdown>"}}

Skip conditions (silent, exit 0, no stdout):
- Recursion guard (``MNEMOS_INJECT_RUNNING=1``)
- Source field is ``resume``, ``compact``, or ``edit``
- Invalid stdin payload
- cwd missing or not in any project
- ``build_adaptive_context`` returns empty string
- Any exception during build (logged to ``~/.claude-mnemos/inject.log``)

Hook never blocks: returns 0 unconditionally.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Hook lives outside the package; allow it to import claude_mnemos.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

RECURSION_ENV = "MNEMOS_INJECT_RUNNING"
# SessionStart payload `source` field — sources we silently skip:
#   resume:  Claude is restoring an existing session; it already has prior
#            context (re-injecting would duplicate).
#   compact: Claude just ran context compaction; injecting would undo what
#            the user asked for.
#   edit:    PostToolUse-triggered partial source — not a fresh session, the
#            model is mid-flight and any inject would land in an unpredictable
#            position.
SKIP_SOURCES = frozenset({"resume", "compact", "edit"})
DEFAULT_MAX_CHARS = 40_000


def _log(msg: str) -> None:
    """Append a line to ~/.claude-mnemos/inject.log. Never raise."""
    try:
        from datetime import UTC, datetime
        ts = datetime.now(UTC).isoformat()
        log_path = Path.home() / ".claude-mnemos" / "inject.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    if os.environ.get(RECURSION_ENV) == "1":
        return 0
    os.environ[RECURSION_ENV] = "1"

    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        _log(f"stdin parse failed: {exc}")
        return 0

    if not isinstance(payload, dict):
        return 0

    source = payload.get("source")
    if source in SKIP_SOURCES:
        return 0

    cwd_str = payload.get("cwd")
    if not cwd_str:
        return 0

    try:
        from claude_mnemos.core.session_start import (
            build_adaptive_context_with_stats,
        )
        from claude_mnemos.mapping.resolver import (
            ProjectResolver,
            ResolverAmbiguityError,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"import failed: {exc}")
        return 0

    cwd = Path(cwd_str)
    try:
        project = ProjectResolver().resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        _log(f"resolve ambiguous: {exc}")
        return 0
    except Exception as exc:  # noqa: BLE001
        _log(f"resolve failed: {exc}")
        return 0

    if project is None:
        return 0

    try:
        context, stats = build_adaptive_context_with_stats(
            Path(project.vault_root),
            cwd=cwd,
            max_chars=DEFAULT_MAX_CHARS,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"build failed: {exc}")
        return 0

    if not context:
        return 0

    # Best-effort metric write — failure does not block the inject.
    try:
        from datetime import UTC, datetime
        from uuid import uuid4

        from claude_mnemos.state.inject_metrics import (
            InjectMetricEvent,
            InjectMetricsLog,
        )
        event = InjectMetricEvent(
            id=uuid4().hex,
            timestamp=datetime.now(UTC),
            session_id=payload.get("session_id"),
            operation="session_start",
            mode=stats.mode,
            tokens_full=stats.tokens_full,
            tokens_actual=stats.tokens_actual,
            candidates_total=stats.candidates_total,
            candidates_packed=stats.candidates_packed,
        )
        InjectMetricsLog.append_to_vault(Path(project.vault_root), event)
    except Exception as exc:  # noqa: BLE001
        _log(f"metric write failed: {exc}")

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
