import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

const { default: i18n } = await import("../i18n");
const { ProjectSettings } = await import("../pages/ProjectSettings");
const { apiClient } = await import("../api/client");

const FULL_SETTINGS = {
  version: 1,
  locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  snapshots: { daily_enabled: true, retention_days: 180 },
};

const FULL_GLOBAL = {
  version: 1,
  locale: "uk",
  daemon_port: 5757,
  default_model: "claude-sonnet-4-6",
  default_language_hint: "auto",
  default_max_input_tokens: 150000,
  default_retention_days: 180,
};

const PROJECTS = [
  { name: "alpha", display_name: "Alpha", vault_root: "/v/alpha", cwd_patterns: [] },
];

beforeAll(async () => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        title: "Settings",
        loading: "Loading settings...",
        not_found_title: "Project not found",
        not_found_body: "The project was not found.",
        not_found_back: "Go back",
        save: "Save",
        saving: "Saving...",
        danger: {
          title: "Danger zone",
          body: "Permanent actions.",
          delete_button: "Delete project",
          modal_title: "Delete?",
          modal_body: "Body",
          confirm_label: "Type",
          cancel: "Cancel",
          confirm: "Delete",
          deleting: "Deleting...",
          force_delete: "Force",
        },
        section: {
          general: {
            title: "General",
            display_name: "Display name",
            display_name_hint: "",
            slug: "Slug",
            slug_hint: "",
            vault: "Vault",
            vault_hint: "",
            cwd: "Cwd",
            copy: "Copy",
          },
          locale: { title: "Locale", inherit: "Inherit" },
          auto_ingest: { title: "Auto-ingest", enabled: "Enabled", mode: "Mode" },
          lint: { title: "Lint", schedule: "Schedule", enabled_rules: "Rules", autofix_on_save: "Autofix" },
          snapshots: { title: "Snapshots", daily_enabled: "Daily", retention_days: "Retention" },
        },
      },
    },
    true,
    true,
  );
  if (!i18n.isInitialized) {
    await new Promise<void>((resolve) => i18n.on("initialized", resolve));
  }
  await i18n.changeLanguage("en");
});

function wrap(ui: ReactNode, path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/settings" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function mockApi() {
  return vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "/projects") return { data: PROJECTS };
    if (url.startsWith("/settings/global")) return { data: FULL_GLOBAL };
    if (url.startsWith("/settings/")) return { data: FULL_SETTINGS };
    return { data: {} };
  });
}

describe("ProjectSettings", () => {
  it("renders all 6 section titles when project loaded", async () => {
    mockApi();
    render(wrap(<ProjectSettings />, "/project/alpha/settings"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument(),
    );
    // v0.0.12: 5 placebo subgroups (Ontology/Watchdog/Lifecycle/Prompts/
    // Telemetry/Ingest overrides) were dropped. Remaining: General, Locale,
    // Auto-ingest, Lint, Snapshots + Danger zone.
    for (const title of [
      "General",
      "Locale",
      "Auto-ingest",
      "Lint",
      "Snapshots",
      "Danger zone",
    ]) {
      await waitFor(() =>
        expect(screen.getByText(title)).toBeInTheDocument(),
      );
    }
  });

  it("shows loading skeleton when projects list is not yet fetched", async () => {
    // Block /projects forever so project remains undefined.
    vi.spyOn(apiClient, "get").mockImplementation(
      () => new Promise(() => {}),
    );
    render(wrap(<ProjectSettings />, "/project/alpha/settings"));
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows not-found UI when slug missing from projects list", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects") return { data: [] };
      return { data: {} };
    });
    render(wrap(<ProjectSettings />, "/project/ghost/settings"));
    await waitFor(() =>
      expect(screen.getByText("Project not found")).toBeInTheDocument(),
    );
  });
});
