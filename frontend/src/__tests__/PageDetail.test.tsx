import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PageDetail } from "../pages/PageDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    pages: {
      backlinks: "Backlinks",
      no_backlinks: "No backlinks",
      open_in_obsidian: "Open in Obsidian",
      copy_wikilink: "Copy wikilink",
      edit_disabled: "Edit (in #14c)",
      verify_disabled: "Verify (in #14c)",
      delete_disabled: "Delete (in #14c)",
      not_found_title: "Page not found",
      not_found_hint: "Go back",
    },
    wiki: {
      status: { draft: "Draft", verified: "Verified" },
      type: { concept: "Concept" },
      flavor: { pattern: "Pattern" },
    },
  }, true, true);
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
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("PageDetail", () => {
  it("renders title + body + status + backlinks", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha/wiki/concepts/foo.md") {
        return {
          data: {
            path: "wiki/concepts/foo.md",
            frontmatter: {
              title: "Foo", type: "concept", status: "draft", confidence: 0.7,
              flavor: ["pattern"], sources: [], related: [],
              created: "2026-04-29", updated: "2026-04-29",
              provenance: null, agent_written: true, last_human_edit: null,
            },
            body: "# Foo\n\nbody text",
          },
        };
      }
      if (url === "/pages/alpha/wiki/concepts/foo.md/backlinks") {
        return { data: { backlinks: ["wiki/entities/bar.md"] } };
      }
      throw new Error(`unexpected ${url}`);
    });

    render(wrap(<PageDetail />, "/project/alpha/pages/wiki/concepts/foo.md"));
    await waitFor(() =>
      expect(screen.getByTestId("page-title")).toHaveTextContent("Foo"),
    );
    expect(screen.getByText("body text")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("wiki/entities/bar.md")).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<PageDetail />, "/project/alpha/pages/wiki/missing.md"));
    await waitFor(() =>
      expect(screen.getByText(/Page not found/i)).toBeInTheDocument(),
    );
  });
});
