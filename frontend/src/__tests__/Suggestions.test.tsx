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
      empty: { title: "No proposals pending", body: "body", cta: "mnemos ontology scan" },
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
      scan_button: "Scan vault",
      scan_running: "Scanning",
      scan_toast: "Scan done {{created}}/{{scanned}}",
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
    await waitFor(() => expect(screen.getByText(/no proposals pending/i)).toBeInTheDocument());
  });

  it("shows Scan button in toolbar and in empty state CTA", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { suggestions: [], total: 0 } });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getByText(/no proposals pending/i)).toBeInTheDocument());
    // Two "Scan vault" buttons: one in the toolbar, one in the empty-state CTA.
    const scanButtons = screen.getAllByText("Scan vault");
    expect(scanButtons.length).toBeGreaterThanOrEqual(2);
  });

  it("calls /scan endpoint when Scan button is clicked", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { suggestions: [], total: 0 } });
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: {
        created: ["ont-2026-05-22-abc"],
        skipped_existing: 0,
        skipped_distinct: 0,
        skipped_capped: 0,
        errors: [],
        scanned_pages: 5,
      },
    });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getAllByText("Scan vault").length).toBeGreaterThan(0));
    const btn = screen.getAllByText("Scan vault")[0];
    btn.click();
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith("/ontology/alpha/scan");
    });
  });
});
