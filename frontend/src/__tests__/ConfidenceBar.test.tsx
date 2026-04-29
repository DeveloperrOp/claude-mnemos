import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBar } from "../components/widgets/ConfidenceBar";

describe("ConfidenceBar", () => {
  it("renders percentage label", () => {
    render(<ConfidenceBar value={0.7} />);
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("clamps fill width to 0-100%", () => {
    render(<ConfidenceBar value={1.5} />);
    const fill = screen.getByTestId("confidence-fill");
    expect(fill).toHaveStyle({ width: "100%" });
  });

  it("renders 0% for zero", () => {
    render(<ConfidenceBar value={0} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
