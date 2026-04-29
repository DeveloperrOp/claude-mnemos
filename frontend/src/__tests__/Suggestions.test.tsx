import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Suggestions } from "../pages/Suggestions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: {
      cancel: "Cancel",
      confirm: "Confirm",
      working: "Working...",
      typed_confirm_input_placeholder: "Type {{phrase}} to confirm",
    },
    suggestions: {
      title: "Suggestions",
      filter_status: "Status",
      status: { pending: "Pending", approved: "Approved", rejected: "Rejected", deferred: "Deferred", all: "All" },
      operation: { merge_entities: "Merge", rename_entity: "Rename", delete_page: "Delete" },
      confidence: "Confidence", affected_pages: "Affected", proposed_target: "Target",
      reason: "Reason", body_header: "Reasoning",
      no_suggestions: "No suggestions",
      showing_n: "{{count}} suggestions",
      approved_toast: "Suggestion approved",
      rejected_toast: "Suggestion rejected",
      deferred_toast: "Suggestion deferred",
      approve_button: "Approve",
      reject_button: "Reject",
      defer_button: "Defer",
      approve_modal_title: "Apply suggestion?",
      approve_modal_desc: "This will execute the {{operation}} operation on {{count}} affected pages.",
      approve_delete_modal_title: "Apply delete-page suggestion?",
      approve_delete_modal_desc: "This will permanently delete the page from the vault. Type the page name to confirm.",
      approve_delete_typed_label: "Type the page name",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/suggestions"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/suggestions" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Suggestions", () => {
  it("renders suggestions", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        suggestions: [
          {
            frontmatter: {
              id: "ont-2026-04-29-abc",
              created: "2026-04-29T12:00:00Z",
              operation: "merge_entities",
              status: "pending",
              confidence: 0.85,
              affected_pages: ["wiki/x.md", "wiki/y.md"],
              proposed_target: "wiki/x.md",
              reason: "duplicate",
              applied_at: null,
              applied_op_id: null,
            },
            body: "## Reasoning\n\ndetails",
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getByText("ont-2026-04-29-abc")).toBeInTheDocument());
    expect(screen.getByText("Merge")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { suggestions: [], total: 0 } });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getByText(/no suggestions/i)).toBeInTheDocument());
  });
});
