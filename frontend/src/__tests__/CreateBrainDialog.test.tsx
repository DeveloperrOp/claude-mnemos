import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { CreateBrainDialog } from "@/components/widgets/CreateBrainDialog";
import * as projectsApi from "@/api/projects.api";
import * as lostApi from "@/api/lost_sessions.api";
import type { LostGroup } from "@/components/widgets/LostSessionGroups";
import type { LostSession } from "@/types/LostSession";

vi.mock("@/api/projects.api");
vi.mock("@/api/lost_sessions.api");

beforeAll(() => {
  void i18n.changeLanguage("en");
});

function mkSession(over: Partial<LostSession>): LostSession {
  return {
    session_id: "s1",
    transcript_path: "C:/t/s1.jsonl",
    sha: "sha-s1",
    size_bytes: 100,
    mtime: "2026-06-01T00:00:00Z",
    project_name: "__unassigned__",
    cwd: "D:/code/my-project",
    group_root: "D:/code/my-project",
    preview: null,
    ...over,
  };
}

const GROUP: LostGroup = {
  root: "D:/code/my-project",
  sessions: [
    mkSession({ session_id: "a", sha: "sha-a" }),
    mkSession({ session_id: "b", sha: "sha-b" }),
  ],
  totalBytes: 200,
  lastMtime: "2026-06-01T00:00:00Z",
};

function renderDialog(over?: { onDone?: () => void; onOpenChange?: (o: boolean) => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onDone = over?.onDone ?? vi.fn();
  const onOpenChange = over?.onOpenChange ?? vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <CreateBrainDialog open group={GROUP} onOpenChange={onOpenChange} onDone={onDone} />
    </QueryClientProvider>,
  );
  return { onDone, onOpenChange };
}

describe("CreateBrainDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("prefills display name and vault from group root", () => {
    renderDialog();
    expect(screen.getByTestId("create-brain-name")).toHaveValue("My Project");
    expect(screen.getByTestId("create-brain-vault")).toHaveValue(
      "D:/code/my-project/.mnemos",
    );
  });

  it("happy path: creates project then imports sessions with extract:false, calls onDone", async () => {
    vi.mocked(projectsApi.createProject).mockResolvedValue({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    });
    vi.mocked(lostApi.importLostSessionsSelection).mockResolvedValue({
      queued: 2,
      skipped: 0,
      missing: [],
      session_ids: ["a", "b"],
    });
    const user = userEvent.setup();
    const { onDone } = renderDialog();

    await user.click(screen.getByTestId("create-brain-submit"));

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(projectsApi.createProject).toHaveBeenCalledWith({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    });
    expect(lostApi.importLostSessionsSelection).toHaveBeenCalledWith({
      project_name: "my-project",
      session_ids: ["a", "b"],
      extract: false,
    });
  });

  it("409 on create: shows inline name-taken error, never imports, keeps dialog open", async () => {
    vi.mocked(projectsApi.createProject).mockRejectedValue(
      Object.assign(new Error("Request failed with status code 409"), {
        response: { status: 409 },
      }),
    );
    const user = userEvent.setup();
    const { onDone, onOpenChange } = renderDialog();

    await user.click(screen.getByTestId("create-brain-submit"));

    expect(await screen.findByTestId("create-brain-error")).toBeInTheDocument();
    expect(lostApi.importLostSessionsSelection).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    // Dialog fields are still there for the user to edit the name.
    expect(screen.getByTestId("create-brain-name")).toBeInTheDocument();
  });

  it("import failure after successful create: shows honest error, onDone not called", async () => {
    vi.mocked(projectsApi.createProject).mockResolvedValue({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    });
    vi.mocked(lostApi.importLostSessionsSelection).mockRejectedValue(
      new Error("boom-import"),
    );
    const user = userEvent.setup();
    const { onDone, onOpenChange } = renderDialog();

    await user.click(screen.getByTestId("create-brain-submit"));

    const err = await screen.findByTestId("create-brain-error");
    expect(err.textContent).toMatch(/создан, но импорт/);
    expect(err.textContent).toMatch(/boom-import/);
    expect(onDone).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("double submit: second click while pending does not call createProject twice", async () => {
    let resolveCreate!: (v: projectsApi.CreateProjectBody & { name: string }) => void;
    vi.mocked(projectsApi.createProject).mockImplementation(
      () =>
        new Promise((res) => {
          resolveCreate = res as never;
        }),
    );
    const user = userEvent.setup();
    renderDialog();

    const btn = screen.getByTestId("create-brain-submit");
    await user.click(btn);
    // While the first createProject is still in flight the confirm button is
    // disabled; even a programmatic second click must be a no-op.
    btn.click();
    expect(projectsApi.createProject).toHaveBeenCalledTimes(1);
    resolveCreate({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    });
  });
});
