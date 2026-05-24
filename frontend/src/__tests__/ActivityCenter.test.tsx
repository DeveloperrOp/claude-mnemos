import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ActivityCenter } from "../pages/ActivityCenter";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      breadcrumb: { activity: "activity" },
      activity: {
        title: "Activity",
        groups: {
          needs_attention: "Needs attention",
          today: "Today",
          yesterday: "Yesterday",
          earlier_week: "This week",
          older: "Older",
        },
        op: { ingest: "Ingest", manual_patch: "Manual edit" },
        affected_pages: "{{count}} pages",
        detail: "Detail",
        undo_button: "Undo",
        undone_toast: "Operation undone",
        undo_modal_title: "Undo this operation?",
        undo_modal_desc: "This will revert all pages affected by this operation to their state before it ran.",
        no_activity: "No activity",
        empty: { title: "No operations yet", body: "body" },
      },
      confirm: {
        cancel: "Cancel", working: "Working…",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/activity"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/activity" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ActivityCenter", () => {
  it("renders entries grouped", async () => {
    const today = new Date().toISOString();
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        entries: [
          {
            id: "op-1",
            timestamp: today,
            operation_type: "ingest",
            status: "success",
            snapshot_path: null,
            can_undo: true,
            undone: false,
            undone_at: null,
            undone_by_id: null,
            affected_pages: ["wiki/a.md"],
            metadata: {},
          },
        ],
        total: 1,
      },
    });
    render(wrap(<ActivityCenter />));
    await waitFor(() => expect(screen.getByText("Today")).toBeInTheDocument());
    expect(screen.getByText("Ingest")).toBeInTheDocument();
  });

  it("shows empty state with page header (P1-5: header in empty state)", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { entries: [], total: 0 },
    });
    render(wrap(<ActivityCenter />));
    await waitFor(() =>
      expect(screen.getByText(/no operations yet/i)).toBeInTheDocument(),
    );
    // P1-5: header (h1 "Activity") and breadcrumb must render even when empty.
    expect(screen.getByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByText(/claude-mnemos/i)).toBeInTheDocument();
  });
});
