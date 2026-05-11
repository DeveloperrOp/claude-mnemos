import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { SetupChecklist } from "@/components/widgets/dashboard/SetupChecklist";
import * as api from "@/api/diagnostics.api";

vi.mock("@/api/diagnostics.api");

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      overview: {
        setup: {
          all_ok: "✓ Setup OK",
          heading: "SETUP STATUS",
          diagnostics_link: "Diagnostics →",
          fix_button: "Fix",
        },
        hooks_fix: {
          label: "Re-install hooks",
          success_toast: "Hooks installed",
          error_toast: "Hook install failed: {{error}}",
          pending: "Installing…",
        },
      },
      diagnostics: {
        row: {
          claude_cli: "Claude Code CLI",
          hooks: "Claude Code hooks",
          vaults: "Vault writability",
          projects: "Tracked projects",
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
      <MemoryRouter>
        <SetupChecklist />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SetupChecklist widget", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders collapsed when all_ok", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "ok" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    expect(await screen.findByText(/setup ok/i)).toBeInTheDocument();
    expect(screen.queryByText(/Claude Code installed/i)).toBeNull();
  });

  it("expands by default and shows non-ok row when any fail", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: false,
      claude_cli: { status: "critical", message: "Claude Code is not installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    expect(await screen.findByText(/Claude Code is not installed/i)).toBeInTheDocument();
  });

  it("expands collapsed widget on click", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "Claude CLI installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    const summary = await screen.findByText(/setup ok/i);
    fireEvent.click(summary);
    expect(await screen.findByText(/Claude CLI installed/i)).toBeInTheDocument();
  });
});
