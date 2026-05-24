import { describe, it, expect, vi, beforeAll } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { useProjectUpdate } from "../hooks/useProjectUpdate";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        saved_toast: "Saved",
        save_error_toast: "Save failed: {{message}}",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useProjectUpdate", () => {
  it("fires success toast after save", async () => {
    const success = vi.spyOn(toast, "success").mockImplementation(() => "" as never);
    vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { name: "alpha", display_name: "Alpha", vault_root: "/v", cwd_patterns: [] },
    });
    const { result } = renderHook(() => useProjectUpdate("alpha"), { wrapper: wrap });
    result.current.mutate({ display_name: "Alpha" });
    await waitFor(() => expect(success).toHaveBeenCalledWith("Saved"));
  });

  it("fires error toast on failure", async () => {
    const error = vi.spyOn(toast, "error").mockImplementation(() => "" as never);
    vi.spyOn(apiClient, "patch").mockRejectedValue({ message: "boom" });
    const { result } = renderHook(() => useProjectUpdate("alpha"), { wrapper: wrap });
    result.current.mutate({ display_name: "X" });
    await waitFor(() => expect(error).toHaveBeenCalled());
  });
});
