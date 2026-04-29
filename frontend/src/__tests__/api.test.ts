import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listProjects } from "../api/projects.api";
import { getHealth } from "../api/health.api";
import { getUsage } from "../api/metrics.api";

describe("api", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "get");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("listProjects parses an array of ProjectMapEntry", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
    });
    const list = await listProjects();
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe("alpha");
  });

  it("listProjects rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [{ wrong: 1 }] });
    await expect(listProjects()).rejects.toThrow();
  });

  it("getHealth parses the per-vault dict shape", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        status: "ok",
        version: "0.1",
        uptime_s: 12,
        alerts_count: 0,
        vaults: {
          alpha: {
            watchdog_running: true,
            jobs_queued: 0,
            jobs_running: 0,
            jobs_dead_letter: 0,
          },
        },
        jobs_alert: false,
        scheduler_jobs: [],
      },
    });
    const h = await getHealth();
    expect(h.status).toBe("ok");
    expect(h.vaults.alpha?.watchdog_running).toBe(true);
  });

  it("getUsage parses summary shape", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        period: "30d",
        period_days: 30,
        sessions_covered: 10,
        tokens_input: 600,
        tokens_output: 400,
        tokens_injected: 1000,
        raw_bytes_total: 8192,
        tokens_per_byte: 0.049,
      },
    });
    const u = await getUsage("30d");
    expect(u.sessions_covered).toBe(10);
    expect(u.tokens_injected).toBe(1000);
  });
});
