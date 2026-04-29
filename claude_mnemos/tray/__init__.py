"""Tray-icon supervisor for claude-mnemos daemon.

Standalone Python process that owns the daemon as a subprocess, displays a
system-tray icon, and exposes a small menu (Open dashboard / Restart / Show
logs / Quit). See docs/plans/2026-04-29-tray-autostart-design.md.
"""
