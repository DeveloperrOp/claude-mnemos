import { describe, expect, it, vi, beforeAll } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { LostSessionGroups, groupUnassigned } from "@/components/widgets/LostSessionGroups";
import type { LostSession } from "@/types/LostSession";

beforeAll(() => {
  void i18n.changeLanguage("en");
});

function mk(over: Partial<LostSession>): LostSession {
  return {
    session_id: "s1",
    transcript_path: "C:/t/s1.jsonl",
    sha: "sha-s1",
    size_bytes: 100,
    mtime: "2026-06-01T00:00:00Z",
    project_name: "__unassigned__",
    cwd: "D:/code/proj",
    group_root: "D:/code/proj",
    preview: null,
    ...over,
  };
}

describe("groupUnassigned", () => {
  it("groups unassigned sessions by group_root", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", sha: "sha-a", group_root: "D:/code/proj" }),
      mk({ session_id: "b", sha: "sha-b", group_root: "D:/code/proj" }),
      mk({ session_id: "c", sha: "sha-c", group_root: "D:/code/other", cwd: "D:/code/other" }),
    ]);
    expect(groups).toHaveLength(2);
    const proj = groups.find((g) => g.root === "D:/code/proj");
    expect(proj?.sessions.map((s) => s.session_id)).toEqual(["a", "b"]);
  });

  it("falls back to cwd when group_root is missing", () => {
    const groups = groupUnassigned([mk({ session_id: "a", group_root: null, cwd: "D:/x" })]);
    expect(groups[0].root).toBe("D:/x");
  });

  it("skips assigned sessions and sessions without any folder", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", project_name: "perviy" }),
      mk({ session_id: "b", group_root: null, cwd: null }),
    ]);
    expect(groups).toHaveLength(0);
  });

  it("sorts groups by session count desc", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", group_root: "D:/one" }),
      mk({ session_id: "b", group_root: "D:/two" }),
      mk({ session_id: "c", group_root: "D:/two" }),
    ]);
    expect(groups[0].root).toBe("D:/two");
  });

  it("aggregates totalBytes and lastMtime per group", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", size_bytes: 100, mtime: "2026-06-01T00:00:00Z" }),
      mk({ session_id: "b", sha: "sha-b", size_bytes: 250, mtime: "2026-06-03T00:00:00Z" }),
    ]);
    expect(groups[0].totalBytes).toBe(350);
    expect(groups[0].lastMtime).toBe("2026-06-03T00:00:00Z");
  });
});

describe("LostSessionGroups", () => {
  it("renders a card per group with count and create button", () => {
    render(
      <LostSessionGroups
        sessions={[mk({ session_id: "a" }), mk({ session_id: "b", sha: "sha-b" })]}
        onCreateBrain={vi.fn()}
      />,
    );
    expect(screen.getByText(/D:\/code\/proj/)).toBeInTheDocument();
    expect(screen.getByTestId("create-brain")).toBeInTheDocument();
  });

  it("renders one create button per group", () => {
    render(
      <LostSessionGroups
        sessions={[
          mk({ session_id: "a", group_root: "D:/one" }),
          mk({ session_id: "b", sha: "sha-b", group_root: "D:/two" }),
        ]}
        onCreateBrain={vi.fn()}
      />,
    );
    expect(screen.getAllByTestId("create-brain")).toHaveLength(2);
  });

  it("renders nothing when no unassigned groups", () => {
    const { container } = render(
      <LostSessionGroups sessions={[mk({ project_name: "perviy" })]} onCreateBrain={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("calls onCreateBrain with the group on click", () => {
    const cb = vi.fn();
    render(<LostSessionGroups sessions={[mk({})]} onCreateBrain={cb} />);
    fireEvent.click(screen.getByTestId("create-brain"));
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb.mock.calls[0][0].root).toBe("D:/code/proj");
  });
});
