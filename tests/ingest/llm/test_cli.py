from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ExtractionRaw,
    LLMExtractionError,
    ModelNotFoundError,
    TranscriptTooLargeError,
)
from claude_mnemos.ingest.llm.cli import CliLLMClient
from claude_mnemos.ingest.llm.rate_limit import RateLimitError


@pytest.fixture
def cfg() -> Config:
    return Config(
        api_key=None,
        model="claude-sonnet-4-5",
        language_hint="auto",
        max_input_tokens=180000,
        lock_timeout=30.0,
    )


@pytest.fixture
def cfg_known() -> Config:
    """cfg whose model IS in KNOWN_MODELS_NEWEST_FIRST, so fallback_model()
    can resolve a different id (needed to exercise the fallback path)."""
    return Config(
        api_key=None,
        model="claude-opus-4-8",
        language_hint="auto",
        max_input_tokens=180000,
        lock_timeout=30.0,
    )


def _stub_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


_TOOL_SCHEMA = {
    "name": "save_pages",
    "description": "Save extracted pages",
    "input_schema": {
        "type": "object",
        "properties": {"pages": {"type": "array"}},
        "required": ["pages"],
    },
}


def _ok_envelope(payload: dict[str, Any]) -> str:
    return json.dumps({
        "result": "extracted",
        "session_id": "abc",
        "structured_output": payload,
        "cost_usd": 0.001,
        "duration_ms": 1234,
        "num_turns": 1,
    })


def test_extract_invokes_claude_p_with_correct_args(cfg: Config) -> None:
    from pathlib import Path
    payload = {"pages": [], "summary": "ok"}
    binary_path = Path("/usr/bin/claude")
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=binary_path):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        client = CliLLMClient(cfg)
        result = client.extract(system="SYS", user="USR", tool=_TOOL_SCHEMA)

    assert isinstance(result, ExtractionRaw)
    assert result.payload == payload

    cmd = run.call_args[0][0]
    assert cmd[0] == str(binary_path)
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--json-schema" in cmd
    assert "--system-prompt" in cmd
    assert "--setting-sources" in cmd
    # v0.0.39: the configured model is now passed explicitly so the picker
    # actually controls CLI extraction (was previously subscription default).
    midx = cmd.index("--model")
    assert cmd[midx + 1] == cfg.model


def test_extract_falls_back_when_model_rejected(cfg_known: Config) -> None:
    """If claude -p rejects the configured model as unknown, the client retries
    once with fallback_model() and the second invocation uses the fallback id."""
    from pathlib import Path

    from claude_mnemos.config import fallback_model

    payload = {"pages": []}
    with (
        patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run,
        patch(
            "claude_mnemos.ingest.llm.cli.find_claude_binary",
            return_value=Path("/x/claude"),
        ),
    ):
        run.side_effect = [
            _stub_completed(1, stderr='API Error: 404 {"type":"not_found_error"}'),
            _stub_completed(0, stdout=_ok_envelope(payload)),
        ]
        result = CliLLMClient(cfg_known).extract(
            system="S", user="U", tool=_TOOL_SCHEMA,
        )

    assert result.payload == payload
    assert run.call_count == 2
    fb = fallback_model(cfg_known.model)
    assert fb != cfg_known.model
    second_cmd = run.call_args_list[1][0][0]
    midx = second_cmd.index("--model")
    assert second_cmd[midx + 1] == fb


def test_extract_raises_model_not_found_when_no_fallback(cfg: Config) -> None:
    """An unknown model id outside KNOWN_MODELS has no fallback — the error
    propagates as ModelNotFoundError (still an LLMExtractionError subclass)."""
    with (
        patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run,
        patch(
            "claude_mnemos.ingest.llm.cli.find_claude_binary",
            return_value=__import__("pathlib").Path("/x/claude"),
        ),
    ):
        run.return_value = _stub_completed(
            1, stderr='API Error: 404 {"type":"not_found_error"}'
        )
        with pytest.raises(ModelNotFoundError):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
        # cfg.model is not in the known set → no second attempt.
        assert run.call_count == 1


def test_extract_uses_default_max_turns(cfg: Config) -> None:
    """--max-turns must be ≥2 so Claude CLI can complete a tool_use → result loop.

    Plan Phase A (2026-05-24): previously hardcoded to 1, which broke any
    json-schema flow — CLI made the tool call on turn 1 but couldn't return
    the structured output without a second turn, surfacing as 'claude -p
    exit 1: ' with empty stderr.
    """
    from pathlib import Path

    from claude_mnemos.ingest.llm.cli import DEFAULT_MAX_TURNS

    assert DEFAULT_MAX_TURNS >= 2, (
        f"DEFAULT_MAX_TURNS={DEFAULT_MAX_TURNS} too low — tool_use needs ≥2 turns"
    )

    payload = {"pages": [], "summary": "ok"}
    with (
        patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run,
        patch(
            "claude_mnemos.ingest.llm.cli.find_claude_binary",
            return_value=Path("/usr/bin/claude"),
        ),
    ):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        CliLLMClient(cfg).extract(system="SYS", user="USR", tool=_TOOL_SCHEMA)

    cmd = run.call_args[0][0]
    idx = cmd.index("--max-turns")
    assert cmd[idx + 1] == str(DEFAULT_MAX_TURNS)
    assert "--no-session-persistence" in cmd
    assert "--max-turns" in cmd

    # System prompt passed as flag value
    sys_idx = cmd.index("--system-prompt")
    assert cmd[sys_idx + 1] == "SYS"

    # JSON schema is the tool's input_schema serialized
    schema_idx = cmd.index("--json-schema")
    parsed_schema = json.loads(cmd[schema_idx + 1])
    assert parsed_schema == _TOOL_SCHEMA["input_schema"]


