import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
const { default: App } = await import("../App");

beforeAll(async () => {
  i18n.addResourceBundle("en", "translation", { common: { open: "Open" } }, true, true);
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

describe("App smoke", () => {
  it("renders the Layout shell", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("banner")).toBeInTheDocument(),
    );
    expect(screen.getByText("claude-mnemos")).toBeInTheDocument();
  });
});
