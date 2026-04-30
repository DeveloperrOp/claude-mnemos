import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { deleteProject } from "../api/projects.api";

describe("deleteProject", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "delete");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("DELETE /projects/{slug} happy path", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: undefined });
    await expect(deleteProject("p1")).resolves.toBeUndefined();
    expect(apiClient.delete).toHaveBeenCalledWith("/projects/p1", { params: undefined });
  });

  it("DELETE supports ?force=true", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: undefined });
    await deleteProject("p1", { force: true });
    expect(apiClient.delete).toHaveBeenCalledWith("/projects/p1", { params: { force: true } });
  });
});
