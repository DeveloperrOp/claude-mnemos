import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock HttpBackend so i18n never makes real HTTP requests.
vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

// Import after mock is registered.
const { default: i18n } = await import("../i18n");
const { default: App } = await import("../App");

beforeAll(async () => {
  // Provide inline translations so t() resolves to real strings.
  i18n.addResourceBundle("uk", "translation", { common: { open: "Відкрити" } }, true, true);
  i18n.addResourceBundle("ru", "translation", { common: { open: "Открыть" } }, true, true);
  i18n.addResourceBundle("en", "translation", { common: { open: "Open" } }, true, true);
  // Wait for i18n to initialize (it will since backend never blocks).
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
});

describe("i18n", () => {
  it("renders Ukrainian by default after detection", async () => {
    await i18n.changeLanguage("uk");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("Відкрити"),
    );
  });

  it("switches language at runtime", async () => {
    await i18n.changeLanguage("en");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("Open"),
    );
  });
});
