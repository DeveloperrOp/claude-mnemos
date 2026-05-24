"""CLI provider — drives ``claude -p`` subprocess for extraction.

Uses the user's Claude Code subscription (Pro/Max) via OAuth, no separate
ANTHROPIC_API_KEY needed. Token counts are approximate (tiktoken proxy)
since the CLI JSON envelope doesn't expose exact usage figures.

See docs/plans/2026-04-30-llm-cli-provider-design.md §5 for rationale.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from typing import Any

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ExtractionRaw,
    LLMExtractionError,
)
from claude_mnemos.ingest.llm.auth import find_claude_binary
from claude_mnemos.ingest.llm.rate_limit import parse_rate_limit_from_stderr
from claude_mnemos.ingest.llm.tokens import count_tokens_local

DEFAULT_TIMEOUT_SEC = 120
DEFAULT_MAX_TURNS = 5
"""Maximum tool-use turns per extract call. Must be ≥2 so the CLI can
complete a tool_use → result loop. 5 accommodates validation retries
(the validator can ask the model to fix a bad payload up to 2 times)."""


def _build_env() -> dict[str, str]:
    """Copy os.environ minus vars that would derail subprocess auth.

    - CLAUDECODE / CLAUDE_CODE_ENTRYPOINT: parent-session markers; their
      presence makes ``claude -p`` refuse to run (recursion guard).
    - ANTHROPIC_API_KEY: if set, claude CLI prefers it over OAuth subscription
      → user gets billed per-token instead of subscription quota. We strip
      it to force subscription path. Users who explicitly want API mode use
      ``ApiLLMClient`` (selected by factory when ``ingest_provider == "api"``).
    """
    env = os.environ.copy()
    for var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY"):
        env.pop(var, None)
    return env


class CliLLMClient:
    """LLMClient implementation backed by ``claude -p`` subprocess."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        binary = find_claude_binary()
        if binary is None:
            raise LLMExtractionError(
                "claude binary not found on PATH; install Claude Code or "
                "switch to ApiLLMClient via ingest_provider='api'"
            )

        payload = self._call_once(str(binary), system, user, tool)

        first_validation_error: Exception | None = None
        if validate is not None:
            try:
                validate(payload)
                return self._build_result(system, user, payload)
            except Exception as exc:  # noqa: BLE001
                first_validation_error = exc
        else:
            return self._build_result(system, user, payload)

        # Retry once with the validation error appended (mirrors ApiLLMClient).
        retry_user = (
            user
            + "\n\n---\n\n"
            + f"ATTENTION: A previous attempt to call {tool['name']} failed schema validation: "
            + str(first_validation_error)
            + f". Please call {tool['name']} again with a corrected payload "
            + "that strictly matches the tool's input_schema."
        )
        try:
            payload2 = self._call_once(str(binary), system, retry_user, tool)
        except LLMExtractionError as exc:
            raise LLMExtractionError(
                f"retry after validation failure also failed: {exc}"
            ) from exc

        try:
            validate(payload2)
        except Exception as exc:  # noqa: BLE001
            raise LLMExtractionError(
                f"LLM tool input failed validation twice: first={first_validation_error}, "
                f"second={exc}"
            ) from exc
        return self._build_result(system, retry_user, payload2)

    def _call_once(
        self,
        binary: str,
        system: str,
        user: str,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        cmd = [
            binary,
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(tool["input_schema"]),
            "--system-prompt", system,
            "--setting-sources", "",
            "--no-session-persistence",
            "--max-turns", str(DEFAULT_MAX_TURNS),
        ]
        try:
            result = subprocess.run(
                cmd,
                input=user,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=DEFAULT_TIMEOUT_SEC,
                check=False,
                env=_build_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMExtractionError(
                f"claude -p timed out after {DEFAULT_TIMEOUT_SEC}s"
            ) from exc

        if result.returncode != 0:
            rate_err = parse_rate_limit_from_stderr(result.stderr)
            if rate_err is not None:
                raise rate_err
            raise LLMExtractionError(
                f"claude -p exit {result.returncode}: {result.stderr.strip()[:500]}"
            )

        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LLMExtractionError(
                f"claude -p returned invalid JSON: {exc}"
            ) from exc

        structured = envelope.get("structured_output")
        if structured is None:
            raise LLMExtractionError(
                "claude -p response missing structured_output field"
            )
        return dict(structured)

    def _build_result(
        self,
        system: str,
        user: str,
        payload: dict[str, Any],
    ) -> ExtractionRaw:
        # Token counts are approximate (cl100k proxy). UI marks them with `~` prefix.
        input_tokens = count_tokens_local(system) + count_tokens_local(user)
        output_tokens = count_tokens_local(json.dumps(payload, ensure_ascii=False))
        return ExtractionRaw(
            payload=payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
