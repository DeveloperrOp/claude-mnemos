# Process-Integrity Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two confirmed process bugs that silently corrupt vault data — the watchdog flipping `agent_written` on mere reads, and skip-extractions creating orphaned source pages with broken backlinks — plus add a manifest↔filesystem drift lint guard.

**Architecture:** Three independent changes. (1) The watchdog handler gates its `agent_written` flip on a real *content* change (sha256+size signature cache) instead of trusting any `FileModifiedEvent` — Windows emits one for last-access-time bumps, which reads cause. (2) The ingest pipeline routes a zero-knowledge extraction (LLM returned no pages) to the existing raw-only shape instead of writing an empty knowledge source page with a dead `[[Open transcript]]` backlink. (3) A new `manifest_drift` lint rule flags manifest entries whose referenced files no longer exist.

**Tech Stack:** Python 3.12, Pydantic v2, `watchdog` 6.0.0, pytest. Dev venv: `D:\code\claude-mnemos\.venv\Scripts\python.exe`. Run from `cd /d/code/claude-mnemos`.

**Root-cause evidence (from diagnosis):**
- Watchdog: `watchdog` Windows mask includes `FILE_NOTIFY_CHANGE_LAST_ACCESS`; this machine has `fsutil DisableLastAccess == 2` (atime ON); a read → atime bump → `FILE_ACTION_MODIFIED` (indistinguishable from a write) → `VaultChangeHandler._mark_under_lock` flips `agent_written` unconditionally. Repro: `os.utime` atime-only bump flips the flag with byte-identical content.
- Skip orphans: `pipeline.py` unconditionally appends `source_page` to `to_write` even when `extraction.pages == []`; `_build_source_page` always emits the `[[<id>|Open transcript]]` backlink + `sources:[raw/chats/<id>.md]`. The raw files of the 2026-05-02 batch were deleted out-of-band (historical artifact, no live deleter), leaving orphans. No manifest-drift guard exists.

---

### Task 1: Watchdog content-signature gate (stop spurious `agent_written` flips)

**Files:**
- Modify: `claude_mnemos/daemon/watchdog_handler.py`
- Test: `tests/daemon/test_watchdog_handler_signature.py` (new)

**Design:** `VaultChangeHandler` keeps `self._sigs: dict[Path, tuple[str, int]]` (sha256 hex + byte length), guarded by `threading.Lock`. Seeded at construction by walking `vault/wiki/**/*.md` (best-effort) so every pre-existing page has a baseline. In `_handle`, a self-write (`tracker.contains`) re-baselines the signature and returns. In `_mark_under_lock`, compute the current signature: if it equals the remembered one → the event was a metadata/atime touch, **return without flipping**; otherwise flip as today, then re-baseline to the post-write bytes. An unseen page (no baseline) is seeded and skipped (conservative — don't flip on first-ever observation).

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_watchdog_handler_signature.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.daemon.watchdog_handler import VaultChangeHandler
from watchdog.events import FileModifiedEvent

_FM = """---
title: Foo
type: concept
status: draft
confidence: 0.7
flavor: []
sources: []
related: []
created: '2026-04-26'
updated: '2026-04-26'
agent_written: true
---
body text
"""


def _seed_page(vault: Path) -> Path:
    p = vault / "wiki" / "concepts" / "foo.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_FM, encoding="utf-8")
    return p


def _handler(vault: Path) -> VaultChangeHandler:
    return VaultChangeHandler(vault, OurWritesTracker(), Alerts())


def _agent_written(p: Path) -> bool:
    return "agent_written: false" not in p.read_text(encoding="utf-8")


def test_metadata_only_event_does_not_flip(tmp_path: Path) -> None:
    # A modify event whose content is byte-identical (atime/attrib bump) must
    # NOT flip agent_written -> false.
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)  # seeds foo.md signature at construction
    h.on_modified(FileModifiedEvent(str(p)))
    assert _agent_written(p) is True


