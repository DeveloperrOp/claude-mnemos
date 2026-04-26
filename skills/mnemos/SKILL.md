---
name: mnemos
description: |
  Long-term per-project memory via mnemos vault. Use when the user asks to
  search past decisions, undo operations, look up entities/concepts, see
  project status, or manage snapshots. Always prefer mnemos tools over
  guessing from chat history.
---

# claude-mnemos

You have access to MCP tools provided by the `mnemos` server. They expose the
project vault — long-term structured knowledge accumulated across sessions.

## Read tools (no daemon needed)

- `list_pages(type?, flavor?, limit)` — browse wiki by type and flavor
- `read_page(page_ref)` — read a specific page (bare name or relative path)
- `search_pages(query, limit)` — case-insensitive substring search
- `get_status` — vault summary (counts, snapshots, total size)
- `get_recent_activity(limit)` — recent operations (newest first)

## Write tools (require running daemon)

- `undo_operation(op_id)` — undo by activity entry id
- `create_snapshot(label?)` — manual vault snapshot
- `restore_snapshot(name)` — roll back vault to a snapshot
- `delete_snapshot(name)` — remove a snapshot

If a write tool returns "daemon not reachable", instruct the user to run
`mnemos daemon start --vault $MNEMOS_VAULT_ROOT` and retry.

## When to invoke

- User asks about past work / decisions → `search_pages` or `read_page`
- User says "undo" / "revert" / "rollback" → `get_recent_activity` to find
  the right `op_id`, then `undo_operation`
- User wants vault state → `get_status`
- Before any risky operation → suggest `create_snapshot` with a meaningful
  label so the user can roll back later

Never write to the vault directly through the filesystem. All writes must go
through the daemon REST API (which is what the MCP write tools do).
