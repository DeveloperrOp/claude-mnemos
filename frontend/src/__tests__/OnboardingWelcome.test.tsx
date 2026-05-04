import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { OnboardingWelcome } from "@/pages/OnboardingWelcome";
import * as onboardingApi from "@/api/onboarding.api";
import * as projectCreate from "@/hooks/useProjectCreate";

vi.mock("@/api/onboarding.api");
vi.mock("@/hooks/useProjectCreate");

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OnboardingWelcome />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OnboardingWelcome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default stub so tests that don't care about mutations still render.
    vi.mocked(projectCreate.useProjectCreate).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof projectCreate.useProjectCreate>);
  });

  it("renders detected workspaces with session counts", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({
      cwds: [
        { cwd: "D:/code/app1", session_count: 12, last_seen: "2026-05-04T10:00Z" },
        { cwd: "D:/code/app2", session_count: 3, last_seen: "2026-05-03T10:00Z" },
      ],
    });
    renderPage();
    expect(await screen.findByText(/D:\/code\/app1/i)).toBeInTheDocument();
    expect(screen.getByText(/12 sessions/i)).toBeInTheDocument();
    expect(await screen.findByText(/D:\/code\/app2/i)).toBeInTheDocument();
  });

  it("shows empty hint when no cwds detected", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({ cwds: [] });
    renderPage();
    expect(
      await screen.findByText(/no claude code sessions found/i),
    ).toBeInTheDocument();
  });

  it("creates a project when user picks a workspace and clicks Track", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({
      cwds: [{ cwd: "D:/code/app1", session_count: 12, last_seen: "2026-05-04T10:00Z" }],
    });
    const mutate = vi.fn();
    vi.mocked(projectCreate.useProjectCreate).mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof projectCreate.useProjectCreate>);

    renderPage();
    const checkbox = await screen.findByRole("checkbox", { name: /D:\/code\/app1/i });
    await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole("button", { name: /track selected/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: expect.stringMatching(/app1/),
          vault_root: expect.stringContaining("D:/code/app1"),
          cwd_patterns: expect.arrayContaining(["D:/code/app1"]),
        }),
        expect.anything(),
      );
    });
  });

  it("offers Show advanced link", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({ cwds: [] });
    renderPage();
    expect(await screen.findByRole("link", { name: /show advanced/i })).toBeInTheDocument();
  });
});
