"""Each skill has a valid YAML frontmatter with required fields."""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"

EXPECTED_SKILLS = [
    "mnemos",
    "mnemos-status",
    "mnemos-search",
    "mnemos-undo",
    "mnemos-activity",
]


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with `---` frontmatter delimiter")
    end_marker = "\n---\n"
    end = text.find(end_marker, 4)
    if end < 0:
        raise AssertionError("SKILL.md missing closing `---` frontmatter delimiter")
    fm_text = text[4:end]
    body = text[end + len(end_marker) :]
    fm = yaml.safe_load(fm_text)
    if not isinstance(fm, dict):
        raise AssertionError("frontmatter must be a YAML mapping")
    return fm, body


@pytest.mark.parametrize("name", EXPECTED_SKILLS)
def test_skill_dir_exists(name):
    assert (SKILLS_ROOT / name / "SKILL.md").is_file(), (
        f"skills/{name}/SKILL.md is missing"
    )


@pytest.mark.parametrize("name", EXPECTED_SKILLS)
def test_skill_frontmatter_valid_yaml(name):
    text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    assert "name" in fm
    assert "description" in fm
    assert isinstance(fm["name"], str) and fm["name"]
    assert isinstance(fm["description"], str) and fm["description"]
    assert body.strip(), f"skills/{name}/SKILL.md has empty body"


@pytest.mark.parametrize("name", EXPECTED_SKILLS)
def test_skill_name_matches_directory(name):
    text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
    fm, _ = _split_frontmatter(text)
    assert fm["name"] == name, (
        f"skills/{name}/SKILL.md frontmatter name={fm['name']!r} "
        f"does not match directory name {name!r}"
    )


def test_subskills_have_argument_hint():
    """Sub-skills that take user input declare an argument-hint."""
    for name in ("mnemos-search", "mnemos-undo", "mnemos-activity"):
        text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
        fm, _ = _split_frontmatter(text)
        assert "argument-hint" in fm, f"{name} should declare argument-hint"
        assert isinstance(fm["argument-hint"], str)


def test_main_skill_has_no_argument_hint():
    """The main mnemos skill is behavioral, not a slash command."""
    text = (SKILLS_ROOT / "mnemos" / "SKILL.md").read_text(encoding="utf-8")
    fm, _ = _split_frontmatter(text)
    assert "argument-hint" not in fm
