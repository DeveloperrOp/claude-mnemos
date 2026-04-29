import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { StatusBadge } from "../components/widgets/StatusBadge";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: { status: { draft: "Draft", verified: "Verified" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("StatusBadge", () => {
  it("renders draft with neutral color", () => {
    render(<StatusBadge status="draft" />);
    const el = screen.getByRole("status");
    expect(el).toHaveAttribute("data-status", "draft");
    expect(el).toHaveTextContent("Draft");
  });

  it("renders verified with success color", () => {
    render(<StatusBadge status="verified" />);
    expect(screen.getByRole("status")).toHaveAttribute("data-status", "verified");
  });
});
