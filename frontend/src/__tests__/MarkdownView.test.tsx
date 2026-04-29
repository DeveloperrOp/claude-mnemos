import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownView } from "../components/markdown/MarkdownView";

describe("MarkdownView", () => {
  it("renders headings", () => {
    render(<MarkdownView body={"# Hello\n\nworld"} />);
    expect(screen.getByRole("heading", { level: 1, name: "Hello" })).toBeInTheDocument();
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("renders fenced code blocks", () => {
    render(<MarkdownView body={"```\ncode here\n```"} />);
    expect(screen.getByText("code here")).toBeInTheDocument();
  });

  it("does NOT render raw HTML (XSS-safe)", () => {
    render(<MarkdownView body={"<script>alert(1)</script>"} />);
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders GFM tables", () => {
    render(
      <MarkdownView body={"| a | b |\n|---|---|\n| 1 | 2 |"} />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
