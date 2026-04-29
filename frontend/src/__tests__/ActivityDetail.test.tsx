import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ActivityDetail } from "../pages/ActivityDetail";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      activity: {
        op: { ingest: "Ingest" },
        metadata: "Metadata",
        snapshot: "Snapshot",
        can_undo: "Can undo",
        cannot_undo: "Cannot undo",
        undone: "Undone",
        undo_disabled: "Undo (#14c)",
        affected_pages: "{{count}} pages",
        not_found_title: "Activity not found",
        not_found_hint: "Back",
      },
      navigation: { activity: "Activity" },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/activity/:opId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ActivityDetail", () => {
  it("renders entry with metadata + can_undo flag", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        id: "op-1",
        timestamp: "2026-04-29T12:00:00Z",
        operation_type: "ingest",
        status: "success",
        snapshot_path: ".backups/2026-04-29-pre-op-x",
        can_undo: true,
        undone: false,
        undone_at: null,
        undone_by_id: null,
        affected_pages: ["wiki/x.md"],
        metadata: { session_id: "s1" },
      },
    });
    render(wrap(<ActivityDetail />, "/project/alpha/activity/op-1"));
    await waitFor(() =>
      expect(screen.getByText("Ingest")).toBeInTheDocument(),
    );
    expect(screen.getByText("Can undo")).toBeInTheDocument();
    expect(screen.getByText(/session_id/)).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<ActivityDetail />, "/project/alpha/activity/missing"));
    await waitFor(() =>
      expect(screen.getByText(/Activity not found/i)).toBeInTheDocument(),
    );
  });
});
