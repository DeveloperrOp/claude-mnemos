import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
const { ProjectView } = await import("../pages/ProjectView");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      health: { ok: "Healthy", degraded: "Degraded", down: "Down" },
      project_view: {
        open_in_obsidian: "Open in Obsidian",
        unknown_title: "Project not found",
        unknown_hint: "is not registered.",
        coming_in: "Coming in {{plan}}",
        stats: {
          sessions_covered: "Sessions",
          jobs_queued: "Queued",
          jobs_running: "Running",
          jobs_dead_letter: "Dead Letter",
        },
      },
      navigation: {
        pages: "Pages",
        sessions: "Sessions",
        activity: "Activity",
        suggestions: "Suggestions",
        trash: "Trash",
        snapshots: "Snapshots",
        health: "Health",
        settings: "Settings",
      },
      placeholder: { back_link: "Back to Overview" },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const FAKE_PROJECTS_RESP = {
  data: [{ name: "alpha", vault_root: "D:/v/alpha", cwd_patterns: [] }],
};
const FAKE_HEALTH_RESP = {
  data: {
    status: "ok",
    version: "0.1",
    uptime_s: 0,
    alerts_count: 0,
    vaults: {
      alpha: {
        watchdog_running: true,
        jobs_queued: 1,
        jobs_running: 0,
        jobs_dead_letter: 0,
      },
    },
    jobs_alert: false,
    scheduler_jobs: [],
  },
};

describe("ProjectView", () => {
  it("renders header + stats + tiles for known project", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects") return FAKE_PROJECTS_RESP;
      if (url === "/health") return FAKE_HEALTH_RESP;
      return { data: { projects: [] } };
    });
    render(wrap(<ProjectView />, "/project/alpha"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "alpha" })).toBeInTheDocument(),
    );
    // Vault path visible
    expect(screen.getByText(/D:\/v\/alpha/)).toBeInTheDocument();
    // 8 navigation tiles
    expect(
      screen.getAllByRole("link").filter((l) =>
        l.getAttribute("href")?.startsWith("/project/alpha/"),
      ),
    ).toHaveLength(8);
  });

  it("renders UnknownProject when name is not in /projects", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    render(wrap(<ProjectView />, "/project/ghost"));
    await waitFor(() =>
      expect(screen.getByText(/unknown_title|not found|не найден|не знайдено/i))
        .toBeInTheDocument(),
    );
  });
});
