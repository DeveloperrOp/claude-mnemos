import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../../i18n";
import { apiClient } from "../../api/client";
import { InjectPreview } from "../../components/widgets/InjectPreview";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      inject_preview: {
        title: "INJECT CONTEXT",
        tokens_label: "tokens",
        limit_label: "limit",
        truncated: "TRUNCATED",
        pages_count: "Pages included ({{count}})",
        preview_show: "Show preview",
        preview_hide: "Hide preview",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const PAYLOAD = {
  tokens_estimate: 12500,
  limit: 50000,
  ratio: 0.25,
  pages: [
    {
      path: "wiki/concepts/foo.md",
      slug: "concepts/foo",
      score: 0.85,
      included: true,
    },
    {
      path: "wiki/concepts/bar.md",
      slug: "concepts/bar",
      score: 0.32,
      included: false,
    },
  ],
  preview_text: "# Project context (mnemos)\n\nSeed body for preview.",
  computed_at: "2026-05-03T20:00:00Z",
};

afterEach(() => vi.resetAllMocks());

describe("InjectPreview widget", () => {
  it("renders tokens, limit, pages count and progress bar (green zone)", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: PAYLOAD });
    render(wrap(<InjectPreview project="alpha" />));

    await waitFor(() =>
      expect(screen.getByTestId("inject-preview")).toBeDefined(),
    );
    expect(screen.getByText("INJECT CONTEXT")).toBeDefined();
    expect(screen.getByText("12.5K")).toBeDefined();
    expect(screen.getByText(/50.0K tokens/)).toBeDefined();
    expect(screen.getByText("Pages included (2)")).toBeDefined();

    const fill = screen.getByTestId("inject-preview-bar-fill");
    expect(fill.className).toMatch(/bg-success/);
    expect(screen.queryByTestId("inject-preview-truncated")).toBeNull();
  });

  it("uses amber bar in 75–100% zone", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      data: { ...PAYLOAD, ratio: 0.85 },
    });
    render(wrap(<InjectPreview project="alpha" />));
    await waitFor(() =>
      expect(screen.getByTestId("inject-preview")).toBeDefined(),
    );
    const fill = screen.getByTestId("inject-preview-bar-fill");
    expect(fill.className).toMatch(/bg-amber-500/);
  });

  it("uses destructive bar + TRUNCATED badge over 100%", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      data: { ...PAYLOAD, ratio: 1.4 },
    });
    render(wrap(<InjectPreview project="alpha" />));
    await waitFor(() =>
      expect(screen.getByTestId("inject-preview")).toBeDefined(),
    );
    const fill = screen.getByTestId("inject-preview-bar-fill");
    expect(fill.className).toMatch(/bg-destructive/);
    expect(screen.getByTestId("inject-preview-truncated")).toBeDefined();
  });

  it("toggles pages and preview collapsibles", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: PAYLOAD });
    render(wrap(<InjectPreview project="alpha" />));
    await waitFor(() =>
      expect(screen.getByTestId("inject-preview")).toBeDefined(),
    );

    // Pages collapsed initially.
    expect(screen.queryByTestId("inject-preview-pages")).toBeNull();
    fireEvent.click(screen.getByText("Pages included (2)"));
    expect(screen.getByTestId("inject-preview-pages")).toBeDefined();
    expect(screen.getByText(/wiki\/concepts\/foo\.md/)).toBeDefined();

    // Preview collapsed initially.
    expect(screen.queryByTestId("inject-preview-text")).toBeNull();
    fireEvent.click(screen.getByText("Show preview"));
    expect(screen.getByTestId("inject-preview-text")).toBeDefined();
  });
});
