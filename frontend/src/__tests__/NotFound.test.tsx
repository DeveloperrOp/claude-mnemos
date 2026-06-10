import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

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
const { NotFound } = await import("../pages/NotFound");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      not_found: {
        title: "Page not found",
        hint: "There is no such page.",
        back_link: "Back to Overview",
      },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", () => resolve()));
  }
  await i18n.changeLanguage("en");
});

describe("NotFound", () => {
  it("renders a friendly message and a link home, not a raw stack trace", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Page not found");
    const link = screen.getByRole("link", { name: "Back to Overview" });
    expect(link).toHaveAttribute("href", "/");
    // Guard against React Router's default ErrorBoundary copy leaking through.
    expect(screen.queryByText(/Unexpected Application Error/i)).toBeNull();
  });
});
