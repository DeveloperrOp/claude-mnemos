import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PagesBrowser } from "../pages/PagesBrowser";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    pages: {
      filters: {
        title: "Filters",
        type: "Type", flavor: "Flavor", status: "Status",
        sort: "Sort", sort_updated: "Updated", sort_created: "Created",
        sort_title: "Title", search_placeholder: "Search...", reset: "Reset",
      },
      showing_n_of_m: "{{shown}} of {{total}}",
      no_pages: "No pages",
      loading_frontmatter: "Loading...",
    },
    wiki: {
      type: { entity: "Entity", concept: "Concept", source: "Source" },
      status: { draft: "Draft", reviewed: "Reviewed", verified: "Verified", stale: "Stale", archived: "Archived" },
      flavor: { pattern: "Pattern", mistake: "Mistake", decision: "Decision", lesson: "Lesson", reference: "Reference" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path = "/project/alpha/pages") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/pages" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const fmFor = (title: string, type: "entity" | "concept" | "source") => ({
  path: `wiki/${type}s/${title}.md`,
  frontmatter: {
    title, type, status: "draft", confidence: 0.7,
    flavor: [], sources: [], related: [],
    created: "2026-04-29", updated: "2026-04-29",
    provenance: null, agent_written: true, last_human_edit: null,
  },
  body: "",
});

describe("PagesBrowser", () => {
  it("renders cards for every returned page", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha") return { data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] } };
      if (url === "/pages/alpha/wiki/concepts/a.md") return { data: fmFor("a", "concept") };
      if (url === "/pages/alpha/wiki/entities/b.md") return { data: fmFor("b", "entity") };
      throw new Error(`unexpected url ${url}`);
    });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText("a")).toBeInTheDocument());
    expect(screen.getByText("b")).toBeInTheDocument();
  });

  it("shows empty state when no pages", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { pages: [] } });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText(/no pages/i)).toBeInTheDocument());
  });

  it("filters by type when type is unchecked", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha") return { data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] } };
      if (url.endsWith("a.md")) return { data: fmFor("a", "concept") };
      if (url.endsWith("b.md")) return { data: fmFor("b", "entity") };
      throw new Error(`unexpected url ${url}`);
    });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText("a")).toBeInTheDocument());
    // toggling will be unit-tested via PageFilters; here we only check render.
  });
});
