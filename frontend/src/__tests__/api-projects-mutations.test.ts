import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { createProject } from "../api/projects.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("projects mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("createProject POSTs body with name + display_name + vault_root + cwd_patterns", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "alpha",
        display_name: "Alpha",
        vault_root: "/tmp/alpha",
        cwd_patterns: ["~/code/alpha"],
      },
    });
    const out = await createProject({
      name: "alpha",
      display_name: "Alpha",
      vault_root: "/tmp/alpha",
      cwd_patterns: ["~/code/alpha"],
    });
    expect(apiClient.post).toHaveBeenCalledWith("/projects", {
      name: "alpha",
      display_name: "Alpha",
      vault_root: "/tmp/alpha",
      cwd_patterns: ["~/code/alpha"],
    });
    expect(out.name).toBe("alpha");
  });

  it("createProject defaults cwd_patterns to empty array", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { name: "beta", display_name: null, vault_root: "/tmp/beta", cwd_patterns: [] },
    });
    await createProject({ name: "beta", display_name: null, vault_root: "/tmp/beta" });
    expect(apiClient.post).toHaveBeenCalledWith("/projects", {
      name: "beta",
      display_name: null,
      vault_root: "/tmp/beta",
      cwd_patterns: [],
    });
  });
});
