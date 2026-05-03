import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import {
  getDashboardSnapshot,
  postDumpNow,
  postScanActive,
} from "../api/dashboard.api";

const SNAPSHOT_FIXTURE = {
  kpi: {
    queue: { queued: 1, running: 0, failed: 0 },
    active: { hot: 1, cooling: 0 },
    today: { ingest_count: 0, pages_count: 0 },
    tokens_today: 0,
    lost_total: 1304,
  },
  active_sessions: [
    {
      session_id: "abc",
      transcript_path: "C:/x/abc.jsonl",
      sha: "deadbeef",
      project_name: "alpha",
      cwd: "D:/code/alpha",
      preview: "hi",
      mtime: "2026-05-03T10:00:00Z",
      size_bytes: 1024,
      status: "hot",
      auto_dump_at: "2026-05-04T10:00:00Z",
    },
  ],
  running_jobs: [],
  errors: [],
};

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("dashboard api", () => {
  afterEach(() => vi.resetAllMocks());

  it("getDashboardSnapshot parses payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: SNAPSHOT_FIXTURE });
    const r = await getDashboardSnapshot();
    expect(r.kpi.active.hot).toBe(1);
    expect(r.active_sessions[0].session_id).toBe("abc");
  });

  it("postDumpNow sends project_name in body", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { id: "j1", kind: "ingest", status: "queued" },
    });
    await postDumpNow("abc", { project_name: "alpha" });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/dashboard/active-sessions/abc/dump-now",
      { project_name: "alpha" },
    );
  });

  it("postScanActive returns scanned count", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { scanned: 3 } });
    const r = await postScanActive();
    expect(r.scanned).toBe(3);
  });

  it("getDashboardSnapshot rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { kpi: { queue: { queued: "not-a-number" } } },
    });
    await expect(getDashboardSnapshot()).rejects.toThrow();
  });
});
