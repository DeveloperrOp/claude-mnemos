import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";

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
const { UsageWidget } = await import("../components/widgets/UsageWidget");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    { usage: { title: "Usage", no_data: "No data yet" } },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("UsageWidget", () => {
  it("formats tokens injected and ratio", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        total_tokens_injected: 8234,
        tokens_full: 47356,
        sessions_covered: 5,
        avg_compression_ratio: 5.75,
        events_count: 5,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() => expect(screen.getByText(/8\.2K/)).toBeInTheDocument());
    expect(screen.getByText(/×5\.8/)).toBeInTheDocument();
    expect(screen.getAllByText(/5/).length).toBeGreaterThan(0);
  });

  it("shows 'no data' when usage is empty", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        total_tokens_injected: 0,
        tokens_full: 0,
        sessions_covered: 0,
        avg_compression_ratio: 0,
        events_count: 0,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(screen.getByText(/no_data|no data/i)).toBeInTheDocument(),
    );
  });
});
