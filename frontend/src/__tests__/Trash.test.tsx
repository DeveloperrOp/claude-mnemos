import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Trash } from "../pages/Trash";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    trash: {
      title: "Trash",
      deleted_at: "deleted at",
      operation_type: "op",
      restorable: "Restorable",
      blocked: "Blocked",
      no_entries: "No trash",
      showing_n: "{{count}} entries",
      restored_toast: "Restored",
      permanently_deleted_toast: "Permanently deleted",
      restore_modal_title: "Restore page?",
      restore_modal_desc: "Move {{name}} back.",
      restore_button: "Restore",
      delete_permanent_modal_title: "Permanently delete?",
      delete_permanent_modal_desc: "This cannot be undone.",
      delete_permanent_typed_label: "Type the page name",
      delete_permanent_button: "Delete forever",
    },
    confirm: {
      cancel: "Cancel",
      confirm: "Confirm",
      working: "Working...",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/trash"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/trash" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Trash", () => {
  it("renders entries", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        entries: [
          {
            trash_id: "t1",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: "wiki/concepts/foo.md",
            operation_type: "manual_delete",
            page_basename: "foo",
            restorable: true,
            restore_blocked_reason: null,
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Trash />));
    await waitFor(() => expect(screen.getByText("foo")).toBeInTheDocument());
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { entries: [], total: 0 } });
    render(wrap(<Trash />));
    await waitFor(() => expect(screen.getByText(/no trash/i)).toBeInTheDocument());
  });
});
