import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Help } from "../pages/Help";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    help: {
      title: "Help",
      nav: { quickstart: "Quickstart", concepts: "Concepts", workflows: "Workflows", troubleshooting: "Troubleshooting", about: "About" },
      quickstart: { heading: "Quickstart", intro: "go", step1_title: "1.", step1_body: "a", step2_title: "2.", step2_body: "b", step3_title: "3.", step3_body: "c" },
      concepts: { heading: "Concepts", intro: "i",
        projects_title: "Projects", projects_body: "p",
        sessions_title: "Sessions", sessions_body: "s",
        pages_title: "Pages", pages_body: "pg",
        suggestions_title: "Suggestions", suggestions_body: "sg",
        snapshots_title: "Snapshots", snapshots_body: "sn",
        deadletter_title: "Failed jobs", deadletter_body: "dl" },
      workflows: { heading: "Common workflows", intro: "i",
        ingest_title: "Daily ingest", ingest_body: "x",
        snapshot_title: "Snap", snapshot_body: "y",
        restore_title: "Restore", restore_body: "z" },
      troubleshooting: { heading: "Troubleshooting", intro: "i",
        daemon_down_title: "Daemon down", daemon_down_body: "x",
        ingest_failing_title: "Ingest failing", ingest_failing_body: "y",
        mount_failed_title: "Mount", mount_failed_body: "z" },
      about: { heading: "About", version_label: "Version", links: "Links", github: "GitHub", spec: "Spec", issues: "Report" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>;
}

describe("Help", () => {
  it("renders all 5 section headings", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { status: "ok", version: "0.1.0", uptime_s: 0, scheduler_jobs: [], alerts_count: 0, vaults: {}, jobs_alert: false },
    });
    render(wrap(<Help />));
    await waitFor(() => expect(screen.getByText("Help")).toBeInTheDocument());
    // Verify section headings in the content grid (skip nav sidebar)
    const sections = screen.getAllByText((content, element) => {
      if (!element || !element.className) return false;
      return typeof content === 'string' && element.className.includes('section-rail');
    });
    expect(sections.length).toBeGreaterThanOrEqual(5);
  });

  it("displays version from useHealth", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { status: "ok", version: "1.2.3", uptime_s: 0, scheduler_jobs: [], alerts_count: 0, vaults: {}, jobs_alert: false },
    });
    render(wrap(<Help />));
    await waitFor(() => expect(screen.getByText(/1\.2\.3/)).toBeInTheDocument());
  });
});
