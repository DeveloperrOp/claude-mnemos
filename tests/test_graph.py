from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.core.graph import build_page_graph


def _write_page(vault: Path, slug: str, body: str = "", related: list[str] | None = None) -> None:
    """Write a wiki page with minimal frontmatter at vault/wiki/<slug>.md."""
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    related_str = ""
    if related:
        related_str = "related:\n" + "\n".join(f"  - {r}" for r in related) + "\n"
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        "status: draft\n"
        "confidence: 0.7\n"
        "flavor: []\n"
        "sources: []\n"
        f"{related_str}"
        + ("related: []\n" if not related else "")
        + "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def test_build_page_graph_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    graph = build_page_graph(tmp_path)
    assert graph == {}


def test_build_page_graph_isolated_page(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="no links")
    graph = build_page_graph(tmp_path)
    assert "concepts/a" in graph
    assert graph["concepts/a"] == set()


def test_build_page_graph_body_wikilinks_undirected(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/b]] for details.")
    _write_page(tmp_path, "concepts/b")
    graph = build_page_graph(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in graph["concepts/b"]


def test_build_page_graph_frontmatter_related(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", related=["concepts/b"])
    _write_page(tmp_path, "concepts/b")
    graph = build_page_graph(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in graph["concepts/b"]


def test_build_page_graph_unknown_target_does_not_crash(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/missing]]")
    graph = build_page_graph(tmp_path)
    assert "concepts/missing" in graph["concepts/a"]


def test_build_page_graph_skips_invalid_frontmatter(tmp_path: Path) -> None:
    bad = tmp_path / "wiki" / "broken.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not yaml frontmatter\nbody only\n", encoding="utf-8")
    _write_page(tmp_path, "concepts/a")
    graph = build_page_graph(tmp_path)
    assert "concepts/a" in graph
    assert "broken" not in graph
