import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { TopSessionsTable } from "../components/widgets/TopSessionsTable";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      top_sessions_title: "Top sessions",
      top_sessions_subtitle: "All-time top by tokens",
      col_project: "Project",
      col_session: "Session",
      col_ingested_at: "Ingested",
      col_tokens_total: "Tokens",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const ROWS = [
  {
    project: "alpha", session_id: "abc-very-long",
    ingested_at: "2026-04-29T12:00:00Z",
    tokens_input: 100, tokens_output: 200, tokens_total: 300, raw_bytes: 1024,
  },
];

describe("TopSessionsTable", () => {
  it("renders subtitle + row", () => {
    render(<MemoryRouter><TopSessionsTable rows={ROWS} /></MemoryRouter>);
    expect(screen.getByText("Top sessions")).toBeInTheDocument();
    expect(screen.getByText(/all-time/i)).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<MemoryRouter><TopSessionsTable rows={[]} /></MemoryRouter>);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
