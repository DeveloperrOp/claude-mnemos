import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UpdateBanner } from "@/components/widgets/dashboard/UpdateBanner";
import * as api from "@/api/update.api";

vi.mock("@/api/update.api");

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UpdateBanner />
    </QueryClientProvider>,
  );
}

describe("UpdateBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when no update available", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.0.1",
      download_url: null,
      has_update: false,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    const { container } = renderBanner();
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector("[data-testid='update-banner']")).toBeNull();
  });

  it("renders banner with version + download link when has_update", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.1.0",
      download_url: "https://example.com/v0.1.0",
      has_update: true,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    renderBanner();
    expect(await screen.findByText(/0\.1\.0/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /download/i });
    expect(link).toHaveAttribute("href", "https://example.com/v0.1.0");
  });

  it("calls dismiss when 'Later' clicked", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.1.0",
      download_url: "https://example.com/v0.1.0",
      has_update: true,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    vi.mocked(api.dismissUpdate).mockResolvedValue();
    renderBanner();
    await userEvent.click(await screen.findByRole("button", { name: /later/i }));
    await waitFor(() => expect(api.dismissUpdate).toHaveBeenCalled());
  });
});
