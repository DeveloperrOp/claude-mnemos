import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { TooltipProvider } from "../components/ui/tooltip";

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
const { Sidebar } = await import("../components/layout/Sidebar");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      navigation: {
        overview: "Overview",
        pages: "Pages",
        sessions: "Sessions",
        queue: "Queue",
        activity: "Activity",
        suggestions: "Suggestions",
        lost_sessions: "Lost Sessions",
        trash: "Trash",
        snapshots: "Snapshots",
        health: "Health",
        settings: "Settings",
        metrics: "Metrics",
        help: "Help",
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

describe("Sidebar", () => {
  it("highlights Overview on /", () => {
    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );
    const overview = screen.getByRole("link", { name: /overview|огляд|обзор/i });
    expect(overview).toHaveAttribute("aria-current", "page");
  });

  it("shows project section disabled when no project active", () => {
    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );
    // Per-project nav links are present but render as disabled (data-disabled).
    const pages = screen.queryByText(/pages|сторінки|страницы/i);
    expect(pages).toBeInTheDocument();
    expect(pages!.closest("[data-disabled]")).toBeInTheDocument();
  });

  it("activates project links when on /project/:name", () => {
    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/project/alpha/pages"]}>
          <Routes>
            <Route path="/project/:name/*" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );
    const pages = screen.getByRole("link", { name: /pages|сторінки|страницы/i });
    expect(pages).toHaveAttribute("aria-current", "page");
  });
});
