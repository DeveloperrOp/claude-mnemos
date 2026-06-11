"""``mnemos hook <event>`` — fast hook entry.

Claude Code invokes this when a SessionStart/SessionEnd/PreCompact event
fires. It must cold-start fast (≤500ms): we lazy-import only the matching
``hooks/<event>.py`` ``main()`` function, skipping the FastAPI/uvicorn
stack entirely.

The bundled exe registers this as the hook target in ~/.claude/settings.json
when ``mnemos hooks install`` runs in frozen mode.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Callable

EVENTS = ("session-start", "session-end", "pre-compact")


def _import_session_start() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import session_start  # type: ignore
    return session_start.main


def _import_session_end() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import session_end  # type: ignore
    return session_end.main


def _import_pre_compact() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import pre_compact  # type: ignore
    return pre_compact.main


_DISPATCH: dict[str, str] = {
    "session-start": "_import_session_start",
    "session-end": "_import_session_end",
    "pre-compact": "_import_pre_compact",
}


def run(argv: list[str], stdin_payload: str | None = None) -> int:
    """Programmatic entry — used in tests and from cli.py."""
    import claude_mnemos.cli_hook as _self

    if not argv or argv[0] not in EVENTS:
        sys.stderr.write(
            f"mnemos hook: unknown event '{argv[0] if argv else ''}'. "
            f"Expected one of: {', '.join(EVENTS)}\n"
        )
        return 2

    event = argv[0]
    if stdin_payload is not None:
        sys.stdin = io.StringIO(stdin_payload)

    importer = getattr(_self, _DISPATCH[event])
    main_fn = importer()
    try:
        result = main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def _cmd_hook(args: argparse.Namespace) -> int:
    return run([args.event])


def add_hook_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("hook", help="Run a Claude Code hook (internal — invoked by Claude Code)")
    p.add_argument("event", choices=EVENTS, help="Hook event name")
    p.set_defaults(func=_cmd_hook)
