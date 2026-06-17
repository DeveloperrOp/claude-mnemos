import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { VersionStatus } from "@/components/widgets/dashboard/VersionStatus";
import * as api from "@/api/update.api";

vi.mock("@/api/update.api");

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      overview: {
        version_status: {
          label: "Version {{version}}",
          check_button: "Check for updates",
          checking: "Checking…",
          up_to_date: "You're on the latest version",
          check_error: "Couldn't check for updates — no connection to GitHub",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function renderWidget() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <VersionStatus />
    </QueryClientProvider>,
  );
}

const VERSION: api.VersionInfo = {
  version: "0.0.53",
  platform: "Windows-11-10.0.26200-SP0",
  python_version: "3.12.10",
};

const upToDateStatus: api.UpdateStatus = {
  current: "0.0.53",
  latest: "0.0.53",
  download_url: null,
  asset_url: null,
  has_update: false,
  checked_at: new Date().toISOString(),
  dismissed_until: null,
  error: null,
};

describe("VersionStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getVersionInfo).mockResolvedValue(VERSION);
    vi.mocked(api.getUpdateStatus).mockResolvedValue(upToDateStatus);
  });

  it("renders the installed version", async () => {
    renderWidget();
    expect(await screen.findByText(/Version 0\.0\.53/)).toBeInTheDocument();
  });

  it("checks for updates and reports 'up to date' when none found", async () => {
    vi.mocked(api.checkForUpdate).mockResolvedValue(upToDateStatus);
    renderWidget();
    await userEvent.click(
      await screen.findByRole("button", { name: /check for updates/i }),
    );
    await waitFor(() => expect(api.checkForUpdate).toHaveBeenCalled());
    expect(
      await screen.findByTestId("version-status-uptodate"),
    ).toBeInTheDocument();
  });

  it("surfaces an error when the check fails", async () => {
    vi.mocked(api.checkForUpdate).mockRejectedValue(new Error("network"));
    renderWidget();
    await userEvent.click(
      await screen.findByRole("button", { name: /check for updates/i }),
    );
    expect(
      await screen.findByTestId("version-status-error"),
    ).toBeInTheDocument();
  });
});
