import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import Lint from "../pages/Lint";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      breadcrumb: { lint: "lint" },
      lint: {
        title: "Lint",
        run_button: "Run lint",
        running: "Running",
        autofix_button: "Auto-fix ({{count}})",
        autofix_running: "Fixing",
        autofix_submit: "Apply auto-fixes",
        autofix_confirm_title: "Apply auto-fixes?",
        autofix_confirm_body: "{{count}} fixable",
        fixable_badge: "Fix",
        last_run: "Last run: {{time}}",
        run_toast: "Done {{findings}}",
        autofix_toast: "Fixed: {{fixed}}, skipped: {{skipped}}",
        empty: {
          title: "Lint has not run yet",
          body: "Click Run lint",
        },
        clean: {
          title: "Vault is clean",
          body: "Zero findings",
        },
        summary: { total: "Total", fixable: "Fixable" },
        severity: { error: "Error", warning: "Warning", info: "Info" },
        rules: {
          wikilinks_broken: "Broken wikilinks",
          orphan_pages: "Orphan pages",
        },
      },
      confirm: { cancel: "Cancel", working: "Working" },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/lint"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route
            path="/project/:name/lint"
            element={<Suspense fallback={null}>{ui}</Suspense>}
          />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const SAMPLE_REPORT = {
  version: 1,
  run_id: "abc123",
  started_at: "2026-05-22T10:00:00Z",
  finished_at: "2026-05-22T10:00:05Z",
  vault_root: "/tmp/alpha",
  rule_versions: { wikilinks_broken: "v1", orphan_pages: "v1" },
  summary: {
    total: 3,
    by_severity: { error: 1, warning: 2 },
    by_rule: { wikilinks_broken: 2, orphan_pages: 1 },
    fixable_count: 1,
  },
  findings: [
    {
      id: "wikilinks_broken:abc",
      rule_id: "wikilinks_broken",
      severity: "warning",
      message: "broken wikilink [[foo]] (likely typo of [[fool]])",
      page_path: "wiki/concepts/page1.md",
      fixable: true,
      fix_kind: "fix_wikilink_typo",
      metadata: { target: "foo", candidate: "fool" },
    },
    {
      id: "wikilinks_broken:def",
      rule_id: "wikilinks_broken",
      severity: "warning",
      message: "broken wikilink [[bar]]",
      page_path: "wiki/concepts/page2.md",
      fixable: false,
      fix_kind: null,
      metadata: { target: "bar", candidate: null },
    },
    {
      id: "orphan_pages:ghi",
      rule_id: "orphan_pages",
      severity: "error",
      message: "page has no incoming wikilinks (orphan)",
      page_path: "wiki/concepts/page3.md",
      fixable: false,
      fix_kind: null,
      metadata: {},
    },
  ],
};

describe("Lint page", () => {
  it("shows empty state when no run yet (404)", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({
      response: { status: 404 },
    });
    render(wrap(<Lint />));
    await waitFor(() =>
      expect(screen.getByText("Lint has not run yet")).toBeInTheDocument(),
    );
  });

  it("renders findings grouped by rule when results present", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: SAMPLE_REPORT });
    render(wrap(<Lint />));
    await waitFor(() => expect(screen.getByText("Orphan pages")).toBeInTheDocument());
    expect(screen.getByText("Broken wikilinks")).toBeInTheDocument();
    // Group order: error severity first → orphan_pages on top, expanded by default,
    // so its single finding's message should be in the DOM.
    expect(
      screen.getByText("page has no incoming wikilinks (orphan)"),
    ).toBeInTheDocument();
  });

  it("disables autofix button when fixable_count is 0", async () => {
    const cleanReport = {
      ...SAMPLE_REPORT,
      summary: { ...SAMPLE_REPORT.summary, fixable_count: 0 },
    };
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: cleanReport });
    render(wrap(<Lint />));
    await waitFor(() => expect(screen.getByText(/Auto-fix \(0\)/)).toBeInTheDocument());
    const btn = screen.getByText(/Auto-fix \(0\)/).closest("button");
    expect(btn).toBeDisabled();
  });

  it("shows clean empty state when zero findings", async () => {
    const cleanReport = {
      ...SAMPLE_REPORT,
      summary: { total: 0, by_severity: {}, by_rule: {}, fixable_count: 0 },
      findings: [],
    };
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: cleanReport });
    render(wrap(<Lint />));
    await waitFor(() => expect(screen.getByText("Vault is clean")).toBeInTheDocument());
  });
});
