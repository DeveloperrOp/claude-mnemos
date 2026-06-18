import { describe, it, expect, vi, beforeAll } from "vitest";
import { act } from "react";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import i18n from "../i18n";
import * as pagesApi from "../api/pages.api";
import { usePagePatch } from "../hooks/usePagePatch";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      pages: {
        editor: {
          saved_toast: "Page saved",
          stale_conflict: "This page changed on disk — reloaded.",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

function wrap(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("usePagePatch", () => {
  it("invalidates the page query on a 409 conflict", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(pagesApi, "patchPage").mockRejectedValue({ response: { status: 409 } });
    const { result } = renderHook(() => usePagePatch(), { wrapper: wrap(qc) });
    await act(async () => {
      try {
        await result.current.mutateAsync({
          project: "proj",
          page_ref: "ref",
          body: { body: "x" },
        });
      } catch {
        /* expected */
      }
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["page", "proj", "ref"] });
  });

  it("does NOT invalidate the page query on a non-409 error", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(pagesApi, "patchPage").mockRejectedValue({ response: { status: 500 } });
    const error = vi.spyOn(toast, "error").mockImplementation(() => "" as never);
    const { result } = renderHook(() => usePagePatch(), { wrapper: wrap(qc) });
    await act(async () => {
      try {
        await result.current.mutateAsync({
          project: "proj",
          page_ref: "ref",
          body: { body: "x" },
        });
      } catch {
        /* expected */
      }
    });
    expect(spy).not.toHaveBeenCalledWith({ queryKey: ["page", "proj", "ref"] });
    expect(error).toHaveBeenCalled();
  });
});
