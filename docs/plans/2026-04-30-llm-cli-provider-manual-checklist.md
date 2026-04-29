# LLM CLI Provider — Manual E2E Checklist

These checks cannot run in CI (require real Claude Code login). Run by hand on Yarik's Win11 machine after merge.

## Prerequisites
- [ ] `claude login` completed (or `CLAUDE_CODE_OAUTH_TOKEN` env set)
- [ ] No `ANTHROPIC_API_KEY` env var (verify: `echo $ANTHROPIC_API_KEY` empty)
- [ ] Branch `feat/llm-cli-provider` (or `main` after merge), `pip install -e .` done

## Auth preflight
- [ ] `mnemos --help` works (CLI installed)
- [ ] Open dashboard at http://localhost:5757/
- [ ] Onboarding wizard (`/onboarding`) shows green «Claude CLI installed and authenticated»
- [ ] `curl http://localhost:5757/health/claude-cli` → 200 with `{"installed":true,"authenticated":true,...}`

## CLI mode ingest (no API key)
- [ ] `MNEMOS_INGEST_PROVIDER` unset (auto-detect picks CLI when no `ANTHROPIC_API_KEY`)
- [ ] Create a test project via dashboard pointing at a real Claude Code session vault
- [ ] Trigger ingest of one session via dashboard «Sessions → Ingest»
- [ ] Job appears in /jobs with status=running, then completed
- [ ] Resulting markdown pages exist in vault under `wiki/`
- [ ] Pages contain reasonable extracted entities (not garbage)
- [ ] /metrics/usage shows token counts with `~` prefix where applicable (CLI ingests)

## Rate-limit pause (synthetic)
- [ ] Manually inject a `RateLimitError` by patching `CliLLMClient` at runtime, OR wait for natural rate hit during bulk ingest
- [ ] `curl http://localhost:5757/health` shows `queue_paused_until` non-null, in future
- [ ] Dashboard Overview shows amber banner «Rate limited — resumes at HH:MM»
- [ ] Worker does not pull new jobs while paused (verify via /jobs status or supervisor.log)
- [ ] Once `paused_until` passes, jobs resume automatically without restart

## API mode (legacy preservation)
- [ ] Set `ANTHROPIC_API_KEY=sk-...` and `MNEMOS_INGEST_PROVIDER=api`
- [ ] Restart daemon
- [ ] Ingest one session
- [ ] Token counts have NO `~` prefix in UI (exact via `count_tokens` API)
- [ ] /metrics/usage compression_ratio shows precise number (not approximate)

## Failure modes
- [ ] Stop `claude` daemon (e.g. log out from Claude Code) → /health/claude-cli reports `authenticated=false`
- [ ] Trigger ingest with CLI mode → graceful error in dashboard, job in dead-letter
- [ ] Re-login (`claude login`) → manual «Retry from dead-letter» works

## Recursion guard
- [ ] Run `mnemos ingest <session>` from inside a Claude Code session (terminal where `CLAUDECODE=1`)
- [ ] CLI subprocess receives clean env (`CliLLMClient._build_env()` strips `CLAUDECODE`/`CLAUDE_CODE_ENTRYPOINT`/`ANTHROPIC_API_KEY`)
- [ ] Ingest succeeds (not blocked by recursion check)

## Backward compatibility
- [ ] Existing tests pass: backend 1465+ pytest, frontend 196+ Vitest
- [ ] Existing vaults remain intact (no schema migrations break old data)
- [ ] Old `IngestRecord` entries with exact token counts continue to render correctly in metrics
