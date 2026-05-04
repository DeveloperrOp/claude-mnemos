import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { Diagnostics } from "@/pages/Diagnostics";
import * as api from "@/api/diagnostics.api";
import * as installHooksMod from "@/hooks/useInstallHooks";

vi.mock("@/api/diagnostics.api");
vi.mock("@/hooks/useInstallHooks");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Diagnostics />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Diagnostics page", () => {
  it("renders four checklist rows", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "Claude Code installed" },
      hooks: { status: "ok", message: "Hooks installed" },
      vaults: { status: "ok", message: "Vaults writable" },
      projects: { status: "ok", message: "1 project tracked", count: 1 },
    });
    renderPage();
    expect(await screen.findByText(/Claude Code CLI/i)).toBeInTheDocument();
    expect(await screen.findByText(/Claude Code hooks/i)).toBeInTheDocument();
    expect(await screen.findByText(/Vault writability/i)).toBeInTheDocument();
    expect(await screen.findByText(/Tracked projects/i)).toBeInTheDocument();
  });

  it("shows critical message when claude_cli missing", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: false,
      claude_cli: { status: "critical", message: "Claude Code is not installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderPage();
    expect(await screen.findByText(/Claude Code is not installed/i)).toBeInTheDocument();
  });

  it("renders Re-install hooks button when hooks row is not ok and triggers install", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: false,
      claude_cli: { status: "ok", message: "ok" },
      hooks: { status: "warning", message: "Some Claude Code hooks are missing: PreCompact." },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    const mutateAsync = vi.fn().mockResolvedValue({});
    vi.mocked(installHooksMod.useInstallHooks).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof installHooksMod.useInstallHooks>);

    renderPage();
    const btn = await screen.findByRole("button", { name: /re-install hooks/i });
    await userEvent.click(btn);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
  });

  it("does not render Re-install hooks button when hooks row is ok", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "ok" },
      hooks: { status: "ok", message: "All hooks installed" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    vi.mocked(installHooksMod.useInstallHooks).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof installHooksMod.useInstallHooks>);

    renderPage();
    expect(await screen.findByText(/All hooks installed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /re-install hooks/i })).toBeNull();
  });
});
