import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { PageCard } from "../components/widgets/PageCard";
import type { WikiPageFrontmatter } from "../types/WikiPage";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: {
      type: { concept: "Concept" },
      status: { draft: "Draft", verified: "Verified" },
      flavor: { pattern: "Pattern" },
    },
    pages: { open: "Open", open_in_obsidian: "Open in Obsidian" },
  }, true, true);
  void i18n.changeLanguage("en");
});

const fm: WikiPageFrontmatter = {
  title: "Foo",
  type: "concept",
  status: "draft",
  confidence: 0.7,
  flavor: ["pattern"],
  sources: [],
  related: [],
  created: "2026-04-29",
  updated: "2026-04-29",
  provenance: null,
  agent_written: true,
  last_human_edit: null,
};

describe("PageCard", () => {
  it("renders title, type, status, confidence", () => {
    render(
      <MemoryRouter>
        <PageCard project="alpha" path="wiki/concepts/foo.md" frontmatter={fm} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Foo")).toBeInTheDocument();
    expect(screen.getByText("Concept")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("Pattern")).toBeInTheDocument();
  });

  it("links to page detail", () => {
    render(
      <MemoryRouter>
        <PageCard project="alpha" path="wiki/concepts/foo.md" frontmatter={fm} />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /foo/i });
    expect(link).toHaveAttribute(
      "href",
      "/project/alpha/pages/wiki/concepts/foo.md",
    );
  });
});
