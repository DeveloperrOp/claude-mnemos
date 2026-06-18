import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { JobRow } from "@/pages/Queue";
import type { Job } from "@/types/Job";

const baseJob: Job = {
  id: "job-0001-abcdef",
  kind: "extract",
  payload: {},
  status: "succeeded",
  attempt: 1,
  next_attempt_at: "2026-06-18T00:00:00Z",
  created_at: "2026-06-18T00:00:00Z",
  started_at: "2026-06-18T00:00:01Z",
  finished_at: "2026-06-18T00:00:02Z",
  error: null,
  error_traceback: null,
  warning: null,
  project_name: "demo",
};

function renderRow(job: Job) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobRow job={job} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("JobRow warning chip", () => {
  it("shows an amber warning when job.warning is set", async () => {
    renderRow({ ...baseJob, status: "succeeded", warning: "no LLM client available" });
    const chip = await screen.findByTestId("job-warning");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent(/no LLM client available/i);
    expect(chip.className).toContain("text-amber-600");
  });

  it("renders no warning chip when job.warning is null", () => {
    renderRow({ ...baseJob, status: "succeeded", warning: null });
    expect(screen.queryByTestId("job-warning")).toBeNull();
  });
});
