import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProvenanceIndicator } from "../components/widgets/ProvenanceIndicator";

describe("ProvenanceIndicator", () => {
  it("renders percentages from _pct fields", () => {
    render(
      <ProvenanceIndicator
        counts={{ extracted_pct: 70, inferred_pct: 20, ambiguous_pct: 10 }}
      />,
    );
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("renders nothing when counts is null", () => {
    const { container } = render(<ProvenanceIndicator counts={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when all pct are zero", () => {
    const { container } = render(
      <ProvenanceIndicator
        counts={{ extracted_pct: 0, inferred_pct: 0, ambiguous_pct: 0 }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
