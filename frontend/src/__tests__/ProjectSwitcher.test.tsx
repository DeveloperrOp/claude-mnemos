import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
const { ProjectSwitcher } = await import("../components/layout/ProjectSwitcher");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    { common: { loading: "Loading..." }, topbar: { all_projects: "All projects" } },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/project/:name" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ProjectSwitcher", () => {
  it("renders 'all projects' label when on /", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
    });
    render(wrap(<ProjectSwitcher />));
    await waitFor(() => {
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });

  it("opens menu and lists projects", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [
        { name: "alpha", vault_root: "/a", cwd_patterns: [] },
        { name: "beta", vault_root: "/b", cwd_patterns: [] },
      ],
    });
    const user = userEvent.setup();
    render(wrap(<ProjectSwitcher />));
    await waitFor(() => screen.getByRole("button"));
    await user.click(screen.getByRole("button"));
    expect(await screen.findByText("alpha")).toBeInTheDocument();
    expect(await screen.findByText("beta")).toBeInTheDocument();
  });
});
