import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { getClaudeCliAuth } from "../api/claudeCli.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("Claude CLI auth API", () => {
  it("GET /health/claude-cli parses authenticated state", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: true,
      binary_path: "/usr/bin/claude",
    });
    const auth = await getClaudeCliAuth();
    expect(auth.installed).toBe(true);
    expect(auth.authenticated).toBe(true);
  });

  it("permissive parsing — missing binary_path defaults to null", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: false,
      authenticated: false,
    });
    const auth = await getClaudeCliAuth();
    expect(auth.binary_path).toBeNull();
  });
});
