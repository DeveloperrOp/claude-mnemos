import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
          applying: "Updating… the app will close and reopen.",
          apply_error: "Couldn't update automatically — use the release link.",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UpdateBanner />
    </QueryClientProvider>,
  );
}

const WINDOWS_VERSION: api.VersionInfo = {
  version: "0.0.1",
  platform: "Windows-11-10.0.26200-SP0",
  python_version: "3.12.8",
};
const MAC_VERSION: api.VersionInfo = {
  version: "0.0.1",
  platform: "macOS-14.0-arm64",
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

describe("UpdateBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Sensible default for tests that don't care about platform.
    vi.mocked(api.getVersionInfo).mockResolvedValue(WINDOWS_VERSION);
  });

  it("renders nothing when no update available", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      ...baseStatus,
      latest: "0.0.1",
      download_url: null,
      asset_url: null,
      has_update: false,
    });
    const { container } = renderBanner();
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector("[data-testid='update-banner']")).toBeNull();
  });

  it("renders banner with version + download link when has_update", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    renderBanner();
    expect(await screen.findByText(/0\.1\.0/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /download/i });
    expect(link).toHaveAttribute("href", "https://example.com/v0.1.0");
  });

  it("calls dismiss when 'Later' clicked", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    vi.mocked(api.dismissUpdate).mockResolvedValue();
    renderBanner();
    await userEvent.click(await screen.findByRole("button", { name: /later/i }));
    await waitFor(() => expect(api.dismissUpdate).toHaveBeenCalled());
  });

  it("shows 'Update now' on Windows with an asset_url", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    renderBanner();
    expect(
      await screen.findByRole("button", { name: /update now/i }),
    ).toBeInTheDocument();
    // release link is still present
    expect(screen.getByRole("link", { name: /download/i })).toBeInTheDocument();
  });

  it("hides 'Update now' on non-Windows platform (release link still shows)", async () => {
    vi.mocked(api.getVersionInfo).mockResolvedValue(MAC_VERSION);
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    renderBanner();
    // Wait for the banner to render the download link first.
    expect(await screen.findByRole("link", { name: /download/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /update now/i }),
    ).toBeNull();
  });

  it("hides 'Update now' when asset_url is null (release link still shows)", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      ...baseStatus,
      asset_url: null,
    });
    renderBanner();
    expect(await screen.findByRole("link", { name: /download/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /update now/i }),
    ).toBeNull();
  });

  it("POSTs /api/update/apply and shows the updating state on success", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    vi.mocked(api.applyUpdate).mockResolvedValue({
      started: true,
      version: "0.1.0",
    });
    renderBanner();
    await userEvent.click(
      await screen.findByRole("button", { name: /update now/i }),
    );
    await waitFor(() => expect(api.applyUpdate).toHaveBeenCalled());
    // Banner switches to the "updating" state…
    expect(
      await screen.findByTestId("update-banner-updating"),
    ).toBeInTheDocument();
    // …and other actions disappear.
    expect(
      screen.queryByRole("button", { name: /update now/i }),
    ).toBeNull();
    expect(screen.queryByRole("link", { name: /download/i })).toBeNull();
  });

  it("shows an inline error on apply failure but keeps the release link", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue(baseStatus);
    vi.mocked(api.applyUpdate).mockRejectedValue(new Error("409 conflict"));
    renderBanner();
    await userEvent.click(
      await screen.findByRole("button", { name: /update now/i }),
    );
    expect(
      await screen.findByTestId("update-banner-error"),
    ).toBeInTheDocument();
    // The release link remains as the always-available fallback.
    expect(screen.getByRole("link", { name: /download/i })).toBeInTheDocument();
  });
});
