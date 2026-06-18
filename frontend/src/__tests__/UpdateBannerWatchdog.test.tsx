import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { UpdateBanner } from "@/components/widgets/dashboard/UpdateBanner";
import * as api from "@/api/update.api";

vi.mock("@/api/update.api");

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      overview: {
        update: {
          eyebrow: "UPDATE",
          available: "v{{version}} is available",
          current_version: "(you have {{current}})",
          download_button: "Download",
          later_button: "Later",
          apply_button: "Update now",
          applying: "Updating…",
          apply_error: "Couldn't update automatically.",
          apply_uac_hint: "UAC hint.",
          last_failed: "Last attempt failed: {{error}}.",
          apply_timeout: "The update didn't finish automatically.",
          apply_retry: "Try again",
          applied: "Updated to v{{version}}",
          restarting: "Restarting…",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

const WINDOWS_VERSION: api.VersionInfo = {
  version: "0.0.1",
  platform: "Windows-11-10.0.26200-SP0",
  python_version: "3.12.8",
};

const baseStatus: api.UpdateStatus = {
  current: "0.0.1",
  latest: "0.1.0",
  download_url: "https://example.com/v0.1.0",
  asset_url: "https://example.com/assets/v0.1.0/mnemos-setup.exe",
  has_update: true,
  checked_at: new Date().toISOString(),
  dismissed_until: null,
  error: null,
};

function renderBanner(
  props: { applyTimeoutMs?: number; versionPollMs?: number } = {
    applyTimeoutMs: 30,
  },
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      {/* tiny watchdog window so the test runs on real timers */}
      <UpdateBanner {...props} />
    </QueryClientProvider>,
  );
}

describe("UpdateBanner watchdog", () => {
  beforeEach(() => {
    vi.mocked(api.getVersionInfo).mockReset();
    vi.mocked(api.getUpdateStatus).mockReset();
    vi.mocked(api.applyUpdate).mockReset();
  });

  it("flips from 'updating' to a timeout/retry state if the swap never completes", async () => {
    // Version never changes (still 0.0.1, latest is 0.1.0) so the poll must
    // NOT false-"apply" — the watchdog is the only thing that can fire.
    vi.mocked(api.getVersionInfo).mockResolvedValue(WINDOWS_VERSION);
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    vi.mocked(api.applyUpdate).mockResolvedValue({
      started: true,
      version: "0.1.0",
    });

    renderBanner({ applyTimeoutMs: 30, versionPollMs: 5 });
    await userEvent.click(
      await screen.findByRole("button", { name: /update now/i }),
    );
    // Latches into "updating" first…
    expect(
      await screen.findByTestId("update-banner-updating"),
    ).toBeInTheDocument();
    // …then the watchdog flips it to the timeout/retry state.
    expect(
      await screen.findByTestId("update-banner-timeout"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("update-banner-updating")).toBeNull();

    // Retry resets back to the actionable banner.
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(
      await screen.findByRole("button", { name: /update now/i }),
    ).toBeInTheDocument();
  });

  it("shows 'updated' once /api/version reports the new version", async () => {
    vi.mocked(api.getVersionInfo)
      .mockResolvedValueOnce(WINDOWS_VERSION) // initial 0.0.1
      .mockResolvedValue({ ...WINDOWS_VERSION, version: "0.1.0" }); // after swap
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus); // latest 0.1.0
    vi.mocked(api.applyUpdate).mockResolvedValue({
      started: true,
      version: "0.1.0",
    });

    renderBanner({ applyTimeoutMs: 9000, versionPollMs: 20 });
    await userEvent.click(
      await screen.findByRole("button", { name: /update now/i }),
    );
    expect(
      await screen.findByTestId("update-banner-updating"),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("update-banner-applied"),
    ).toBeInTheDocument();
  });
});
