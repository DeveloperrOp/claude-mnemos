# Changelog

## [Unreleased] — Plan #13b-α (2026-04-27)

### Added
- `~/.claude-mnemos/project-map.json` (cwd → vault routing).
- Per-project + global settings persistence under `~/.claude-mnemos/`.
- `mnemos project` and `mnemos settings` CLI subgroups.
- `/projects/*` and `/settings/*` daemon REST endpoints.
- MCP `--auto-resolve` / `--project NAME` flags + degraded mode.
- `migrate_legacy_dotmnemos()` helper that moves daemon.pid /
  daemon.config.json from `~/.mnemos/` to `~/.claude-mnemos/`.

### Changed
- All existing CLI subgroups: `--vault PATH` → `--project NAME`
  (auto-resolves from cwd via project-map if omitted).
- `mnemos ingest` positional `vault` argument → `--project NAME` flag.
- `.mcp.json` uses `--auto-resolve` instead of `--vault ${MNEMOS_VAULT_ROOT}`.
- Daemon applies project's `snapshots` settings at startup; reloads on
  `PATCH /settings/{project}` (matching its own vault).
- PID file path moved from `~/.mnemos/` to `~/.claude-mnemos/`.

### Removed
- `MNEMOS_VAULT_ROOT` env var support (hard cut — see migration in README).
- `mnemos ingest <jsonl> <vault>` positional vault arg (now `--project`).
