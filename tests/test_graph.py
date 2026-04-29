from __future__ import annotations

from pathlib import Path

from claude_mnemos.core.graph import build_page_graph, pages_within_k_hops
from claude_mnemos.core.graph import build_page_graph_with_pages


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


def test_pages_within_k_hops_seeds_only_at_k0() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=0)
    assert out == {"a": 0}


def test_pages_within_k_hops_one_hop() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=1)
    assert out == {"a": 0, "b": 1}


def test_pages_within_k_hops_two_hops() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=2)
    assert out == {"a": 0, "b": 1, "c": 2}


def test_pages_within_k_hops_multiple_seeds() -> None:
    graph = {"a": {"x"}, "b": {"y"}, "x": {"a"}, "y": {"b"}}
    out = pages_within_k_hops(graph, {"a", "b"}, k=1)
    assert out == {"a": 0, "b": 0, "x": 1, "y": 1}


def test_pages_within_k_hops_seed_not_in_graph_skipped() -> None:
    graph = {"a": {"b"}, "b": {"a"}}
    out = pages_within_k_hops(graph, {"missing"}, k=2)
    assert out == {}


def test_pages_within_k_hops_min_distance_wins() -> None:
    # diamond: a→b, a→c, b→d, c→d. d is reachable in 2 hops via either path.
    graph = {"a": {"b", "c"}, "b": {"a", "d"}, "c": {"a", "d"}, "d": {"b", "c"}}
    out = pages_within_k_hops(graph, {"a"}, k=2)
    assert out["d"] == 2


def test_build_page_graph_with_pages_returns_pair(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/b]]")
    _write_page(tmp_path, "concepts/b", body="bravo")
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in pages
    assert "concepts/b" in pages
    assert pages["concepts/a"].body == "See [[concepts/b]]"


def test_build_page_graph_with_pages_skips_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "wiki" / "broken.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not yaml frontmatter\nbody only\n", encoding="utf-8")
    _write_page(tmp_path, "concepts/a")
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert "concepts/a" in pages
    assert "broken" not in pages
    assert "broken" not in graph


def test_build_page_graph_with_pages_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert graph == {}
    assert pages == {}