def test_real_content_edit_flips(tmp_path: Path) -> None:
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)
    p.write_text(_FM.replace("body text", "EDITED by a human"), encoding="utf-8")
    h.on_modified(FileModifiedEvent(str(p)))
    assert _agent_written(p) is False


def test_self_write_rebaselines_signature(tmp_path: Path) -> None:
    # After a daemon self-write (tracker.contains), a later metadata event on
    # the NEW content must not flip.
    p = _seed_page(tmp_path)
    h = _handler(tmp_path)
    new = _FM.replace("body text", "ingested content")
    h.tracker.add(p)
    p.write_text(new, encoding="utf-8")
    h.on_modified(FileModifiedEvent(str(p)))  # self-write -> re-baseline, skip
    h.tracker.remove(p)
    h.on_modified(FileModifiedEvent(str(p)))  # metadata event on new content
    assert _agent_written(p) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /d/code/claude-mnemos && .venv/Scripts/python.exe -m pytest tests/daemon/test_watchdog_handler_signature.py -q`
Expected: FAIL (`test_metadata_only_event_does_not_flip` flips today; the others may pass for the wrong reason).

- [ ] **Step 3: Add the signature cache + gate to `watchdog_handler.py`**

Add imports near the top (after the existing imports):

```python
import hashlib
import threading
```

In `VaultChangeHandler.__init__`, after `self.lock_timeout_s = lock_timeout_s`, add:

```python
        # Content-signature cache (sha256 hex, byte length) per page. Used to
        # tell a real content edit from a metadata/atime touch — on Windows a
        # mere read bumps last-access-time, which surfaces as a FileModifiedEvent
        # indistinguishable from a write. Without this gate, reading/linting/
        # opening the vault in Obsidian would falsely flip agent_written.
        self._sigs: dict[Path, tuple[str, int]] = {}
        self._sigs_lock = threading.Lock()
        self._seed_signatures()
```

Add these methods to the class (e.g. just after `__init__`):

```python
    def _content_signature(self, path: Path) -> tuple[str, int] | None:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return (hashlib.sha256(data).hexdigest(), len(data))

    def _seed_signatures(self) -> None:
        """Baseline every existing wiki page so the first event after start is
        compared, not assumed. Best-effort: a read failure just skips that page
        (it will be lazily seeded on its first event)."""
        wiki = self.vault / "wiki"
        if not wiki.is_dir():
            return
        for p in wiki.rglob("*.md"):
            if any(part.startswith(".") for part in p.relative_to(self.vault).parts):
                continue
            sig = self._content_signature(p.resolve())
            if sig is not None:
                with self._sigs_lock:
                    self._sigs[p.resolve()] = sig

    def _rebaseline(self, path: Path) -> None:
        sig = self._content_signature(path)
        with self._sigs_lock:
            if sig is None:
                self._sigs.pop(path, None)
            else:
                self._sigs[path] = sig
```

In `_handle`, change the self-write check to re-baseline before returning. Replace:

```python
            if self.tracker.contains(path):
                return
```

with:

```python
            if self.tracker.contains(path):
                # Daemon's own write (ingest/flip/etc). Re-baseline so the next
                # external event compares against the freshly-written content
                # instead of stale bytes (which would look like an edit).
                self._rebaseline(path)
                return
```

In `_mark_under_lock`, after the `read_page` try/except block and BEFORE building `new_fm`, insert the content-change gate:

```python
        cur_sig = self._content_signature(path)
        with self._sigs_lock:
            prev_sig = self._sigs.get(path)
        if prev_sig is None:
            # First time we see this page (created after start / unseeded) —
            # baseline it and do NOT flip. Don't treat an unverifiable first
            # observation as a human edit.
            if cur_sig is not None:
                with self._sigs_lock:
                    self._sigs[path] = cur_sig
            return
        if cur_sig == prev_sig:
            # Byte-identical: a metadata/atime/attrib event, not a content edit.
            return
