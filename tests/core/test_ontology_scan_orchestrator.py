"""Tests for scan_ontology orchestrator (Phase B3d).

Orchestrator glues heuristics + LLM validator + Suggestion creation. Tests
verify the full pipeline using a FakeLLMClient — no subprocess, no LLM cost.

Key invariants:

1. **Idempotency** — re-running scan on the same vault must not create
   duplicate Suggestions. Existing Suggestions (pending + archived) are
   matched by (operation, affected_pages, proposed_target).

2. **Distinct verdicts produce no Suggestions** — the LLM filter is a
   first-class safety net.

3. **Verdict → operation mapping** is the apply pipeline contract:
   - DUPLICATE + target_slug matches one source → `delete_page` (the OTHER)
   - DUPLICATE/MERGE + target_slug is new → `merge_entities`
   - RenameCandidate → `rename_entity` (no LLM, slug-driven)

4. **Capping** — when there are more candidates than ``max_llm_calls``,
   the orchestrator drops the lowest-similarity ones.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from claude_mnemos.core.ontology_scan import scan_ontology
from claude_mnemos.ingest.llm import ExtractionRaw, LLMExtractionError
from claude_mnemos.state.ontology import SuggestionStore


def _write_page(
    vault: Path,
    rel: str,
    *,
    title: str = "Test",
    body: str = "",
    page_type: str = "concept",
) -> Path:
    today = "2026-05-22"
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\n"
        f"title: {title}\n"
        f"type: {page_type}\n"
        f"status: draft\n"
        f"confidence: 0.7\n"
        f"flavor: []\n"
        f"sources: []\n"
        f"related: []\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"agent_written: false\n"
        f"---\n\n{body}"
    )
    path.write_text(fm, encoding="utf-8")
    return path


class ScriptedLLMClient:
    """Returns payloads in order. Useful when test wants different verdicts
    for sequential calls.
    """

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.call_count = 0

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        if self.call_count >= len(self.payloads):
            raise AssertionError(
                f"LLM called more than expected (call {self.call_count + 1}, "
                f"only {len(self.payloads)} scripted payloads)"
            )
        payload = self.payloads[self.call_count]
        self.call_count += 1
        if validate is not None:
            validate(payload)
        return ExtractionRaw(payload=payload, input_tokens=0, output_tokens=0)


class TestEmptyVault:
    def test_empty_vault_produces_no_suggestions(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        (vault / "wiki").mkdir(parents=True)
        llm = ScriptedLLMClient([])
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert result.created == []
        assert result.scanned_pages == 0
        assert llm.call_count == 0


class TestExactDuplicateFlow:
    def test_exact_duplicate_creates_merge_suggestion(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/foo.md", title="Foo", body="copy paste")
        _write_page(vault, "wiki/concepts/bar.md", title="Bar", body="copy paste")
        # LLM verdict: duplicate, target slug = foo (matches page_a)
        # → orchestrator should emit delete_page for bar.
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "duplicate",
                    "target_slug": "foo",
                    "merged_title": "Foo",
                    "reason": "Identical content.",
                }
            ]
        )
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert len(result.created) == 1

        store = SuggestionStore(vault)
        suggestions = store.list()
        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.frontmatter.operation == "delete_page"
        # The page deleted is the one whose slug ISN'T target.
        assert s.frontmatter.affected_pages == ["wiki/concepts/bar.md"]
        assert "Identical" in s.frontmatter.reason

    def test_exact_duplicate_with_new_target_uses_merge(self, tmp_path: Path) -> None:
        # LLM verdict: duplicate, target slug = "combined" (matches neither source)
        # → no single page can be kept; emit merge_entities with new target.
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/foo.md", title="Foo", body="same")
        _write_page(vault, "wiki/concepts/bar.md", title="Bar", body="same")
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "duplicate",
                    "target_slug": "combined",
                    "merged_title": "Combined",
                    "reason": "Identical but need new name.",
                }
            ]
        )
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert len(result.created) == 1
        store = SuggestionStore(vault)
        s = store.list()[0]
        assert s.frontmatter.operation == "merge_entities"
        assert s.frontmatter.proposed_target == "wiki/concepts/combined.md"
        assert set(s.frontmatter.affected_pages) == {
            "wiki/concepts/bar.md",
            "wiki/concepts/foo.md",
        }


class TestMergeVerdictFlow:
    def test_merge_verdict_creates_merge_suggestion(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(
            vault,
            "wiki/concepts/auth-a.md",
            title="Auth A",
            body="jwt token authentication with refresh handling logic",
        )
        _write_page(
            vault,
            "wiki/concepts/auth-b.md",
            title="Auth B",
            body="jwt token authentication with refresh handling logic and security extra",
        )
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "merge",
                    "target_slug": "auth-jwt-pattern",
                    "merged_title": "Auth JWT Pattern",
                    "reason": "Overlapping coverage of JWT auth.",
                }
            ]
        )
        result = scan_ontology(
            vault, llm=llm, max_llm_calls=50, partial_threshold=0.5
        )
        assert len(result.created) == 1
        store = SuggestionStore(vault)
        s = store.list()[0]
        assert s.frontmatter.operation == "merge_entities"
        assert s.frontmatter.proposed_target == "wiki/concepts/auth-jwt-pattern.md"


class TestDistinctVerdictFlow:
    def test_distinct_verdict_produces_no_suggestion(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/a.md", title="A", body="copy paste")
        _write_page(vault, "wiki/concepts/b.md", title="B", body="copy paste")
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "distinct",
                    "reason": "Despite identical text, they cover different scopes.",
                }
            ]
        )
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert result.created == []
        assert result.skipped_distinct == 1
        store = SuggestionStore(vault)
        assert store.list() == []


class TestRenameFlow:
    def test_slug_mismatch_creates_rename_without_llm(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/old-name.md", title="Completely Different Title")
        # No exact/partial dup → no LLM calls needed
        llm = ScriptedLLMClient([])
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert len(result.created) == 1
        assert llm.call_count == 0
        store = SuggestionStore(vault)
        s = store.list()[0]
        assert s.frontmatter.operation == "rename_entity"
        assert s.frontmatter.affected_pages == ["wiki/concepts/old-name.md"]
        assert s.frontmatter.proposed_target == "wiki/concepts/completely-different-title.md"

    def test_skip_rename_if_target_path_exists(self, tmp_path: Path) -> None:
        # Two pages: old-name.md (title says "Foo") + foo.md (already named foo).
        # Rename would conflict — skip.
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/old-name.md", title="Foo Bar Baz")
        _write_page(vault, "wiki/concepts/foo-bar-baz.md", title="Foo Bar Baz", body="unique")
        llm = ScriptedLLMClient([])
        result = scan_ontology(vault, llm=llm, max_llm_calls=50)
        # Rename to foo-bar-baz would clobber the existing file → skip.
        # But foo-bar-baz.md itself slugifies correctly so no rename for it either.
        rename_suggestions = [
            s for s in SuggestionStore(vault).list()
            if s.frontmatter.operation == "rename_entity"
        ]
        assert rename_suggestions == []


class TestIdempotency:
    def test_second_scan_does_not_duplicate(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/foo.md", title="Foo", body="same")
        _write_page(vault, "wiki/concepts/bar.md", title="Bar", body="same")
        # Same LLM verdict twice — orchestrator should skip second creation.
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "duplicate",
                    "target_slug": "foo",
                    "merged_title": "Foo",
                    "reason": "Identical.",
                },
                {
                    "verdict": "duplicate",
                    "target_slug": "foo",
                    "merged_title": "Foo",
                    "reason": "Identical.",
                },
            ]
        )
        result1 = scan_ontology(vault, llm=llm, max_llm_calls=50)
        result2 = scan_ontology(vault, llm=llm, max_llm_calls=50)
        assert len(result1.created) == 1
        assert result2.created == []
        assert result2.skipped_existing >= 1
        store = SuggestionStore(vault)
        assert len(store.list()) == 1  # Still only one suggestion total


class TestCapping:
    def test_max_llm_calls_capped(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        # 4 pairs of identical pages → 4 LLM-eligible candidates. Cap at 2.
        for i in range(4):
            _write_page(vault, f"wiki/concepts/a{i}.md", title=f"A{i}", body=f"body{i}")
            _write_page(vault, f"wiki/concepts/b{i}.md", title=f"B{i}", body=f"body{i}")
        llm = ScriptedLLMClient(
            [
                {
                    "verdict": "distinct",
                    "reason": "Different scope.",
                }
                for _ in range(2)
            ]
        )
        result = scan_ontology(vault, llm=llm, max_llm_calls=2)
        assert llm.call_count == 2
        assert result.skipped_capped == 2


class TestErrorRecovery:
    def test_llm_error_on_one_pair_does_not_kill_scan(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        _write_page(vault, "wiki/concepts/foo.md", title="Foo", body="same1")
        _write_page(vault, "wiki/concepts/bar.md", title="Bar", body="same1")
        _write_page(vault, "wiki/concepts/baz.md", title="Baz", body="same2")
        _write_page(vault, "wiki/concepts/qux.md", title="Qux", body="same2")

        call_count = [0]

        class FlakyLLM:
            def extract(
                self,
                *,
                system: str,
                user: str,
                tool: dict[str, Any],
                validate: Callable[[dict[str, Any]], Any] | None = None,
            ) -> ExtractionRaw:
                call_count[0] += 1
                if call_count[0] == 1:
                    raise LLMExtractionError("transient failure")
                payload = {
                    "verdict": "duplicate",
                    "target_slug": "baz",
                    "merged_title": "Baz",
                    "reason": "Identical content for second pair.",
                }
                if validate is not None:
                    validate(payload)
                return ExtractionRaw(payload=payload, input_tokens=0, output_tokens=0)

        result = scan_ontology(vault, llm=FlakyLLM(), max_llm_calls=50)
        # Second pair should have produced a suggestion despite first crashing.
        assert len(result.created) == 1
        assert len(result.errors) == 1
