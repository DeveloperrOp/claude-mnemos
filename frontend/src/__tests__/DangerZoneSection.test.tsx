import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { DangerZoneSection } from "../components/settings/sections/DangerZoneSection";
import type { ProjectMapEntry } from "../types/Project";

const PROJECT: ProjectMapEntry = {
  name: "p1",
  display_name: "Alpha",
  vault_root: "/vaults/p1",
  cwd_patterns: [],
};

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        danger: {
          title: "Danger zone",
          body: "Permanent actions.",
          delete_button: "Delete project",
          modal_title: "Delete project «{{name}}»?",
          modal_body: "Vault folder at {{vault}} will NOT be deleted.",
          confirm_label: "Type «{{slug}}» to confirm:",
          cancel: "Cancel",
          confirm: "Delete project",
          deleting: "Deleting...",
          force_delete: "Force delete (cancel jobs)",
          force_modal_title: "Force-delete «{{name}}»?",
          force_modal_body: "This will KILL {{running}} running and DROP {{queued}} queued jobs.",
          force_confirm_label: "Type «{{phrase}}» to confirm",
          force_apply: "Force-delete",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
  vi.spyOn(apiClient, "delete");
});
afterEach(() => {
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={["/settings/p1"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/settings/p1" element={ui} />
          <Route path="/" element={<div data-testid="overview-stub" />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("DangerZoneSection", () => {
  it("renders Delete button", async () => {
    wrap(<DangerZoneSection project={PROJECT} />);
    expect(
      screen.getByRole("button", { name: "Delete project" }),
    ).toBeInTheDocument();
  });

  it("clicking Delete opens modal with project name interpolated", async () => {
    wrap(<DangerZoneSection project={PROJECT} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Delete project" }),
    );
    expect(screen.getByText(/Delete project «Alpha»\?/)).toBeInTheDocument();
    expect(screen.getByText(/Type «p1»/)).toBeInTheDocument();
  });

  it("wrong slug → confirm button disabled; correct slug → DELETE called → navigate", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: undefined });
    wrap(<DangerZoneSection project={PROJECT} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Delete project" }),
    );
    const confirmBtns = screen.getAllByRole("button", {
      name: "Delete project",
    });
    // One in the section header + one in the modal — modal one is the second
    const modalConfirm = confirmBtns[confirmBtns.length - 1];
    expect(modalConfirm).toBeDisabled();

    const input = screen.getByRole("textbox");
    await userEvent.type(input, "wrong-slug");
    expect(modalConfirm).toBeDisabled();

    await userEvent.clear(input);
    await userEvent.type(input, "p1");
    expect(modalConfirm).toBeEnabled();

    await userEvent.click(modalConfirm);
    await waitFor(() =>
      expect(apiClient.delete).toHaveBeenCalledWith("/projects/p1", {
        params: undefined,
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("overview-stub")).toBeInTheDocument(),
    );
  });

  it("409 jobs-running → Force link opens second typed-confirm → DELETE ?force=true (P0-3)", async () => {
    // First call rejects with 409 + dict detail
    vi.mocked(apiClient.delete)
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            detail: {
              error: "jobs_in_progress",
              queued: 2,
              running: 1,
              hint: "Project has running jobs; use ?force=true to cancel them.",
            },
          },
        },
        message: "Request failed with status code 409",
      })
      .mockResolvedValueOnce({ data: undefined });

    wrap(<DangerZoneSection project={PROJECT} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Delete project" }),
    );

    const input = screen.getByRole("textbox");
    await userEvent.type(input, "p1");

    const confirmBtns = screen.getAllByRole("button", {
      name: "Delete project",
    });
    const modalConfirm = confirmBtns[confirmBtns.length - 1];
    await userEvent.click(modalConfirm);

    await waitFor(() =>
      expect(
        screen.getByText(
          /Project has running jobs; use \?force=true to cancel them\./,
        ),
      ).toBeInTheDocument(),
    );

    // P0-3: clicking the Force link MUST NOT trigger DELETE directly.
    // It opens the second modal showing kill-counts and requires typing
    // FORCE-{slug} before the Apply button is enabled.
    const forceLink = screen.getByRole("button", {
      name: /Force delete \(cancel jobs\)/i,
    });
    await userEvent.click(forceLink);

    // Verify second modal opened with kill-counts (running=1, queued=2).
    expect(screen.getByText(/KILL 1 running/)).toBeInTheDocument();
    expect(screen.getByText(/DROP 2 queued/)).toBeInTheDocument();

    // DELETE not yet called — only the initial failed attempt.
    expect(apiClient.delete).toHaveBeenCalledTimes(1);

    // Force-apply button disabled until matching phrase typed.
    const forceApply = screen.getByRole("button", { name: "Force-delete" });
    expect(forceApply).toBeDisabled();

    // Type the required phrase.
    const inputs = screen.getAllByRole("textbox");
    const forceInput = inputs[inputs.length - 1];
    await userEvent.type(forceInput, "FORCE-p1");
    expect(forceApply).toBeEnabled();

    // Now apply → second DELETE with force=true.
    await userEvent.click(forceApply);

    await waitFor(() =>
      expect(apiClient.delete).toHaveBeenLastCalledWith("/projects/p1", {
        params: { force: true },
      }),
    );
  });
});
