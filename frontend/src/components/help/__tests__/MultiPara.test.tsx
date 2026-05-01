import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MultiPara } from "../MultiPara";

describe("MultiPara", () => {
  it("renders paragraphs separated by \\n\\n", () => {
    const { container } = render(<MultiPara value={`One.\n\nTwo.\n\nThree.`} />);
    const ps = container.querySelectorAll("p");
    expect(ps).toHaveLength(3);
    expect(ps[0]?.textContent).toContain("One.");
    expect(ps[1]?.textContent).toContain("Two.");
    expect(ps[2]?.textContent).toContain("Three.");
  });

  it("wraps backtick-fenced inline text in <code>", () => {
    render(<MultiPara value="Run `mnemos daemon stop` to halt." />);
    const code = screen.getByText("mnemos daemon stop");
    expect(code.tagName).toBe("CODE");
    expect(code.className).toMatch(/font-mono/);
  });

  it("wraps **double-asterisk** text in <strong>", () => {
    render(<MultiPara value="The **Inject** operation runs at start." />);
    const bold = screen.getByText("Inject");
    expect(bold.tagName).toBe("STRONG");
  });

  it("handles backticks and bold in the same paragraph", () => {
    render(<MultiPara value="**Important:** run `mnemos daemon foreground` first." />);
    expect(screen.getByText("Important:").tagName).toBe("STRONG");
    expect(screen.getByText("mnemos daemon foreground").tagName).toBe("CODE");
  });

  it("leaves text without markdown unchanged", () => {
    const { container } = render(<MultiPara value="Plain text without any markup." />);
    expect(container.querySelector("code")).toBeNull();
    expect(container.querySelector("strong")).toBeNull();
    expect(container.textContent).toContain("Plain text without any markup.");
  });

  it("does NOT recursively parse bold inside code", () => {
    // **bold** literally inside backticks should remain as text **bold**.
    render(<MultiPara value="Type `**raw**` to see it." />);
    const code = screen.getByText("**raw**");
    expect(code.tagName).toBe("CODE");
    // Confirm there's no <strong> nested
    expect(code.querySelector("strong")).toBeNull();
  });
});
