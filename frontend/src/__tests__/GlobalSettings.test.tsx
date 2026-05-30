import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

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
const { GlobalSettings } = await import("../pages/GlobalSettings");
const { GlobalGeneralSection } = await import(
  "../components/settings/globals/GlobalGeneralSection"
);
const { GlobalDefaultsSection } = await import(
  "../components/settings/globals/GlobalDefaultsSection"
);
const { apiClient } = await import("../api/client");

const FULL_GLOBAL = {
  version: 1,
  locale: "uk",
  daemon_port: 5757,
  default_model: "claude-sonnet-4-6",
  default_language_hint: "auto",
  default_max_input_tokens: 150000,
  default_retention_days: 180,
};

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
        global: {
          title: "Global settings",
          general: {
            title: "General",
            locale: "Dashboard language",
            daemon_port: "Daemon port",
            daemon_port_warn: "Port change needs a restart.",
            save_and_restart_btn: "Save & restart",
            restart_daemon_btn: "Restart daemon",
            restart_in_progress: "Daemon is restarting…",
          },
          defaults: {
            title: "Defaults",
            default_model: "Default model",
            default_language_hint: "Default language hint",
            default_max_input_tokens: "Default max input tokens",
            default_retention_days: "Default retention (days)",
          },
        },
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

afterEach(() => {
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("GlobalSettings page", () => {
  it("renders both sections", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: FULL_GLOBAL });
    wrap(<GlobalSettings />);
    expect(
      screen.getByRole("heading", { name: "Global settings" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("General")).toBeInTheDocument(),
    );
    expect(screen.getByText("Defaults")).toBeInTheDocument();
  });
});

describe("GlobalGeneralSection", () => {
  it("changes daemon_port and PATCHes /settings/global", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: FULL_GLOBAL });
    vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { ...FULL_GLOBAL, daemon_port: 6000 },
    });
    wrap(<GlobalGeneralSection />);
    await waitFor(() =>
      expect(screen.getByText("General")).toBeInTheDocument(),
    );
    const portInput = screen.getByDisplayValue("5757");
    await userEvent.clear(portInput);
    await userEvent.type(portInput, "6000");
    // The accordion "Save" button — not the "Save & restart" one that the
    // port-change warning block now also renders.
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/settings/global",
        expect.objectContaining({ daemon_port: 6000, locale: "uk" }),
      ),
    );
  });

  it("'Save & restart' PATCHes then POSTs /daemon/restart", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: FULL_GLOBAL });
    vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { ...FULL_GLOBAL, daemon_port: 6000 },
    });
    // supervised:false → flow opens the manual-help dialog instead of
    // polling /version + reloading the window (keeps the test deterministic).
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: { ok: true, supervised: false } });

    wrap(<GlobalGeneralSection />);
    await waitFor(() =>
      expect(screen.getByText("General")).toBeInTheDocument(),
    );
    const portInput = screen.getByDisplayValue("5757");
    await userEvent.clear(portInput);
    await userEvent.type(portInput, "6000");

    await userEvent.click(
      screen.getByRole("button", { name: /Save & restart/i }),
    );

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/settings/global",
        expect.objectContaining({ daemon_port: 6000 }),
      ),
    );
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/daemon/restart"),
    );
  });
});

describe("GlobalDefaultsSection", () => {
  it("changes default_model via preset dropdown and PATCHes /settings/global", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: FULL_GLOBAL });
    vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { ...FULL_GLOBAL, default_model: "claude-opus-4-7" },
    });
    wrap(<GlobalDefaultsSection />);
    await waitFor(() =>
      expect(screen.getByText("Defaults")).toBeInTheDocument(),
    );
    // v0.0.36 replaced the free-text model input with a preset select
    // when the current value matches one of the known model IDs.
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    const modelSelect = selects.find((s) => s.value === "claude-sonnet-4-6")!;
    await userEvent.selectOptions(modelSelect, "claude-opus-4-7");
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/settings/global",
        expect.objectContaining({ default_model: "claude-opus-4-7" }),
      ),
    );
  });
});
