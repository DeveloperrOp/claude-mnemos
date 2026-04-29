import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "../components/ui/sonner";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PageEdit } from "../pages/PageEdit";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      confirm: {
        cancel: "Cancel",
        confirm: "Confirm",
        working: "Working...",
        typed_confirm_input_placeholder: "Type {{phrase}}",
      },
      pages: {
        editor: {
          title: "Edit page",
          title_field: "Title",
          type: "Type",
          status: "Status",
          flavor: "Flavor",
          confidence: "Confidence",
          aliases: "Aliases",
          aliases_hint: "csv",
          body_label: "Body",
          preview: "Preview",
          save: "Save",
          cancel: "Cancel",
          saved_toast: "Page saved",
          discard_modal_title: "Discard?",
          discard_modal_desc: "Lost.",
          discard_button: "Discard",
          loading: "Loading…",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/pages/*" element={ui} />
        </Routes>
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const SAMPLE = {
  path: "wiki/concepts/foo.md",
  frontmatter: {
    title: "Foo",
    type: "concept",
    status: "draft",
    confidence: 0.85,
    flavor: ["pattern"],
    sources: [],
    related: [],
    created: "2026-04-29T12:00:00Z",
    updated: "2026-04-29T12:00:00Z",
    provenance: null,
    agent_written: true,
    last_human_edit: null,
  },
  body: "## Hello",
};

describe("PageEdit", () => {
  it("renders form populated from page query", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: SAMPLE });
    render(wrap(<PageEdit />, "/project/alpha/pages/wiki/concepts/foo.md/edit"));
    await waitFor(() => expect(screen.getByDisplayValue("Foo")).toBeInTheDocument());
    expect(screen.getByDisplayValue(/## Hello/)).toBeInTheDocument();
  });

  it("Save calls patch with edited body", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: SAMPLE });
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const user = userEvent.setup();
    render(wrap(<PageEdit />, "/project/alpha/pages/wiki/concepts/foo.md/edit"));
    await waitFor(() => screen.getByDisplayValue("Foo"));
    const textarea = screen.getByLabelText(/body/i);
    await user.clear(textarea);
    await user.type(textarea, "edited");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const [url, payload] = patchSpy.mock.calls[0]!;
    expect(url).toContain("/pages/alpha/");
    expect(payload).toMatchObject({ body: "edited" });
  });
});
