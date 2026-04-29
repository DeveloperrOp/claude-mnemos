import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { CompressionTimelineChart } from "../components/widgets/CompressionTimelineChart";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      compression_timeline_legend_events: "Inject events",
      compression_timeline_legend_ratio: "Avg ratio",
      compression_timeline_empty: "No inject events in this period",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const POINTS = [
  { date: "2026-04-27", events_count: 2, valid_events_count: 2, avg_compression_ratio: 4.0 },
  { date: "2026-04-28", events_count: 1, valid_events_count: 1, avg_compression_ratio: 5.0 },
];

describe("CompressionTimelineChart", () => {
  it("renders legend labels with non-empty data", () => {
    render(<CompressionTimelineChart points={POINTS} />);
    expect(screen.getByText("Inject events")).toBeInTheDocument();
    expect(screen.getByText("Avg ratio")).toBeInTheDocument();
  });

  it("renders empty state when all points are zero", () => {
    const empty = POINTS.map((p) => ({ ...p, events_count: 0, valid_events_count: 0, avg_compression_ratio: null }));
    render(<CompressionTimelineChart points={empty} />);
    expect(screen.getByText(/no inject events/i)).toBeInTheDocument();
  });

  it("renders empty state when points array is empty", () => {
    render(<CompressionTimelineChart points={[]} />);
    expect(screen.getByText(/no inject events/i)).toBeInTheDocument();
  });
});
