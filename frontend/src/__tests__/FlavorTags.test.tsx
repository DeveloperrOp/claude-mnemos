import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { FlavorTags } from "../components/widgets/FlavorTags";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: { flavor: { pattern: "Pattern", mistake: "Mistake" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("FlavorTags", () => {
  it("renders one badge per flavor", () => {
    render(<FlavorTags flavors={["pattern", "mistake"]} />);
    expect(screen.getByText("Pattern")).toBeInTheDocument();
    expect(screen.getByText("Mistake")).toBeInTheDocument();
  });

  it("renders nothing when empty", () => {
    const { container } = render(<FlavorTags flavors={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
