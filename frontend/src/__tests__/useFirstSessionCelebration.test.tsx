import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { toast } from "sonner";
import { useFirstSessionCelebration } from "@/hooks/useFirstSessionCelebration";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

interface FakeSnapshotShape {
  active_sessions: { project_name: string }[];
  kpi: Record<string, unknown>;
  running_jobs: unknown[];
  errors: string[];
  per_project_session_counts?: Record<string, number>;
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(toast.success).mockClear();
});

describe("useFirstSessionCelebration", () => {
  it("fires toast on 0→1 transition for a project", () => {
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 0 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 1 } } });
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(vi.mocked(toast.success).mock.calls[0][0]).toMatch(/first session/i);
  });

  it("does not fire when count was already > 0", () => {
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 5 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 6 } } });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("does not fire twice for the same project (localStorage guard)", () => {
    localStorage.setItem("mnemos.first_session_celebrated.my-app", "1");
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 0 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 1 } } });
    expect(toast.success).not.toHaveBeenCalled();
  });
});
