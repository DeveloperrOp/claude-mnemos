import re

from claude_mnemos.core.slug import make_slug


def test_basic_ascii_lowercase():
    assert make_slug("Claude Code") == "claude-code"


def test_uppercase_normalized():
    assert make_slug("FOO BAR") == "foo-bar"


def test_punctuation_collapsed_to_dash():
    assert make_slug("Hello, World!") == "hello-world"


def test_multiple_spaces_collapsed():
    assert make_slug("a   b   c") == "a-b-c"


def test_leading_trailing_dashes_stripped():
    assert make_slug("---abc---") == "abc"


def test_unicode_transliterated_to_ascii():
    out = make_slug("Українська страница")
    assert out.isascii()
    assert re.fullmatch(r"[a-z0-9-]+", out)
    assert len(out) > 0


def test_russian_transliterated_to_ascii():
    out = make_slug("Атомарная запись")
    assert out.isascii()
    assert re.fullmatch(r"[a-z0-9-]+", out)


def test_truncates_to_60_chars_at_word_boundary():
    long_title = " ".join(["wordone"] * 20)
    out = make_slug(long_title)
    assert len(out) <= 60
    assert not out.startswith("-")
    assert not out.endswith("-")


def test_empty_string_returns_untitled_with_hash():
    out = make_slug("")
    assert out.startswith("untitled-")
    assert len(out) == len("untitled-") + 8


def test_whitespace_only_returns_untitled():
    out = make_slug("   \t\n  ")
    assert out.startswith("untitled-")


def test_idempotent():
    s = make_slug("Some Title With Spaces")
    assert make_slug(s) == s


def test_pure_emoji_returns_untitled():
    out = make_slug("🎉🎊")
    assert out.startswith("untitled-")


def test_mixed_emoji_and_text_keeps_text():
    out = make_slug("Hello 🎉 World")
    assert "hello" in out
    assert "world" in out
    assert out.isascii()


def test_underscore_treated_as_separator():
    assert make_slug("snake_case_name") == "snake-case-name"


def test_numbers_preserved():
    assert make_slug("Plan 2 v3") == "plan-2-v3"


def test_untitled_hash_deterministic_per_input():
    assert make_slug("") == make_slug("")
    assert make_slug("🎉") == make_slug("🎉")
