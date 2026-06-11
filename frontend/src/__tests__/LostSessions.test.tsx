import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { LostSessions } from "../pages/LostSessions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    lost_sessions: {
      title: "Lost sessions",
      scan: "Scan", scanning: "Scanning...",
      session_id: "session_id", sha: "sha", size: "size", mtime: "mtime",
      transcript: "transcript",
      no_lost: "All accounted for",
      showing_n: "{{count}} sessions",
      import_button: "Import",
      ignore_button: "Ignore",
      imported_toast: "Import queued",
      ignored_toast: "Marked ignored",
      ignore_modal_title: "Mark session as ignored?",
      ignore_modal_desc: "This will hide the session from the lost-sessions list. The transcript file is not deleted.",
    },
    confirm: {
      cancel: "Cancel",
      confirm: "Confirm",
      working: "Working...",
      typed_confirm_input_placeholder: "Type {{phrase}} to confirm",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
  );
}

describe("LostSessions", () => {
  it("renders sessions with project badges", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        sessions: [
          {
            session_id: "abc-very-long-id-string",
            transcript_path: "/x.md",
            sha: "deadbeefcafe",
            size_bytes: 1024,
            mtime: "2026-04-29T12:00:00Z",
            project_name: "alpha",
          },
        ],
        total: 1,
      },
    });
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
  });

  it("Scan button triggers POST /lost-sessions/scan and refetch", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { sessions: [], total: 0 } });
    const user = userEvent.setup();
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByRole("button", { name: /scan/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /scan/i }));
    expect(post).toHaveBeenCalledWith("/lost-sessions/scan");
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByText(/all accounted for/i)).toBeInTheDocument());
  });

  const unassignedResponse = {
    data: {
      sessions: [
        {
          session_id: "orphan-session-id-1",
          transcript_path: "/t/orphan.jsonl",
          sha: "feedfacecafe",
          size_bytes: 2048,
          mtime: "2026-06-10T12:00:00Z",
          project_name: "__unassigned__",
          cwd: "D:/code/orphan-proj",
          group_root: "D:/code/orphan-proj",
        },
      ],
      total: 1,
    },
  };

  it("renders folder groups block when unassigned sessions exist", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(unassignedResponse);
    render(wrap(<LostSessions />));
    // The group root also appears as the session row's cwd — assert at least one match.
    expect((await screen.findAllByText(/orphan-proj/)).length).toBeGreaterThan(0);
    expect(screen.getByTestId("create-brain")).toBeInTheDocument();
  });

  it("clicking create-brain opens the CreateBrainDialog", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(unassignedResponse);
    const user = userEvent.setup();
    render(wrap(<LostSessions />));
    await user.click(await screen.findByTestId("create-brain"));
    expect(await screen.findByTestId("create-brain-submit")).toBeInTheDocument();
  });
});
