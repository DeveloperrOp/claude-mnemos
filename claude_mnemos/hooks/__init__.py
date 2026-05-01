"""Top-level package marker for the standalone mnemos hook scripts.

The scripts under ``D:\\code\\claude-mnemos\\hooks\\`` (session_start.py,
session_end.py) live outside the ``claude_mnemos`` package proper. They
add the repo root to ``sys.path`` themselves and import ``claude_mnemos``.
This package exists so import paths like ``claude_mnemos.hooks.errors`` work
inside the package — for the error-logging utility shared by hook scripts
and the daemon endpoint.
"""
