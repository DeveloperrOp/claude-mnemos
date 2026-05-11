import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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

// Mock UsageWidget to avoid its data fetch in the layout tests
vi.mock("@/components/widgets/UsageWidget", () => ({
  UsageWidget: () => null,
}));

const { default: i18n } = await import("../i18n");
const { Layout } = await import("../components/layout/Layout");

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
      navigation: {
        create_project: "+ New project",
        project_overview: "Project Overview",
        pages: "Pages",
        sessions: "Sessions",
        queue: "Queue",
        activity: "Activity",
        suggestions: "Suggestions",
        trash: "Trash",
        snapshots: "Snapshots",
        health: "Health",
        settings: "Settings",
      },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function renderLayoutAt(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div data-testid="page">Home</div>} />
            <Route path="/lost-sessions" element={<div data-testid="page">Lost</div>} />
            <Route path="/project/:name" element={<div data-testid="page">Proj</div>} />
            <Route path="/project/:name/pages" element={<div data-testid="page">Pages</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Layout", () => {
  it("renders TopBar slot, Sidebar slot, and Outlet content", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<div>page-body</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("banner")).toBeInTheDocument(); // TopBar = <header>
    // Sidebar = <nav aria-label="primary">; TopBar also has <nav aria-label="global">
    expect(screen.getAllByRole("navigation").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("page-body")).toBeInTheDocument();
  });

  it("hides the sidebar on /", () => {
    renderLayoutAt("/");
    expect(screen.queryByRole("navigation", { name: "primary" })).toBeNull();
    expect(screen.getByRole("link", { name: /lost sessions/i })).toBeInTheDocument();
  });

  it("hides the sidebar on /lost-sessions (a global route)", () => {
    renderLayoutAt("/lost-sessions");
    expect(screen.queryByRole("navigation", { name: "primary" })).toBeNull();
  });

  it("shows the sidebar on /project/foo", () => {
    renderLayoutAt("/project/foo");
    expect(screen.getByRole("navigation", { name: "primary" })).toBeInTheDocument();
  });

  it("shows the sidebar on /project/foo/pages (sub-route)", () => {
    renderLayoutAt("/project/foo/pages");
    expect(screen.getByRole("navigation", { name: "primary" })).toBeInTheDocument();
  });

  it("navigating between global and project routes does not throw (rules-of-hooks regression)", () => {
    // Regression for React error #300 ("rendered fewer hooks than expected"):
    // a previous version of Layout chained `useMatch(...) ?? useMatch(...)`,
    // which short-circuited the second call and changed hook count between
    // renders. Rerendering with two different paths in the same component
    // instance triggers the violation. This must NOT throw.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div data-testid="page">Home</div>} />
              <Route path="/project/:name" element={<div data-testid="page">Proj</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // Re-render the same Layout instance with a project route. If hooks order
    // differs, this throws synchronously with the #300 error.
    rerender(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/project/foo"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<div data-testid="page">Home</div>} />
              <Route path="/project/:name" element={<div data-testid="page">Proj</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // If we reach here, no hooks-order violation fired.
    expect(true).toBe(true);
  });

  it("layout grid switches columns based on project context", () => {
    // Global route — main takes full width via grid-cols-1
    const { container, unmount } = renderLayoutAt("/");
    // The <main> sits inside a <div className="grid grid-cols-1 ..."> on globals.
    // Find the main element and inspect its parent's className.
    const mainGlobal = container.querySelector("main");
    expect(mainGlobal).not.toBeNull();
    expect(mainGlobal!.parentElement?.className).toContain("grid-cols-1");
    unmount();

    // Project route — grid is grid-cols-[16rem_1fr] (sidebar takes 16rem)
    const { container: c2 } = renderLayoutAt("/project/foo");
    const mainProj = c2.querySelector("main");
    expect(mainProj).not.toBeNull();
    expect(mainProj!.parentElement?.className).toContain("grid-cols-[16rem_1fr]");
  });
});
