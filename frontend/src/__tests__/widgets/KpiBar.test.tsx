import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { KpiBar } from "../../components/widgets/dashboard/KpiBar";
import type { Kpi } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      kpi: {
        queue_label: "Queue",
        queue_format: "{{queued}} queued · {{running}} running · {{failed}} failed",
        active_label: "Active",
        active_format: "🟢 {{hot}} · 🟡 {{cooling}}",
        today_label: "Today",
        today_format: "{{ingest}} ingest · {{pages}} pages",
        tokens_label: "Tokens",
        lost_label: "Lost",
        lost_link: "→ Sort",
      },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const KPI: Kpi = {
  queue: { queued: 3, running: 1, failed: 0 },
  active: { hot: 2, cooling: 1 },
  today: { ingest_count: 5, pages_count: 12 },
  tokens_today: 862_000,
  lost_total: 1304,
};

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("KpiBar", () => {
  it("renders all five tiles with values", () => {
    render(wrap(<KpiBar data={KPI} />));
    // Hero (active) + 4 compact tiles by testid
    expect(screen.getByTestId("kpi-queue")).toBeDefined();
    expect(screen.getByTestId("kpi-active")).toBeDefined();
    expect(screen.getByTestId("kpi-today")).toBeDefined();
    expect(screen.getByTestId("kpi-tokens")).toBeDefined();
    expect(screen.getByTestId("kpi-lost")).toBeDefined();
    // Compact queue format is "queued/running/failed"
    expect(screen.getByText("3/1/0")).toBeDefined();
    // Lost shows raw number
    expect(screen.getByText("1304")).toBeDefined();
  });

  it("highlights queue tile in red when failed > 0", () => {
    const failedKpi = { ...KPI, queue: { ...KPI.queue, failed: 2 } };
    const { container } = render(wrap(<KpiBar data={failedKpi} />));
    const tile = container.querySelector('[data-testid="kpi-queue"]');
    expect(tile?.className).toMatch(/destructive|red/);
  });
});
