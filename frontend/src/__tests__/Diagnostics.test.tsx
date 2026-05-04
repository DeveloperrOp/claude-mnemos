import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { Diagnostics } from "@/pages/Diagnostics";
import * as api from "@/api/diagnostics.api";

vi.mock("@/api/diagnostics.api");

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
});
