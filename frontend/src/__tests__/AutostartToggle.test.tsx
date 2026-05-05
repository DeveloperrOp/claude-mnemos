import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "@/api/system.api";

vi.mock("@/api/system.api");

import { useAutostartStatus, useSetAutostart } from "@/hooks/useAutostart";

function AutostartToggle() {
  const q = useAutostartStatus();
  const m = useSetAutostart();
  if (q.isLoading || !q.data) return null;
  return (
    <label>
      <input
        type="checkbox"
        checked={q.data.enabled}
        onChange={(e) => m.mutate(e.target.checked)}
      />
      Start with Windows
    </label>
  );
}

beforeEach(() => vi.clearAllMocks());

function renderToggle() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AutostartToggle />
    </QueryClientProvider>,
  );
}

describe("AutostartToggle", () => {
  it("renders checked when enabled", async () => {
    vi.mocked(api.getAutostart).mockResolvedValue({ enabled: true });
    renderToggle();
    const cb = await screen.findByRole("checkbox");
    expect(cb).toBeChecked();
  });

  it("renders unchecked when disabled", async () => {
    vi.mocked(api.getAutostart).mockResolvedValue({ enabled: false });
    renderToggle();
    const cb = await screen.findByRole("checkbox");
    expect(cb).not.toBeChecked();
  });

  it("calls setAutostart(false) when toggled off", async () => {
    vi.mocked(api.getAutostart).mockResolvedValue({ enabled: true });
    vi.mocked(api.setAutostart).mockResolvedValue();
    renderToggle();
    const cb = await screen.findByRole("checkbox");
    await userEvent.click(cb);
    await waitFor(() =>
      expect(vi.mocked(api.setAutostart).mock.calls[0]?.[0]).toBe(false),
    );
  });
});
