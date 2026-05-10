import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { apiClient } from "../api/client";
import {
  useProjectSettings,
  useProjectSettingsMutation,
} from "../hooks/useProjectSettings";

const FULL = {
  version: 1,
  locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  snapshots: { daily_enabled: true, retention_days: 180 },
};

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

beforeEach(() => {
  vi.spyOn(apiClient, "get");
  vi.spyOn(apiClient, "patch");
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("useProjectSettings", () => {
  it("fetches project settings", async () => {
    const client = makeClient();
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    const { result } = renderHook(() => useProjectSettings("p1"), {
      wrapper: makeWrapper(client),
    });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.snapshots.retention_days).toBe(180);
    expect(apiClient.get).toHaveBeenCalledWith("/settings/p1");
  });

  it("mutation patches and updates cache", async () => {
    const client = makeClient();
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: FULL });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { ...FULL, snapshots: { daily_enabled: true, retention_days: 30 } },
    });

    const wrapper = makeWrapper(client);
    const query = renderHook(() => useProjectSettings("p1"), { wrapper });
    const mut = renderHook(() => useProjectSettingsMutation("p1"), { wrapper });
    await waitFor(() => expect(query.result.current.data).toBeDefined());

    mut.result.current.mutate({ snapshots: { retention_days: 30 } });
    await waitFor(() =>
      expect(query.result.current.data?.snapshots.retention_days).toBe(30),
    );
  });
});
