import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import {
  getProjectSettings,
  patchProjectSettings,
  getGlobalSettings,
  patchGlobalSettings,
} from "../api/settings.api";

const FULL_PROJECT = {
  version: 1,
  auto_ingest: {},
  lint: { schedule: null, enabled_rules: null },
  snapshots: { schedule: "daily", retention_days: 180 },
};

const FULL_GLOBAL = {
  version: 1,
  locale: "uk",
  daemon_port: 5757,
  default_model: "claude-sonnet-4-6",
  default_language_hint: "auto",
  default_max_input_tokens: 150000,
  default_retention_days: 180,
  auto_ingest_defaults: {
    dump_on_session_end: true,
    dump_stale_after_24h: true,
    extract_after_dump: false,
  },
};

describe("settings API", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "get");
    vi.spyOn(apiClient, "patch");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("getProjectSettings parses full payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL_PROJECT });
    const result = await getProjectSettings("p1");
    expect(apiClient.get).toHaveBeenCalledWith("/settings/p1");
    expect(result.auto_ingest.dump_on_session_end).toBeNull();
    expect(result.snapshots.retention_days).toBe(180);
  });

  it("patchProjectSettings sends partial body", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL_PROJECT, snapshots: { schedule: "daily", retention_days: 30 } },
    });
    const result = await patchProjectSettings("p1", { snapshots: { retention_days: 30 } });
    expect(apiClient.patch).toHaveBeenCalledWith("/settings/p1", { snapshots: { retention_days: 30 } });
    expect(result.snapshots.retention_days).toBe(30);
  });

  it("getGlobalSettings parses payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL_GLOBAL });
    const g = await getGlobalSettings();
    expect(apiClient.get).toHaveBeenCalledWith("/settings/global");
    expect(g.daemon_port).toBe(5757);
    expect(g.default_model).toBe("claude-sonnet-4-6");
  });

  it("patchGlobalSettings sends partial", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL_GLOBAL, daemon_port: 6000 },
    });
    const g = await patchGlobalSettings({ daemon_port: 6000 });
    expect(apiClient.patch).toHaveBeenCalledWith("/settings/global", { daemon_port: 6000 });
    expect(g.daemon_port).toBe(6000);
  });

  // v0.0.31: legacy v0.0.9 fields (`enabled`, `mode`) and per-project
  // `locale` were dropped from both the backend Pydantic model and the
  // Zod schema. Old on-disk JSON still contains them — z.object()
  // strips unknown keys by default, so loading must not throw.
  it("getProjectSettings tolerates legacy fields in payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        version: 1,
        locale: "ru",
        auto_ingest: {
          enabled: null,
          mode: null,
          dump_on_session_end: null,
          dump_stale_after_24h: null,
          extract_after_dump: null,
        },
        lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
        snapshots: { schedule: "daily", retention_days: 180 },
      },
    });
    const result = await getProjectSettings("p1");
    expect(result.auto_ingest.dump_on_session_end).toBeNull();
    expect(result.auto_ingest.extract_after_dump).toBeNull();
    // Dropped fields are absent on the parsed object.
    expect((result.auto_ingest as Record<string, unknown>).enabled).toBeUndefined();
    expect(result).not.toHaveProperty("locale");
  });
});
