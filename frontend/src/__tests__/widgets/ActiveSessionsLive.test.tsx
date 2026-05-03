import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { ActiveSessionsLive } from "../../components/widgets/dashboard/ActiveSessionsLive";
import type { ActiveSession } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      active: {
        title: "Active sessions",
        empty: "No active sessions",
        dump_now_button: "Dump now",
        read_button: "Read",
        auto_dump_in: "auto-dump in {{remaining}}",
        auto_dump_overdue: "auto-dump pending",
      },
    },
    lost_sessions: {
      selection: { unassigned_label: "unassigned" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

vi.mock("../../api/client", () => ({
  apiClient: { post: vi.fn() },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

const HOT: ActiveSession = {
  session_id: "abcd1234efgh",
  transcript_path: "C:/x.jsonl",
  sha: "deadbeef",
  project_name: "alpha",
  cwd: "D:/code/alpha",
  preview: "hello",
  mtime: new Date(Date.now() - 5 * 60_000).toISOString(),
  size_bytes: 1024,
  status: "hot",
  auto_dump_at: null,
};

const COOLING: ActiveSession = {
  ...HOT,
  session_id: "cool0001",
  status: "cooling",
  mtime: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
  auto_dump_at: new Date(Date.now() + 22 * 60 * 60_000).toISOString(),
};

describe("ActiveSessionsLive", () => {
  it("shows empty state when no sessions", () => {
    render(wrap(<ActiveSessionsLive sessions={[]} />));
    expect(screen.getByText(/No active sessions/)).toBeDefined();
  });

  it("groups by project and renders rows", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT, COOLING]} />));
    expect(screen.getAllByText(/alpha/).length).toBeGreaterThan(0);
    expect(screen.getByText(/abcd1234/)).toBeDefined();
  });

  it("renders countdown for cooling sessions only", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT, COOLING]} />));
    expect(screen.getByText(/auto-dump in/)).toBeDefined();
  });

  it("Dump now button is present for assigned sessions", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT]} />));
    expect(screen.getByRole("button", { name: /Dump now/i })).toBeDefined();
  });
});
