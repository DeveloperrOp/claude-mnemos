import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { Toaster } from "../components/ui/sonner";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Onboarding } from "../pages/Onboarding";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: { working: "Working..." },
    onboarding: {
      title: "Create new project",
      subtitle: "Mount a vault.",
      name_label: "Project name",
      name_hint: "lowercase",
      name_invalid: "Invalid name",
      name_taken: "Already exists",
      display_name_label: "Display name",
      display_name_hint: "Name shown in the dashboard.",
      slug_label: "Slug (technical)",
      slug_hint: "Used in URLs and folder names.",
      slug_edit: "Edit slug",
      slug_lock: "Auto",
      slug_invalid: "Invalid slug",
      vault_label: "Vault path",
      vault_hint: "Absolute",
      advanced_toggle: "Advanced",
      cwd_label: "CWD patterns",
      cwd_hint: "globs",
      submit: "Create project",
      cancel: "Cancel",
      mount_failed_title: "Mount failed",
      success_toast: "Project created",
      autostart_label: "Auto-start mnemos on login",
      autostart_hint: "Adds a tray icon and starts the daemon automatically when you sign in.",
      cli_check_label: "Claude CLI status",
      cli_check_ok: "✓ Claude CLI installed and authenticated",
      cli_check_not_installed: "⚠ Claude CLI not found — install Claude Code from https://claude.ai/download",
      cli_check_not_authenticated: "⚠ Claude CLI installed but not logged in — run `claude login` in your terminal",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

let trayMock: MockAdapter;

beforeEach(() => {
  trayMock = new MockAdapter(axios);
});

afterEach(() => {
  trayMock.restore();
  vi.restoreAllMocks();
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/onboarding"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/onboarding" element={ui} />
          <Route path="/project/:name" element={<div data-testid="project-view-stub" />} />
        </Routes>
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Onboarding", () => {
  it("disables submit when display name is empty", async () => {
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    const submit = screen.getByRole("button", { name: /create project/i });
    expect(submit).toBeDisabled();

    // Only filling vault is not enough — display_name must be present.
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/x");
    expect(submit).toBeDisabled();
  });

  it("enables submit on valid input + posts to /projects + navigates", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: { name: "alpha", display_name: "alpha", vault_root: "/tmp/alpha", cwd_patterns: [] },
    });
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/display name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/alpha");

    const submit = screen.getByRole("button", { name: /create project/i });
    expect(submit).not.toBeDisabled();
    await user.click(submit);
    await waitFor(() => expect(screen.getByTestId("project-view-stub")).toBeInTheDocument());
  });

  it("shows mount_failed callout on 500", async () => {
    const err = new Error("Request failed") as Error & { isAxiosError: boolean; response: { status: number; data: { error: string; detail: string } } };
    err.isAxiosError = true;
    err.response = { status: 500, data: { error: "mount_failed", detail: "Permission denied: /var/foo" } };
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(err);
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/display name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/var/foo");
    await user.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(screen.getByText(/mount failed/i)).toBeInTheDocument());
    expect(screen.getByText(/permission denied/i)).toBeInTheDocument();
  });

  it("shows inline name_taken on 409", async () => {
    const err = new Error("Request failed") as Error & { isAxiosError: boolean; response: { status: number; data: { error: string; detail: string } } };
    err.isAxiosError = true;
    err.response = { status: 409, data: { error: "name_conflict", detail: "Name already exists" } };
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(err);
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/display name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/alpha");
    await user.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(screen.getByText(/already exists/i)).toBeInTheDocument());
  });

  it("renders auto-start checkbox when platform supported", async () => {
    trayMock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: false,
    });
    render(wrap(<Onboarding />));

    expect(await screen.findByLabelText(/auto.?start/i)).toBeInTheDocument();
  });

  it("hides auto-start checkbox on unsupported platform", async () => {
    trayMock.onGet("/tray/status").reply(200, {
      platform: "unsupported",
      autostart_enabled: false,
    });
    render(wrap(<Onboarding />));
    // Wait a tick so the fetch resolves and any conditional render settles.
    await waitFor(() => expect(trayMock.history.get.length).toBeGreaterThan(0));
    expect(screen.queryByLabelText(/auto.?start/i)).not.toBeInTheDocument();
  });

  it("calls /tray/install when checkbox checked and form submitted", async () => {
    trayMock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: false,
    });
    trayMock.onPost("/tray/install").reply(200, { installed: true });
    vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: { name: "p1", display_name: "p1", vault_root: "/x", cwd_patterns: [] },
    });

    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/display name/i), "p1");
    await user.type(screen.getByLabelText(/vault path/i), "/x");
    // Checkbox is checked by default; the explicit click would toggle off.
    // The plan's intent is "checkbox checked" so we just submit.
    expect(await screen.findByLabelText(/auto.?start/i)).toBeChecked();
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      const installCalls = trayMock.history.post.filter((c) => c.url === "/tray/install");
      expect(installCalls.length).toBe(1);
    });
  });

  it("shows green CLI check when authenticated", async () => {
    trayMock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: true,
      binary_path: "/x/claude",
    });
    render(wrap(<Onboarding />));
    expect(await screen.findByText(/Claude CLI installed and authenticated/i))
      .toBeInTheDocument();
  });

  it("shows install instruction when CLI missing", async () => {
    trayMock.onGet("/health/claude-cli").reply(200, {
      installed: false,
      authenticated: false,
    });
    render(wrap(<Onboarding />));
    expect(await screen.findByText(/Claude Code from https:/i))
      .toBeInTheDocument();
  });

  it("shows login instruction when CLI installed but not authed", async () => {
    trayMock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: false,
    });
    render(wrap(<Onboarding />));
    expect(await screen.findByText(/run `claude login`/i))
      .toBeInTheDocument();
  });

  it("auto-derives slug from display_name input", async () => {
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    const displayInput = screen.getByLabelText(/display name/i);
    await user.type(displayInput, "Конструктор сайтов");
    const slugInput = screen.getByLabelText(/slug/i) as HTMLInputElement;
    expect(slugInput.value).toMatch(/^[a-z0-9][a-z0-9-]+$/);
  });

  it("locks slug auto-derive when user clicks Edit slug", async () => {
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    const displayInput = screen.getByLabelText(/display name/i);
    await user.type(displayInput, "Test");
    const slugInput = screen.getByLabelText(/slug/i) as HTMLInputElement;
    expect(slugInput.value).toBe("test");

    const editBtn = screen.getByRole("button", { name: /edit slug/i });
    await user.click(editBtn);
    await user.clear(slugInput);
    await user.type(slugInput, "custom-slug");
    expect(slugInput.value).toBe("custom-slug");

    // Subsequent typing in display does NOT change slug
    await user.type(displayInput, " More");
    expect(slugInput.value).toBe("custom-slug");
  });

  it("submits display_name + slug + vault_root to /projects", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: {
        name: "my-project",
        display_name: "My Project",
        vault_root: "/tmp/x",
        cwd_patterns: [],
      },
    });
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/display name/i), "My Project");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/x");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => expect(postSpy).toHaveBeenCalled());
    const [url, body] = postSpy.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe("/projects");
    expect(body.display_name).toBe("My Project");
    expect(body.name).toBe("my-project");
    expect(body.vault_root).toBe("/tmp/x");
  });
});
