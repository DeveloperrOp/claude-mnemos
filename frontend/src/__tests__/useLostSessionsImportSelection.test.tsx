import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { useLostSessionsImportSelection } from "../hooks/useLostSessionsImportSelection";
import type { LostSession } from "../types/LostSession";

function wrap({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const SESSION: LostSession = {
  session_id: "s1",
  transcript_path: "/tmp/s1.jsonl",
  sha: "abc",
  size_bytes: 100,
  mtime: "2026-05-24T00:00:00Z",
  project_name: "alpha",
  cwd: null,
  preview: null,
};

describe("useLostSessionsImportSelection", () => {
  it("defaults extract=false when not specified (P0-2 fix)", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { queued: 1, skipped: 0, missing: [], session_ids: ["s1"] },
    });
    const { result } = renderHook(() => useLostSessionsImportSelection(), {
      wrapper: wrap,
    });
    result.current.mutate({ selected: [SESSION] });
    await waitFor(() => expect(post).toHaveBeenCalled());
    const body = post.mock.calls[post.mock.calls.length - 1][1] as { extract: boolean };
    expect(body.extract).toBe(false);
  });

  it("honors explicit extract=true override", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { queued: 1, skipped: 0, missing: [], session_ids: ["s1"] },
    });
    const { result } = renderHook(() => useLostSessionsImportSelection(), {
      wrapper: wrap,
    });
    result.current.mutate({ selected: [SESSION], extract: true });
    await waitFor(() => expect(post).toHaveBeenCalled());
    const body = post.mock.calls[post.mock.calls.length - 1][1] as { extract: boolean };
    expect(body.extract).toBe(true);
  });
});
