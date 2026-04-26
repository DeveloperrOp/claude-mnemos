---
name: mnemos-status
description: Show mnemos vault summary — counts of pages, snapshots, recent activity, total size. Invoke when the user asks "what's in the vault", "how big is the vault", or wants to verify the daemon and vault are healthy.
---

# /mnemos-status

Invoke the `get_status` MCP tool from the `mnemos` server (no arguments).

Render the JSON to the user as a short table:

| Metric | Value |
| --- | --- |
| Vault path | `{vault}` |
| Wiki pages | `{wiki_pages}` |
| Raw chats | `{raw_chats}` |
| Manifest entries | `{manifest_processed}` |
| Activity entries | `{activity_entries}` |
| Snapshots | `{snapshots}` |
| Total size | `{total_size_bytes}` bytes |

If the tool returns a vault state corruption error, surface it verbatim and
suggest the user check `<vault>/.activity.json` and `<vault>/.manifest.json`.
