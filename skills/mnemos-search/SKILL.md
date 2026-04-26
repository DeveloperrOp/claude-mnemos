---
name: mnemos-search
description: Search the mnemos vault by substring across page filenames and bodies. Use when the user wants to find past mentions of a topic, person, or decision in their vault.
argument-hint: "<query>"
---

# /mnemos-search

User query: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user what to search for.

Otherwise invoke the `search_pages` MCP tool from the `mnemos` server with
`query=$ARGUMENTS` and `limit=20`.

For each result, show:

- The page path (e.g. `wiki/entities/foo.md`)
- Whether the match was in the filename, body, or both
- The snippet (if body match)

If results are empty, say so and suggest a broader query (fewer words, or
without quotes).
