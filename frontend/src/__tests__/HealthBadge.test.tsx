import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";

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
const { HealthBadge } = await import("../components/widgets/HealthBadge");

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    { health: { ok: "Healthy", degraded: "Degraded", down: "Down" } },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

describe("HealthBadge", () => {
  it("renders green when watchdog up and dead-letter clean", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: true,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 0,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "ok");
  });

  it("renders yellow when watchdog down", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: false,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 0,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "warn");
  });

  it("renders red when watchdog down AND dead-letter overflow", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: false,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 11,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "danger");
  });

  it("renders 'down' when no health data", () => {
    render(<HealthBadge vault_health={undefined} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "down");
  });
});
