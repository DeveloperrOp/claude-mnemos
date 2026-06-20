import { describe, it, expect, vi, afterEach } from "vitest";
import { applyUpdate } from "@/api/update.api";
import { apiClient } from "@/api/client";

vi.mock("@/api/client", () => ({
  apiClient: { post: vi.fn(), get: vi.fn() },
}));

// Throw SYNCHRONOUSLY from post() rather than mockRejectedValue: an eager
// rejected promise trips vitest's unhandled-rejection guard even though
// applyUpdate's try/catch handles it. A sync throw inside the try is caught
// just the same and creates no stray rejected promise.
function postThrows(payload: unknown): void {
  vi.mocked(apiClient.post).mockImplementation((() => {
    throw payload;
  }) as never);
}

describe("applyUpdate", () => {
  afterEach(() => vi.resetAllMocks());

  it("returns the result on success", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { started: true, version: "0.1.0" },
    });
    await expect(applyUpdate()).resolves.toEqual({
      started: true,
      version: "0.1.0",
    });
  });

  it("treats a 409 in_progress as 'still updating', not an error", async () => {
    // A re-fired apply while a swap runs must not surface as a failure.
    postThrows({
      response: { status: 409, data: { detail: { error: "in_progress" } } },
    });
    await expect(applyUpdate()).resolves.toEqual({
      started: true,
      version: null,
    });
  });

  it("rethrows a 502 stage_failed", async () => {
    postThrows({
      response: { status: 502, data: { detail: { error: "stage_failed" } } },
    });
    await expect(applyUpdate()).rejects.toMatchObject({
      response: { status: 502 },
    });
  });

  it("rethrows a 409 that is NOT in_progress (e.g. no_update)", async () => {
    postThrows({
      response: { status: 409, data: { detail: { error: "no_update" } } },
    });
    await expect(applyUpdate()).rejects.toMatchObject({
      response: { data: { detail: { error: "no_update" } } },
    });
  });
});
