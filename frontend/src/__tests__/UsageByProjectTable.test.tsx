import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { UsageByProjectTable } from "../components/widgets/UsageByProjectTable";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      by_project_title: "Per project",
      col_project: "Project",
      col_sessions: "Sessions",
      col_tokens_input: "Input",
      col_tokens_output: "Output",
      col_tokens_per_byte: "tok/B",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const ROWS = [
  {
    project: "alpha", period_days: 30, sessions_covered: 12,
    tokens_input: 100, tokens_output: 200, tokens_injected: 50,
    raw_bytes_total: 1024, tokens_per_byte: 0.293,
  },
];

describe("UsageByProjectTable", () => {
  it("renders header + row", () => {
    render(<MemoryRouter><UsageByProjectTable rows={ROWS} /></MemoryRouter>);
    expect(screen.getByText("Per project")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<MemoryRouter><UsageByProjectTable rows={[]} /></MemoryRouter>);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
