---
name: mnemos-activity
description: Show recent mnemos activity entries (ingest, manual_restore). Use when the user asks "what did I do recently", "show history", or wants to find an op_id for undo.
argument-hint: "[limit]"
---

# /mnemos-activity

Parse `$ARGUMENTS` as an integer limit. Default to 10 if empty or invalid.

Invoke `get_recent_activity` MCP tool from the `mnemos` server with the limit.

Render entries newest-first as a short table:

| Time | Type | Op ID | Status |
| --- | --- | --- | --- |

For each entry:

- `Time` — `timestamp` shortened to `YYYY-MM-DD HH:MM` UTC
- `Type` — `operation_type` (ingest_extracted / ingest_raw_only / manual_restore)
- `Op ID` — first 8 chars of `id` (full id can be retrieved via search if needed)
- `Status` — show `[UNDONE <ts>]`, `[chain]` for manual_restore, `[undoable]`
  if `can_undo and not undone`, else blank

If no entries, say so.
