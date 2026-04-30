import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { GeneralSection } from "../components/settings/sections/GeneralSection";
import type { ProjectMapEntry } from "../types/Project";

const PROJECT: ProjectMapEntry = {
  name: "p1",
  display_name: "Project One",
  vault_root: "/tmp/p1",
  cwd_patterns: ["~/code/p1/*"],
};

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
        section: {
          general: {
            title: "General",
            display_name: "Display name",
            display_name_hint: "Shown in dashboard. Leave empty to clear.",
            slug: "Slug (read-only)",
            slug_hint: "Used in URLs and file paths.",
            vault: "Vault path (read-only)",
            vault_hint: "To move vault, create new project.",
            cwd: "Project folders",
            copy: "Copy",
          },
        },
      },
      cwd_builder: {
        add: "Add folder",
        remove: "Remove",
        recursive: "Include subfolders",
        empty: "No folders added",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
  vi.spyOn(apiClient, "patch");
});
afterEach(() => {
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("GeneralSection", () => {
  it("renders display_name, slug RO, vault RO, CWD list", () => {
    wrap(<GeneralSection project={PROJECT} />);
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Project One")).toBeInTheDocument();
    const slugInput = screen.getByDisplayValue("p1");
    expect(slugInput).toHaveAttribute("readonly");
    const vaultInput = screen.getByDisplayValue("/tmp/p1");
    expect(vaultInput).toHaveAttribute("readonly");
    expect(screen.getByText(/~\/code\/p1$/)).toBeInTheDocument();
  });

  it("Save disabled when nothing changed", () => {
    wrap(<GeneralSection project={PROJECT} />);
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeDisabled();
  });

  it("change display_name → Save enables → PATCH /projects/p1", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...PROJECT, display_name: "New Name" },
    });
    wrap(<GeneralSection project={PROJECT} />);

    const input = screen.getByDisplayValue("Project One");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");

    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/projects/p1", {
        display_name: "New Name",
        cwd_patterns: ["~/code/p1/*"],
      }),
    );
  });

  it("empty display_name → PATCH sends empty string (clear)", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...PROJECT, display_name: null },
    });
    wrap(<GeneralSection project={PROJECT} />);

    const input = screen.getByDisplayValue("Project One");
    await userEvent.clear(input);

    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith("/projects/p1", {
        display_name: "",
        cwd_patterns: ["~/code/p1/*"],
      }),
    );
  });

  it("removing CWD pattern triggers dirty state", async () => {
    wrap(<GeneralSection project={PROJECT} />);
    const removeBtn = screen.getByRole("button", { name: /Remove/i });
    await userEvent.click(removeBtn);
    const save = screen.getByRole("button", { name: /^Save$/i });
    expect(save).toBeEnabled();
  });
});
