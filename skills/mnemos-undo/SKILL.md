---
name: mnemos-undo
description: Undo a previously logged mnemos operation by activity entry id, or undo the most recent undoable operation. Use when the user says "undo", "revert", "rollback", or "I shouldn't have ingested that".
argument-hint: "<op_id|--last>"
---

# /mnemos-undo

If `$ARGUMENTS` is empty or equals `--last`:

1. Invoke `get_recent_activity` MCP tool with `limit=20`.
2. Pick the newest entry where `can_undo: true` and `undone: false`.
3. If none, tell the user there's nothing to undo and stop.
4. Otherwise use that entry's `id` as `op_id`.

Otherwise treat `$ARGUMENTS` as the `op_id` (full UUID hex).

Invoke `undo_operation` MCP tool with the `op_id`.

Render the result:

- On success: confirm what was reverted (`restored_pages`), mention the new
  `manual_restore` entry id.
- If the response says "daemon not reachable", tell the user to run
  `mnemos daemon start --vault $MNEMOS_VAULT_ROOT` first, then retry.
- If daemon HTTP 4xx (e.g. `already undone`, `snapshot missing`), surface the
  detail verbatim.
