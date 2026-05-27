import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";

const GLOBAL_FACTORY = (locale: "uk" | "ru" | "en") => ({
  version: 1,
  locale,
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
});

vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

// Mock useProjects so the picker has data without hitting the network
vi.mock("@/hooks/useProjects", () => ({
  useProjects: () => ({ data: [], isLoading: false }),
}));

const { default: i18n } = await import("../i18n");
const { TopBar } = await import("../components/layout/TopBar");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      topbar: {
        all_projects: "All projects",
        global_links: {
          lost_sessions: "Lost Sessions",
          failed_jobs: "Failed Jobs",
          metrics: "Metrics",
          help: "Help",
          global_settings: "Global Settings",
        },
      },
      common: { loading: "Loading…" },
      navigation: { create_project: "+ New project" },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "/settings/global") return { data: GLOBAL_FACTORY("uk") };
    if (url === "/usage/me") return { data: null };
    return { data: null };
  });
});

function renderTopBar(initialPath = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TopBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TopBar", () => {
  it("renders the brand", () => {
    render(wrap(<TopBar />));
    // Brand is split into two spans: "claude" / "mnemos"
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("mnemos")).toBeInTheDocument();
  });

  it("locale switcher PATCHes /settings/global with the next locale", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/settings/global") return { data: GLOBAL_FACTORY("uk") };
      throw new Error(`unexpected GET ${url}`);
    });
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: GLOBAL_FACTORY("ru"),
    });
    render(wrap(<TopBar />));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "UK" })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "UK" }));
    await waitFor(() =>
      expect(patchSpy).toHaveBeenCalledWith("/settings/global", { locale: "ru" }),
    );
  });
});

describe("TopBar global links", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders five global navigation links", () => {
    renderTopBar();
    expect(screen.getByRole("link", { name: /lost sessions/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /failed jobs/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /metrics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /help/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /global settings/i })).toBeInTheDocument();
  });

  it("links point at the right routes", () => {
    renderTopBar();
    expect(screen.getByRole("link", { name: /lost sessions/i })).toHaveAttribute("href", "/lost-sessions");
    expect(screen.getByRole("link", { name: /failed jobs/i })).toHaveAttribute("href", "/dead-letter");
    expect(screen.getByRole("link", { name: /metrics/i })).toHaveAttribute("href", "/metrics");
    expect(screen.getByRole("link", { name: /help/i })).toHaveAttribute("href", "/help");
    expect(screen.getByRole("link", { name: /global settings/i })).toHaveAttribute("href", "/settings/global");
  });
});
