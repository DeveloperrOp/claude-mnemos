import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { Placeholder } from "../pages/Placeholder";

vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

const { default: i18n } = await import("../i18n");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    { placeholder: { title: "{{section}}", body: "Coming in plan {{plan}}.", back_link: "Back to Overview" } },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

describe("Placeholder", () => {
  it("renders section title and plan reference", () => {
    render(
      <MemoryRouter>
        <Placeholder section="Pages" plan="#14b" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /pages/i })).toBeInTheDocument();
    expect(screen.getByText(/Coming in plan #14b/i)).toBeInTheDocument();
  });
});
