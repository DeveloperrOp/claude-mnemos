"""Undirected page adjacency graph for adaptive context inject (Plan #13c).

Slugs are relative paths under ``wiki/`` without the ``.md`` suffix
(e.g. ``concepts/foo``). Edges are derived from:

- Body wikilinks ``[[target]]`` — via :mod:`claude_mnemos.core.wikilinks`.
- Frontmatter ``related: [...]`` lists.

The resulting graph is undirected: if A → B is found in either direction,
both neighbors entries point to each other. Targets that don't have their
own page entry still appear as keys (with no neighbors), so callers can
treat the graph as "every slug ever mentioned anywhere".

Pages with malformed frontmatter are skipped silently — graph construction
must never raise on a bad page.
"""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.core.page_io import PageParseError, read_page, slug_from_page_path
from claude_mnemos.core.wikilinks import extract_wikilinks


def build_page_graph(vault: Path) -> dict[str, set[str]]:
    """Walk ``vault/wiki/**/*.md`` and return slug → set of neighbor slugs.

    Bidirectional. Bad pages are skipped. Targets not present as their own
    pages still appear as keys (empty neighbor set).
    """
    graph: dict[str, set[str]] = {}
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return graph

    for page_path in wiki_root.rglob("*.md"):
        try:
            parsed = read_page(page_path)
        except PageParseError:
            continue
        slug = slug_from_page_path(vault, page_path)
        graph.setdefault(slug, set())

        # Body wikilinks
        for link in extract_wikilinks(parsed.body):
            target = link.target.strip()
            if not target:
                continue
            graph[slug].add(target)
            graph.setdefault(target, set()).add(slug)

        # Frontmatter related[]
        for related in parsed.frontmatter.related:
            r = related.strip()
            if not r:
                continue
            graph[slug].add(r)
            graph.setdefault(r, set()).add(slug)

    return graph


def pages_within_k_hops(
    graph: dict[str, set[str]],
    seeds: set[str],
    *,
    k: int = 2,
) -> dict[str, int]:
    """BFS from each seed; return slug → minimum hop distance for all
    reachable pages within ``k`` hops. Seeds map to 0.

    Seeds not present in ``graph`` are silently skipped. The minimum-distance
    win is intentional: when a slug is reachable from multiple seeds, the
    closest seed determines its hop value.
    """
    distances: dict[str, int] = {}
    frontier: list[str] = []
    for s in seeds:
        if s in graph:
            distances[s] = 0
            frontier.append(s)

    for hop in range(1, k + 1):
        next_frontier: list[str] = []
        for node in frontier:
            for neighbor in graph.get(node, set()):
                if neighbor in distances:
                    continue
                distances[neighbor] = hop
                next_frontier.append(neighbor)
        if not next_frontier:
            break
        frontier = next_frontier

    return distances
