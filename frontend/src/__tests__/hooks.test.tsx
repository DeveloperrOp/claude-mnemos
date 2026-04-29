import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { apiClient } from "../api/client";
import { useProjects } from "../hooks/useProjects";

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useProjects", () => {
  it("returns parsed list on success", async () => {
    const client = makeClient();
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      data: [
        { name: "alpha", vault_root: "/vault/alpha", cwd_patterns: ["~/alpha"] },
        { name: "beta", vault_root: "/vault/beta", cwd_patterns: [] },
      ],
    });

    const { result } = renderHook(() => useProjects(), {
      wrapper: makeWrapper(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0]?.name).toBe("alpha");
    expect(result.current.data?.[1]?.name).toBe("beta");
  });

  it("exposes error state on failure", async () => {
    const client = makeClient();
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new Error("network error"));

    const { result } = renderHook(() => useProjects(), {
      wrapper: makeWrapper(client),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe("network error");
  });
});
