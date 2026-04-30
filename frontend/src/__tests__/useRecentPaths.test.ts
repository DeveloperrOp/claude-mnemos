import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecentPaths } from "../hooks/useRecentPaths";

beforeEach(() => {
  localStorage.clear();
});

describe("useRecentPaths", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useRecentPaths());
    expect(result.current.recent).toEqual([]);
  });

  it("adds path to head", () => {
    const { result } = renderHook(() => useRecentPaths());
    act(() => result.current.addRecent("/tmp/a"));
    expect(result.current.recent).toEqual(["/tmp/a"]);
  });

  it("dedupes and moves to head on re-add", () => {
    const { result } = renderHook(() => useRecentPaths());
    act(() => result.current.addRecent("/tmp/a"));
    act(() => result.current.addRecent("/tmp/b"));
    act(() => result.current.addRecent("/tmp/a"));
    expect(result.current.recent).toEqual(["/tmp/a", "/tmp/b"]);
  });

  it("caps at 5 entries", () => {
    const { result } = renderHook(() => useRecentPaths());
    for (let i = 0; i < 7; i++) {
      act(() => result.current.addRecent(`/tmp/${i}`));
    }
    expect(result.current.recent).toHaveLength(5);
    expect(result.current.recent[0]).toBe("/tmp/6");
  });

  it("persists across hook instances via localStorage", () => {
    const { result: r1 } = renderHook(() => useRecentPaths());
    act(() => r1.current.addRecent("/tmp/x"));
    const { result: r2 } = renderHook(() => useRecentPaths());
    expect(r2.current.recent).toEqual(["/tmp/x"]);
  });
});
