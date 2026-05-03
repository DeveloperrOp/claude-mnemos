import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { RunningJobsLive } from "../../components/widgets/dashboard/RunningJobsLive";
import type { RunningJob } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      running: {
        title: "Running now",
        elapsed: "{{seconds}}s elapsed",
        empty: "😴 Nothing running",
      },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("RunningJobsLive", () => {
  it("shows empty state when no jobs", () => {
    render(wrap(<RunningJobsLive jobs={[]} />));
    expect(screen.getByText(/Nothing running/)).toBeDefined();
  });

  it("renders each running job with project + elapsed", () => {
    const now = Date.now();
    const jobs: RunningJob[] = [
      {
        id: "j1",
        kind: "ingest",
        status: "running",
        project_name: "alpha",
        started_at: new Date(now - 12_000).toISOString(),
      },
    ];
    render(wrap(<RunningJobsLive jobs={jobs} />));
    expect(screen.getByText(/ingest/)).toBeDefined();
    expect(screen.getByText(/alpha/)).toBeDefined();
  });
});
