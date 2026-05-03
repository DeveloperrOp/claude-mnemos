import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import {
  getHealthAlerts,
  postSilenceAlert,
  postDismissAlert,
} from "../api/health_alerts.api";
import { HealthAlertSchema } from "../types/HealthAlert";

const ALERT = {
  id: "auto_dump_overdue",
  detector: "auto_dump_overdue",
  severity: "warning",
  message: "Auto-dump overdue by 180 min.",
  context: { overdue_seconds: 10800 },
  first_seen: "2026-05-03T10:00:00Z",
  last_seen: "2026-05-03T10:05:00Z",
  silenced_until: null,
  dismissed: false,
};

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("health alerts api", () => {
  afterEach(() => vi.resetAllMocks());

  it("HealthAlertSchema parses a backend payload", () => {
    const parsed = HealthAlertSchema.parse(ALERT);
    expect(parsed.severity).toBe("warning");
    expect(parsed.dismissed).toBe(false);
  });

  it("HealthAlertSchema rejects unknown severity", () => {
    expect(() =>
      HealthAlertSchema.parse({ ...ALERT, severity: "bogus" }),
    ).toThrow();
  });

  it("getHealthAlerts parses {alerts, silenced} response", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { alerts: [ALERT], silenced: [] },
    });
    const r = await getHealthAlerts();
    expect(r.alerts).toHaveLength(1);
    expect(r.alerts[0].id).toBe("auto_dump_overdue");
    expect(r.silenced).toHaveLength(0);
  });

  it("postSilenceAlert posts duration body", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok" } });
    await postSilenceAlert("auto_dump_overdue", { duration_hours: 24 });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/health-alerts/auto_dump_overdue/silence",
      { duration_hours: 24 },
    );
  });

  it("postDismissAlert posts to dismiss endpoint", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok" } });
    await postDismissAlert("auto_dump_overdue");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/health-alerts/auto_dump_overdue/dismiss",
    );
  });

  it("encodes special chars in alert id", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok" } });
    await postDismissAlert("a/b");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/health-alerts/a%2Fb/dismiss",
    );
  });
});
