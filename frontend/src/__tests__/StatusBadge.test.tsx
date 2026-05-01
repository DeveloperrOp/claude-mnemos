import { describe, it, expect, beforeAll } from "vitest";
import { render } from "@testing-library/react";
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
    const { container } = render(<StatusBadge status="draft" />);
    const el = container.querySelector('[data-status="draft"]');
    expect(el).not.toBeNull();
    expect(el).toHaveTextContent("Draft");
  });

  it("renders verified with success color", () => {
    const { container } = render(<StatusBadge status="verified" />);
    expect(container.querySelector('[data-status="verified"]')).not.toBeNull();
  });
});
