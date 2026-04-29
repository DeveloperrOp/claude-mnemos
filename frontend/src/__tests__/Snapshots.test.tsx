import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Snapshots } from "../pages/Snapshots";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    snapshots: {
      title: "Snapshots",
      kind: { "pre-op": "Pre-op", daily: "Daily", manual: "Manual", all: "All" },
      filter_kind: "Kind",
      label: "label", op_id: "op", op_type: "type", size: "size",
      no_snapshots: "No snapshots", showing_n: "{{count}} snapshots",
      restore_disabled: "Restore (#14c)", delete_disabled: "Delete (#14c)",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/snapshots"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/snapshots" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const SAMPLE = [
  {
    name: "pre-op-2026-04-29-12-00-00-abc-ingest",
    kind: "pre-op",
    timestamp: "2026-04-29T12:00:00Z",
    op_id: "abc",
    op_type: "ingest",
    label: null,
    size_bytes: 1024,
    path: ".backups/pre-op-2026-04-29-12-00-00-abc-ingest",
  },
  {
    name: "daily-2026-04-29-04-00-00",
    kind: "daily",
    timestamp: "2026-04-29T04:00:00Z",
    op_id: null,
    op_type: null,
    label: null,
    size_bytes: 2048,
    path: ".backups/daily-2026-04-29-04-00-00",
  },
];

describe("Snapshots", () => {
  it("renders cards from list", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { snapshots: SAMPLE } });
    render(wrap(<Snapshots />));
    await waitFor(() =>
      expect(
        screen.getByText("pre-op-2026-04-29-12-00-00-abc-ingest"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("daily-2026-04-29-04-00-00")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { snapshots: [] } });
    render(wrap(<Snapshots />));
    await waitFor(() =>
      expect(screen.getByText(/no snapshots/i)).toBeInTheDocument(),
    );
  });
});
