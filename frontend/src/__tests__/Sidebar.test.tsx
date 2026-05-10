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

describe("Sidebar (project-scoped)", () => {
  it("renders project nav items when on /project/:name route", async () => {
    const { default: i18n } = await import("../i18n");
    i18n.addResourceBundle("en", "translation", {
      navigation: {
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
    }, true, true);

    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/project/foo"]}>
          <Routes>
            <Route path="/project/:name/*" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );

    expect(screen.getByText("Project Overview")).toBeInTheDocument();
    expect(screen.getByText("Pages")).toBeInTheDocument();
    expect(screen.getByText("Sessions")).toBeInTheDocument();
    expect(screen.getByText("Queue")).toBeInTheDocument();
    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByText("Suggestions")).toBeInTheDocument();
    expect(screen.getByText("Trash")).toBeInTheDocument();
    expect(screen.getByText("Snapshots")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("does not render any disabled-looking items", () => {
    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/project/foo"]}>
          <Routes>
            <Route path="/project/:name/*" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );
    expect(document.querySelector("[data-disabled]")).toBeNull();
  });

  it("does not contain Lost Sessions, Metrics, Help, Failed Jobs, or Global Settings (they live in TopBar)", () => {
    render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/project/foo"]}>
          <Routes>
            <Route path="/project/:name/*" element={<Sidebar />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>,
    );
    expect(screen.queryByText(/lost sessions/i)).toBeNull();
    expect(screen.queryByText(/failed jobs/i)).toBeNull();
    expect(screen.queryByText(/metrics/i)).toBeNull();
    expect(screen.queryByText(/help/i)).toBeNull();
    expect(screen.queryByText(/global settings/i)).toBeNull();
  });

  it("returns null when there is no project context", () => {
    const { container } = render(
      <TooltipProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Sidebar />
        </MemoryRouter>
      </TooltipProvider>,
    );
    expect(container.querySelector("nav")).toBeNull();
  });
});
