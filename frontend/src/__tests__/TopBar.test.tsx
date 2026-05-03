import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useUIStore } from "../stores/ui.store";

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
const { TopBar } = await import("../components/layout/TopBar");

beforeAll(async () => {
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

describe("TopBar", () => {
  it("renders the brand", () => {
    render(wrap(<TopBar />));
    // Brand is split into two spans: "claude" / "mnemos"
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("mnemos")).toBeInTheDocument();
  });

  it("locale switcher cycles uk → ru → en → uk", async () => {
    const user = userEvent.setup();
    useUIStore.setState({ locale: "uk", sidebarCollapsed: false, theme: "light" });
    render(wrap(<TopBar />));
    const btn = screen.getByRole("button", { name: /uk/i });
    await user.click(btn);
    expect(useUIStore.getState().locale).toBe("ru");
    await user.click(screen.getByRole("button", { name: /ru/i }));
    expect(useUIStore.getState().locale).toBe("en");
    await user.click(screen.getByRole("button", { name: /en/i }));
    expect(useUIStore.getState().locale).toBe("uk");
  });
});
