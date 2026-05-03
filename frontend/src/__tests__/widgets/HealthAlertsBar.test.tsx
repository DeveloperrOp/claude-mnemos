import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../../i18n";
import { HealthAlertsBar } from "../../components/widgets/dashboard/HealthAlertsBar";
import type { HealthAlert } from "../../types/HealthAlert";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      overview: {
        health_alerts: {
          title: "Alerts",
          severity: { info: "info", warning: "warn", critical: "critical" },
          snooze_label: "Snooze",
          snooze_1h: "Snooze 1h",
          snooze_24h: "Snooze 24h",
          snooze_forever: "Forever",
          dismiss: "Dismiss",
          show_more: "Show {{count}} more",
          show_less: "Show less",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

let mockData: { alerts: HealthAlert[]; silenced: HealthAlert[] } = {
  alerts: [],
  silenced: [],
};

vi.mock("../../hooks/dashboard/useHealthAlerts", () => ({
  useHealthAlerts: () => ({ data: mockData }),
}));

vi.mock("../../hooks/dashboard/useDismissHealthAlert", () => ({
  useDismissHealthAlert: () => ({ mutate: vi.fn() }),
}));

vi.mock("../../hooks/dashboard/useSilenceHealthAlert", () => ({
  useSilenceHealthAlert: () => ({ mutate: vi.fn() }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function makeAlert(id: string, overrides: Partial<HealthAlert> = {}): HealthAlert {
  return {
    id,
    detector: id,
    severity: "warning",
    message: `msg-${id}`,
    context: {},
    first_seen: "2026-05-03T10:00:00Z",
    last_seen: "2026-05-03T10:00:00Z",
    silenced_until: null,
    dismissed: false,
    ...overrides,
  };
}

describe("HealthAlertsBar", () => {
  it("renders nothing when no alerts", () => {
    mockData = { alerts: [], silenced: [] };
    const { container } = render(wrap(<HealthAlertsBar />));
    expect(container.querySelector('[data-testid="health-alerts-bar"]')).toBeNull();
  });

  it("renders single alert with message and severity icon", () => {
    mockData = {
      alerts: [makeAlert("a1", { severity: "critical", message: "disk low" })],
      silenced: [],
    };
    render(wrap(<HealthAlertsBar />));
    expect(screen.getByTestId("health-alerts-bar")).toBeDefined();
    expect(screen.getByText("disk low")).toBeDefined();
    expect(screen.getByText(/critical/i)).toBeDefined();
  });

  it("collapses when more than 3 alerts and shows expand toggle", () => {
    mockData = {
      alerts: [
        makeAlert("a"),
        makeAlert("b"),
        makeAlert("c"),
        makeAlert("d"),
        makeAlert("e"),
      ],
      silenced: [],
    };
    render(wrap(<HealthAlertsBar />));
    const rows = screen.getAllByTestId("health-alert-row");
    expect(rows.length).toBe(3);
    expect(screen.getByText(/Show 2 more/)).toBeDefined();
  });

  it("shows all rows when only 3 alerts (no expand toggle)", () => {
    mockData = {
      alerts: [makeAlert("a"), makeAlert("b"), makeAlert("c")],
      silenced: [],
    };
    render(wrap(<HealthAlertsBar />));
    const rows = screen.getAllByTestId("health-alert-row");
    expect(rows.length).toBe(3);
    expect(screen.queryByText(/Show .* more/)).toBeNull();
  });

  it("shows dismiss button per alert", () => {
    mockData = {
      alerts: [makeAlert("a1")],
      silenced: [],
    };
    render(wrap(<HealthAlertsBar />));
    expect(screen.getByText("Dismiss")).toBeDefined();
  });
});
