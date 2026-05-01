import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { BlinkCursor } from "../BlinkCursor";

describe("BlinkCursor", () => {
  it("renders the U+258C glyph", () => {
    const { container } = render(<BlinkCursor />);
    expect(container.textContent).toBe("▌");
  });

  it("forwards aria-hidden=true (decorative)", () => {
    const { container } = render(<BlinkCursor />);
    const span = container.querySelector("span");
    expect(span?.getAttribute("aria-hidden")).toBe("true");
  });
});