```

Then, after the `atomic_write(path, serialize_page(new_parsed))` succeeds (inside the `try`, or right after the `finally`), re-baseline to the post-flip content so the flip's own write event doesn't re-trigger:

```python
        self._rebaseline(path)
```

(Place this line after `self.tracker.remove(path)` returns, i.e. after the try/finally that writes the page.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /d/code/claude-mnemos && .venv/Scripts/python.exe -m pytest tests/daemon/test_watchdog_handler_signature.py tests/daemon/test_watchdog_integration.py -q`
Expected: PASS (new tests green; existing watchdog integration tests still green).

- [ ] **Step 5: Gate + commit**

Run: `.venv/Scripts/python.exe -m ruff check claude_mnemos && .venv/Scripts/python.exe -m mypy claude_mnemos`
Then commit (message file written without BOM via the Write tool, committed with explicit pathspec):

```bash
git add claude_mnemos/daemon/watchdog_handler.py tests/daemon/test_watchdog_handler_signature.py
git commit -F <msg-file>
```
Message subject: `fix(watchdog): only flip agent_written on a real content change`

---

### Task 2: Skip-extraction → raw_only (no orphaned source page)

**Files:**
- Modify: `claude_mnemos/ingest/pipeline.py` (insert a branch right after the `extraction = extractor(...)` call, before `source_relative = ...`)
- Test: `tests/test_pipeline.py` (add cases)

**Design:** When `extraction.pages == []` the LLM produced no knowledge (a skip or empty result). Writing a `wiki/sources/...` page in that case yields an empty knowledge node whose `[[<id>|Open transcript]]` backlink and `sources:[raw/chats/<id>.md]` pointer become broken if the raw is ever cleaned up — the exact dev-vault junk. Instead, keep the raw, record the ingest as `raw_only` (`source_path=None`, `created_pages=[raw]`), log `ingest_raw_only` with the `skipped_reason` in metadata, and write no source page.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_pipeline.py
def test_skip_extraction_writes_no_source_page(tmp_path):
    """A zero-knowledge extraction keeps the raw but writes no wiki/sources page."""
    # Reuse this module's existing fixtures for a fake extractor/llm. The
    # extractor returns an ExtractionResult with pages=[] and a skipped_reason.
    from datetime import date
    from claude_mnemos.ingest.extraction import ExtractionResult

    def _skip_extractor(**_kw):
        return ExtractionResult(
            summary="belongs to another project",
            skipped_reason="this transcript is about project X, not this vault",
            pages=[],
            input_tokens=123,
            output_tokens=4,
        )

    vault = tmp_path / "vault"
    jsonl = _write_sample_transcript(tmp_path)  # existing helper in this test module
    result = ingest(
        jsonl, vault,
        cfg=_test_cfg(),                 # existing helper
        llm_client=_FakeLLM(),           # existing helper / object
        extractor=_skip_extractor,
        extract=True,
        today=date(2026, 4, 26),
    )
    assert result.status == "raw_only"
    # No source page on disk and none referenced by the manifest.
    assert not list((vault / "wiki" / "sources").glob("*.md"))
    assert (vault / "raw" / "chats").exists()
    from claude_mnemos.state.manifest import Manifest
    rec = next(iter(Manifest.load(vault).ingested.values()))
    assert rec.source_path is None
    assert rec.created_pages == [r for r in rec.created_pages if r.startswith("raw/")]
```

> NOTE for implementer: adapt `_write_sample_transcript`, `_test_cfg`, `_FakeLLM` to the actual helper names already present in `tests/test_pipeline.py`. Read the file's existing tests first and mirror their fixture style; do not invent new fixtures if equivalents exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py::test_skip_extraction_writes_no_source_page -q`
Expected: FAIL — today a `wiki/sources/*.md` page IS written and `source_path` is set.

- [ ] **Step 3: Add the zero-knowledge branch in `pipeline.py`**

