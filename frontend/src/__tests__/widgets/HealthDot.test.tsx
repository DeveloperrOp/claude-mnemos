import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { HealthDot } from "../../components/widgets/dashboard/HealthDot";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      overview: {
        health_dot: {
          ok: "Healthy",
          warning: "Warnings",
          critical: "Critical",
          details_link: "→ Details",
        },
      },
    },
    true,
    true
  );
  void i18n.changeLanguage("en");
});

vi.mock("../../hooks/useHealth", () => ({
  useHealth: () => ({
    data: { status: "ok", alerts_count: 0 },
    isLoading: false,
  }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("HealthDot", () => {
  it("renders Healthy state when ok and no alerts", () => {
    render(wrap(<HealthDot />));
    expect(screen.getByText(/Healthy/)).toBeDefined();
  });

  it("links to /health", () => {
    render(wrap(<HealthDot />));
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/health");
  });

  it("shows the details link text", () => {
    render(wrap(<HealthDot />));
    expect(screen.getByText(/→ Details/)).toBeDefined();
  });
});
