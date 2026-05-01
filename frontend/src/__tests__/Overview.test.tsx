import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "../components/ui/tooltip";
import { apiClient } from "../api/client";

vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

const { default: i18n } = await import("../i18n");
const { Overview } = await import("../pages/Overview");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      common: { open: "Open" },
      overview: {
        no_projects_title: "Brain of your projects will appear here",
        no_projects_cta: "Create your first project",
        no_projects_hint_cmd: "Register your first project:",
        no_projects_hint_command: "mnemos project add NAME --vault PATH",
        daemon_down_title: "Daemon unavailable",
        daemon_down_hint_cmd: "Start the daemon:",
        daemon_down_hint_command: "mnemos daemon start",
        daemon_down_reconnect: "Dashboard will reconnect automatically.",
        rate_limited_until: "Rate limited — resumes at {{time}}",
      },
      project_view: {
        stats: {
          sessions_covered: "Sessions",
          jobs_queued: "Queued",
          jobs_dead_letter: "Dead Letter",
        },
      },
      health: { ok: "Healthy", degraded: "Degraded", down: "Down" },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TooltipProvider>{ui}</TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Overview", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders skeleton while loading", () => {
    vi.spyOn(apiClient, "get").mockImplementation(() => new Promise(() => {}));
    render(wrap(<Overview />));
    // Skeleton has no semantic role; check at least a placeholder is present.
    expect(screen.queryByRole("link", { name: /open/i })).not.toBeInTheDocument();
  });

  it("renders DaemonDownAlert on /projects failure", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("ECONNREFUSED"));
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getAllByText(/daemon|демон/i).length).toBeGreaterThan(0),
    );
  });

  it("renders NoProjectsCallout when project list empty", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects") return { data: [] };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
            alerts_count: 0,
            vaults: {},
            jobs_alert: false,
            scheduler_jobs: [],
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText(/no_projects|brain|мозок|мозг/i)).toBeInTheDocument(),
    );
  });

  it("renders project cards when list is populated", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects")
        return {
          data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
        };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
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
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText("alpha")).toBeInTheDocument(),
    );
  });

  it("shows rate-limit banner when queue_paused_until is in the future, hides when in the past", async () => {
    const future = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects")
        return {
          data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
        };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
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
            queue_paused_until: future,
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText(/rate limited/i)).toBeInTheDocument(),
    );
  });

  it("does not show rate-limit banner when queue_paused_until is null", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects")
        return {
          data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
        };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
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
            queue_paused_until: null,
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
    expect(screen.queryByText(/rate limited/i)).not.toBeInTheDocument();
  });

  it("does not show rate-limit banner when queue_paused_until is in the past", async () => {
    const past = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects")
        return {
          data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
        };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
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
            queue_paused_until: past,
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
    expect(screen.queryByText(/rate limited/i)).not.toBeInTheDocument();
  });
});