Immediately after the `extraction = extractor(...)` call (the block ending at the closing `)` around line 192) and BEFORE `source_relative = Path("wiki/sources") / ...`, insert:

```python
            if not extraction.pages:
                # Zero-knowledge extraction (LLM skipped this session or found
                # nothing for this vault). Keep the raw transcript but write NO
                # wiki/sources page: an empty knowledge node whose
                # [[<id>|Open transcript]] backlink + sources:[raw/chats/<id>.md]
                # pointer become broken links once the raw is cleaned up. Record
                # as raw_only instead.
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(UTC),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=cfg.model,
                        input_tokens=extraction.input_tokens,
                        output_tokens=extraction.output_tokens,
                        transcript_path=str(jsonl_path.resolve()),
                        raw_transcript_bytes=len(raw_bytes),
                    ),
                )
                txn.write(Path(".manifest.json"), manifest.serialize_to_string())
                snapshot_target = txn.pre_promote_snapshot_path()
                activity_id = uuid4().hex
                activity.append(
                    _build_activity_entry(
                        op_type="ingest_raw_only",
                        snapshot_target=snapshot_target,
                        vault_root=vault_root,
                        affected=[raw_relative.as_posix()],
                        metadata={
                            "session_id": session_id,
                            "skipped_reason": extraction.skipped_reason,
                            "model": cfg.model,
                            "input_tokens": extraction.input_tokens,
                            "output_tokens": extraction.output_tokens,
                        },
                        entry_id=activity_id,
                    )
                )
                txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())
                if dry_run:
                    txn.reject("dry-run (--extract, no knowledge)")
                    if chunk_cache is not None:
                        chunk_cache.clear()
                    return IngestResult(
                        status="dry_run",
                        session_id=session_id,
                        raw_path=None,
                        snapshot_path=None,
                        activity_id=None,
                    )
                promote = txn.promote_to_vault(tracker=tracker)
                if chunk_cache is not None:
                    chunk_cache.clear()
                return IngestResult(
                    status="raw_only",
                    session_id=session_id,
                    raw_path=vault_root / raw_relative,
                    input_tokens=extraction.input_tokens,
                    output_tokens=extraction.output_tokens,
                    model=cfg.model,
                    snapshot_path=promote.snapshot,
                    activity_id=activity_id,
                )
```

The existing extract path (build source page, collision check, write pages, manifest, promote, return `status="extracted"`) stays unchanged below this branch and now only runs when `extraction.pages` is non-empty.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py tests/ingest -q`
Expected: PASS (new test green; existing extract/raw_only/dry-run/chunk-cache pipeline tests still green).

- [ ] **Step 5: Gate + commit**

Run: `.venv/Scripts/python.exe -m ruff check claude_mnemos && .venv/Scripts/python.exe -m mypy claude_mnemos`
```bash
git add claude_mnemos/ingest/pipeline.py tests/test_pipeline.py
git commit -F <msg-file>
```
Message subject: `fix(ingest): a skipped (zero-knowledge) extraction is raw_only, not an empty source page`

---

### Task 3: `manifest_drift` lint rule (detect manifest↔filesystem drift)

**Files:**
- Modify: `claude_mnemos/lint/rules.py` (new rule + register in `RULE_REGISTRY` and `RULE_VERSIONS`)
- Test: `tests/lint/test_rules.py` (add cases)

**Design:** A read-only rule that loads the manifest and flags any entry whose `raw_path`, `source_path`, or `created_pages` reference a file that no longer exists on disk — an ERROR finding per missing ref, non-fixable (auto-pruning the manifest is risky; surface for the user). A corrupt/missing manifest is not the rule's concern (it returns no findings rather than crashing).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/lint/test_rules.py
import json


def _write_manifest(vault: Path, records: dict) -> None:
    (vault / ".manifest.json").write_text(
        json.dumps({"version": 1, "ingested": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_manifest_drift_flags_missing_raw(tmp_path: Path):
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/gone.md", "source_path": None,
            "created_pages": ["raw/chats/gone.md"], "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    missing = [f for f in findings if f.metadata.get("missing") == "raw/chats/gone.md"]
    assert len(missing) == 1
    assert missing[0].severity == LintSeverity.ERROR
    assert missing[0].fixable is False


def test_manifest_drift_clean_when_files_present(tmp_path: Path):
    raw = tmp_path / "raw" / "chats" / "here.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("x", encoding="utf-8")
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/here.md", "source_path": None,
            "created_pages": ["raw/chats/here.md"], "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_manifest_drift_no_manifest_is_noop(tmp_path: Path):
    assert RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/lint/test_rules.py -k manifest_drift -q`
