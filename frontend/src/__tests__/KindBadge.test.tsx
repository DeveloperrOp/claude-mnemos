import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { KindBadge } from "../components/widgets/KindBadge";

describe("KindBadge", () => {
  it("renders the label", () => {
    render(<KindBadge label="pre-op" tone="amber" />);
    expect(screen.getByText("pre-op")).toBeInTheDocument();
  });

  it("applies the tone via data-tone", () => {
    render(<KindBadge label="daily" tone="blue" />);
    expect(screen.getByText("daily")).toHaveAttribute("data-tone", "blue");
  });
});
