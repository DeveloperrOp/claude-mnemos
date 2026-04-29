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
      col_compression: "Compression",
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
    avg_compression_ratio: null, inject_events_count: 0, valid_events_count: 0,
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

  it("renders compression column when ratio is non-null", () => {
    const row = {
      project: "alpha",
      period_days: 30,
      sessions_covered: 10,
      tokens_input: 100,
      tokens_output: 200,
      tokens_injected: 50,
      raw_bytes_total: 1024,
      tokens_per_byte: 0.293,
      avg_compression_ratio: 4.5,
      inject_events_count: 7,
      valid_events_count: 7,
    };
    render(<MemoryRouter><UsageByProjectTable rows={[row]} /></MemoryRouter>);
    expect(screen.getByText(/4\.5/)).toBeInTheDocument();
  });

  it("renders dash in compression column when ratio is null", () => {
    const row = {
      project: "alpha",
      period_days: 30,
      sessions_covered: 0,
      tokens_input: 0,
      tokens_output: 0,
      tokens_injected: 0,
      raw_bytes_total: 0,
      tokens_per_byte: null,
      avg_compression_ratio: null,
      inject_events_count: 0,
      valid_events_count: 0,
    };
    render(<MemoryRouter><UsageByProjectTable rows={[row]} /></MemoryRouter>);
    expect(screen.getByText(/Compression/i)).toBeInTheDocument();
  });
});
