import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricLabel } from "../MetricLabel";

describe("MetricLabel", () => {
  it("renders LABEL ▸ value pattern", () => {
    render(<MetricLabel label="JOBS">03 queued</MetricLabel>);
    expect(screen.getByText("JOBS")).toBeInTheDocument();
    expect(screen.getByText("▸")).toBeInTheDocument();
    expect(screen.getByText("03 queued")).toBeInTheDocument();
  });

  it("applies mono uppercase to the label", () => {
    render(<MetricLabel label="JOBS">03</MetricLabel>);
    const labelEl = screen.getByText("JOBS");
    expect(labelEl.className).toMatch(/font-mono/);
    expect(labelEl.className).toMatch(/uppercase/);
  });
});