Expected: FAIL with `KeyError: 'manifest_drift'` (rule not registered).

- [ ] **Step 3: Implement the rule in `lint/rules.py`**

Add import near the other imports:

```python
from claude_mnemos.state.manifest import Manifest, ManifestCorruptError
```

Add the rule (place it after `orphan_pages` or with the other rules):

```python
def manifest_drift(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    """Flag manifest entries whose referenced files no longer exist on disk.

    Catches silent drift where the manifest claims a raw/source/created file
    exists but it was deleted out-of-band — the manifest then lies and the
    affected source pages keep dead [[Open transcript]] backlinks. Read-only;
    a missing/corrupt manifest yields no findings (a separate concern).
    """
    out: list[LintFinding] = []
    try:
        manifest = Manifest.load(vault)
    except ManifestCorruptError:
        return out
    for sha, rec in manifest.ingested.items():
        refs = [rec.raw_path]
        if rec.source_path:
            refs.append(rec.source_path)
        refs.extend(rec.created_pages)
        for ref in dict.fromkeys(refs):  # dedupe, keep order
            if not (vault / ref).is_file():
                msg = f"manifest references missing file {ref} (session {rec.session_id})"
                out.append(
                    LintFinding(
                        id=_finding_id("manifest_drift", ref, msg),
                        rule_id="manifest_drift",
                        severity=LintSeverity.ERROR,
                        message=msg,
                        page_path=ref,
                        fixable=False,
                        fix_kind=None,
                        metadata={"session_id": rec.session_id, "sha": sha, "missing": ref},
                    )
                )
    return out
```

Register it: add `"manifest_drift": "v1",` to `RULE_VERSIONS` and `"manifest_drift": manifest_drift,` to `RULE_REGISTRY` (mirror how the existing rules are registered — match insertion order and formatting).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/lint -q`
Expected: PASS (new manifest_drift tests green; existing lint tests still green).

- [ ] **Step 5: Gate + commit**

Run: `.venv/Scripts/python.exe -m ruff check claude_mnemos && .venv/Scripts/python.exe -m mypy claude_mnemos`
```bash
git add claude_mnemos/lint/rules.py tests/lint/test_rules.py
git commit -F <msg-file>
```
Message subject: `feat(lint): manifest_drift rule flags entries referencing missing files`

---

## Final verification (after all tasks)

- [ ] Full backend suite: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` → 0 failures (only the 6 known skips).
- [ ] `.venv/Scripts/python.exe -m mypy claude_mnemos` → Success.
- [ ] `.venv/Scripts/python.exe -m ruff check claude_mnemos` → All checks passed.
- [ ] Live confirmation against the dev vault: run lint twice and confirm the second run no longer produces new `human_edit_detected` events and `agent_written` no longer flips on read.
- [ ] Adversarial review of the diff before tagging v0.0.51.
- [ ] Data cleanup (separate, operational): remove the 17 orphaned skip-marker source pages + their stale manifest entries from `.mnemos-dev` via mnemos trash (undoable).

## Out of scope (historical artifact, no code fix)
The 2026-05-02 raw deletion was a one-off (manual cleanup during early dev); no production path deletes raw while leaving the manifest. The `manifest_drift` rule (Task 3) is the guard so a future drift is caught operationally.
