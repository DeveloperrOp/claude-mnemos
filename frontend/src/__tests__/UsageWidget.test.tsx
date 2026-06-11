import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "../components/ui/tooltip";
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
    {
      usage: { title: "Usage", no_data: "No data yet" },
      metrics: {
        inject_events: "{{count}} inject events",
        avg_compression: "{{ratio}}× avg compression",
      },
    },
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
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>{ui}</TooltipProvider>
    </QueryClientProvider>
  );
}

describe("UsageWidget", () => {
  it("queries the 30d period so tooltips tell the truth", async () => {
    const spy = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "30d",
        period_days: 30,
        sessions_covered: 1,
        tokens_input: 100,
        tokens_output: 200,
        tokens_injected: 300,
        raw_bytes_total: 1024,
        tokens_per_byte: 0.293,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("/metrics/usage", {
        params: { period: "30d" },
      }),
    );
  });

  it("formats tokens injected and sessions covered", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        period_days: 1,
        sessions_covered: 5,
        tokens_input: 5000,
        tokens_output: 3234,
        tokens_injected: 8234,
        raw_bytes_total: 65536,
        tokens_per_byte: 0.0494,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() => expect(screen.getByText(/8\.2K/)).toBeInTheDocument());
    // sessions_covered shown
    expect(screen.getAllByText(/5/).length).toBeGreaterThan(0);
    // tokens_per_byte shown as "0.05 tok/B"
    expect(screen.getByText(/tok\/B/)).toBeInTheDocument();
  });

  it("hides tokens_per_byte when null", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        period_days: 1,
        sessions_covered: 3,
        tokens_input: 400,
        tokens_output: 200,
        tokens_injected: 600,
        raw_bytes_total: 0,
        tokens_per_byte: null,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() => expect(screen.getByText(/600/)).toBeInTheDocument());
    expect(screen.queryByText(/tok\/B/)).not.toBeInTheDocument();
  });

  it("shows 'no data' when usage is empty", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        period_days: 1,
        sessions_covered: 0,
        tokens_input: 0,
        tokens_output: 0,
        tokens_injected: 0,
        raw_bytes_total: 0,
        tokens_per_byte: null,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(screen.getByText(/no_data|no data/i)).toBeInTheDocument(),
    );
  });

  it("renders inject events + compression ratio when present", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "30d",
        period_days: 30,
        sessions_covered: 12,
        tokens_input: 100,
        tokens_output: 200,
        tokens_injected: 50,
        raw_bytes_total: 1024,
        tokens_per_byte: 0.293,
        avg_compression_ratio: 6.3,
        inject_events_count: 47,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(screen.getByText(/47 inject events/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/6\.3× avg compression/)).toBeInTheDocument();
  });

  it("renders zero events without ratio text", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "30d",
        period_days: 30,
        sessions_covered: 4,
        tokens_input: 100,
        tokens_output: 200,
        tokens_injected: 50,
        raw_bytes_total: 1024,
        tokens_per_byte: 0.293,
        avg_compression_ratio: null,
        inject_events_count: 0,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(screen.getByText(/0 inject events/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/avg compression/)).not.toBeInTheDocument();
  });
});
