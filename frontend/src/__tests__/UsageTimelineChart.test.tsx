import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { UsageTimelineChart } from "../components/widgets/UsageTimelineChart";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      timeline_legend_input: "Input tokens",
      timeline_legend_output: "Output tokens",
      timeline_legend_sessions: "Sessions",
      timeline_empty: "No data in this period",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const POINTS = [
  { date: "2026-04-29", sessions: 3, tokens_input: 100, tokens_output: 200 },
  { date: "2026-04-30", sessions: 5, tokens_input: 150, tokens_output: 250 },
];

describe("UsageTimelineChart", () => {
  it("renders legend labels with non-empty data", () => {
    render(<UsageTimelineChart points={POINTS} />);
    expect(screen.getByText("Input tokens")).toBeInTheDocument();
    expect(screen.getByText("Output tokens")).toBeInTheDocument();
    expect(screen.getByText("Sessions")).toBeInTheDocument();
  });

  it("renders empty state when all points are zero", () => {
    const empty = POINTS.map((p) => ({ ...p, sessions: 0, tokens_input: 0, tokens_output: 0 }));
    render(<UsageTimelineChart points={empty} />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });

  it("renders empty state when points array is empty", () => {
    render(<UsageTimelineChart points={[]} />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