def test_extract_passes_user_prompt_via_stdin(cfg: Config) -> None:
    """Critical: Windows CMD truncates multiline argv at first LF.
    User prompt MUST go through stdin."""
    payload = {"pages": []}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/usr/bin/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        CliLLMClient(cfg).extract(system="S", user="multiline\nuser\nprompt", tool=_TOOL_SCHEMA)
    assert run.call_args.kwargs["input"] == "multiline\nuser\nprompt"


def test_extract_clears_recursion_env_vars(cfg: Config) -> None:
    payload = {"pages": []}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")), \
         patch.dict("os.environ", {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x",
                                    "ANTHROPIC_API_KEY": "sk-leak"}):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
    env = run.call_args.kwargs["env"]
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    # ANTHROPIC_API_KEY MUST be removed — otherwise CLI bills via API not subscription
    assert "ANTHROPIC_API_KEY" not in env


def test_extract_returns_approximate_token_counts(cfg: Config) -> None:
    payload = {"pages": [{"slug": "x"}]}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        result = CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
    assert result.input_tokens > 0  # local approximation, non-zero for non-empty text
    assert result.output_tokens > 0


def test_extract_raises_rate_limit_on_429_stderr(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(1, stderr="HTTP 429 Too Many Requests")
        with pytest.raises(RateLimitError):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_extraction_error_on_other_failure(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(1, stderr="something else broke")
        with pytest.raises(LLMExtractionError):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_when_binary_missing(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.find_claude_binary", return_value=None), \
         pytest.raises(LLMExtractionError, match="claude binary not found"):
        CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_retries_once_on_validation_failure(cfg: Config) -> None:
    bad_payload = {"wrong": "shape"}
    good_payload = {"pages": []}

    def validator(p: dict) -> None:
        if "pages" not in p:
            raise ValueError("schema mismatch")

    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.side_effect = [
            _stub_completed(0, stdout=_ok_envelope(bad_payload)),
            _stub_completed(0, stdout=_ok_envelope(good_payload)),
        ]
        result = CliLLMClient(cfg).extract(
            system="S", user="U", tool=_TOOL_SCHEMA, validate=validator,
        )
    assert result.payload == good_payload
    assert run.call_count == 2


def test_extract_raises_after_two_validation_failures(cfg: Config) -> None:
    def always_fail(p: dict) -> None:
        raise ValueError("nope")

    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope({"any": "shape"}))
        with pytest.raises(LLMExtractionError, match="failed validation twice"):
            CliLLMClient(cfg).extract(
                system="S", user="U", tool=_TOOL_SCHEMA, validate=always_fail,
            )


def test_extract_raises_on_invalid_json_envelope(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout="not json at all")
        with pytest.raises(LLMExtractionError, match="invalid JSON"):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_when_structured_output_missing(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        # no structured_output field in envelope
        run.return_value = _stub_completed(0, stdout=json.dumps({"result": "x"}))
        with pytest.raises(LLMExtractionError, match="structured_output"):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_precounts_and_raises_before_subprocess() -> None:
    """An oversized prompt must raise TranscriptTooLargeError BEFORE any
    subprocess work — the user's default subscription path previously had no
    limit check and a too-big session just timed out at 600s."""
    small_cfg = Config(
        api_key=None,
        model="claude-sonnet-4-5",
        language_hint="auto",
        max_input_tokens=10,
        lock_timeout=30.0,
    )
    big_user = "word " * 5000  # far above a 10-token budget
    with (
        patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run,
        patch(
            "claude_mnemos.ingest.llm.cli.find_claude_binary",
            return_value=__import__("pathlib").Path("/x/claude"),
        ),
        pytest.raises(TranscriptTooLargeError) as ei,
    ):
        CliLLMClient(small_cfg).extract(
            system="S", user=big_user, tool=_TOOL_SCHEMA,
        )

    err = ei.value
    assert err.max_input_tokens == small_cfg.max_input_tokens == 10
    assert err.input_tokens > err.max_input_tokens
    # The whole point: the paid/blocking subprocess must NOT run.
    run.assert_not_called()


def test_extract_within_budget_does_not_raise_and_runs_subprocess(cfg: Config) -> None:
    """A within-budget prompt must NOT trip the pre-count guard and DOES invoke
    the subprocess (cfg.max_input_tokens default 180000 is generous)."""
    payload = {"pages": []}
    with (
        patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run,
        patch(
            "claude_mnemos.ingest.llm.cli.find_claude_binary",
            return_value=__import__("pathlib").Path("/x/claude"),
        ),
    ):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        result = CliLLMClient(cfg).extract(
            system="short system", user="short user", tool=_TOOL_SCHEMA,
        )
    assert result.payload == payload
    run.assert_called_once()
