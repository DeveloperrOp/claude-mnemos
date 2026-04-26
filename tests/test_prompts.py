import re
from pathlib import Path

from claude_mnemos.ingest.prompts import format_user, load_system


def test_load_system_returns_non_empty_string():
    s = load_system()
    assert isinstance(s, str)
    assert len(s) > 100
    assert "save_wiki_pages" in s
    assert "entity" in s.lower()
    assert "concept" in s.lower()


def test_load_system_cached(monkeypatch):
    """load_system must hit the file system at most once per process."""
    from claude_mnemos.ingest import prompts as prompts_mod

    # Clear any prior cache to start clean
    prompts_mod.load_system.cache_clear()

    call_count = {"n": 0}
    real_read = Path.read_text

    def counting_read(self, *args, **kwargs):
        if self.name == "system.md":
            call_count["n"] += 1
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read)

    a = prompts_mod.load_system()
    b = prompts_mod.load_system()
    c = prompts_mod.load_system()

    assert a == b == c
    assert call_count["n"] == 1, f"expected one read for system.md, got {call_count['n']}"

    # Cleanup so other tests get a fresh cache
    prompts_mod.load_system.cache_clear()


def test_format_user_inlines_transcript():
    transcript = "## user\n\nhello\n\n## assistant\n\nhi back"
    out = format_user(transcript=transcript, language_hint="auto")
    assert "hello" in out
    assert "hi back" in out


def test_format_user_inlines_language_hint():
    out = format_user(transcript="x", language_hint="uk")
    assert 'language_hint="uk"' in out


def test_format_user_no_unsubstituted_placeholders():
    out = format_user(transcript="x", language_hint="auto")
    assert not re.search(r"\{transcript\}|\{language_hint\}", out)


def test_format_user_handles_curly_braces_in_transcript():
    # Transcripts contain code with f-strings, JSON, etc. — braces must pass through literally.
    transcript = 'Some Python: f"{user.name}" and JSON: {"key": "value"} and {missing_var}'
    out = format_user(transcript=transcript, language_hint="auto")
    assert 'f"{user.name}"' in out
    assert '{"key": "value"}' in out
    assert "{missing_var}" in out


def test_format_user_handles_transcript_containing_template_marker_text():
    # Transcript shouldn't accidentally re-substitute `{transcript}` literal text.
    transcript = "Discussing the {transcript} placeholder syntax"
    out = format_user(transcript=transcript, language_hint="auto")
    # The literal "{transcript}" inside the transcript must remain there.
    assert "{transcript}" in out
